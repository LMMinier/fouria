"""Persistent SQLite action queue + session store for FOURIA v0.2.

Safety invariants enforced here:
- Status flow: pending → approved → claimed → done | failed | ambiguous
- Safe (transport/window) actions are auto-approved on enqueue.
- Mutating actions must be explicitly approved before the bridge sees them.
- Claimed actions are owned by one session; a different bridge session cannot claim them.
- On session reconnect, claimed-but-not-finished actions become 'ambiguous'.
  Ambiguous actions are never silently replayed.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path
import os

ROOT    = Path(os.environ.get("FOURIA_ROOT", Path(__file__).resolve().parents[1]))
DB_PATH = ROOT / "data" / "fouria.db"

_lock = threading.Lock()

# These actions are safe to execute without user confirmation.
AUTO_APPROVE = frozenset({
    "play", "stop", "record", "save", "undo", "redo",
    "show_channel_rack", "show_mixer", "show_playlist", "show_piano_roll", "notify",
    "set_tempo",
    "render", "toggle_record_mode", "jump_to_start", "jump_to_end", "tempo_tap",
})


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with _lock:
        conn = _connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                bridge_id      TEXT    NOT NULL UNIQUE,
                project_hash   TEXT    NOT NULL DEFAULT '',
                registered_at  REAL    NOT NULL,
                last_seen      REAL    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS actions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id     INTEGER REFERENCES sessions(id),
                project_hash   TEXT    NOT NULL DEFAULT '',
                action         TEXT    NOT NULL,
                value          TEXT    NOT NULL DEFAULT '{}',
                status         TEXT    NOT NULL DEFAULT 'pending',
                queued_at      REAL    NOT NULL,
                approved_at    REAL,
                claimed_at     REAL,
                executed_at    REAL
            );
            CREATE TABLE IF NOT EXISTS results (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id      INTEGER NOT NULL,
                ok             INTEGER NOT NULL,
                output         TEXT,
                error          TEXT,
                received_at    REAL    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);
            CREATE INDEX IF NOT EXISTS idx_actions_id     ON actions(id);
            CREATE INDEX IF NOT EXISTS idx_results_aid    ON results(action_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_bid   ON sessions(bridge_id);
        """)
        conn.commit()
        conn.close()


# ── Sessions ──────────────────────────────────────────────────────────────────

def register_session(bridge_id: str, project_hash: str = "") -> int:
    """Upsert a bridge session; return the integer session row id.

    On reconnect, previously claimed-but-not-finished actions for this bridge
    are marked 'ambiguous' so they are never silently replayed.
    """
    now = time.time()
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT id FROM sessions WHERE bridge_id=?", (bridge_id,)
        ).fetchone()
        if row:
            session_id = row[0]
            conn.execute(
                "UPDATE actions SET status='ambiguous'"
                " WHERE session_id=? AND status='claimed'",
                (session_id,),
            )
            conn.execute(
                "UPDATE sessions SET project_hash=?, last_seen=? WHERE id=?",
                (project_hash, now, session_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO sessions (bridge_id, project_hash, registered_at, last_seen)"
                " VALUES (?,?,?,?)",
                (bridge_id, project_hash, now, now),
            )
            session_id = cur.lastrowid
        conn.commit()
        conn.close()
    return session_id


def refresh_session(session_id: int, project_hash: str = ""):
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE sessions SET last_seen=?, project_hash=? WHERE id=?",
            (time.time(), project_hash, session_id),
        )
        conn.commit()
        conn.close()


# ── Actions ───────────────────────────────────────────────────────────────────

def enqueue(action: str, value: dict, session_id: int = None, project_hash: str = "") -> dict:
    """Create a new action row.

    Safe (transport/window) actions are immediately 'approved'.
    Mutating actions start as 'pending' and require an explicit approve() call
    before the bridge will see them.
    """
    status      = "approved" if action in AUTO_APPROVE else "pending"
    now         = time.time()
    approved_at = now if status == "approved" else None
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO actions"
            " (session_id, project_hash, action, value, status, queued_at, approved_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (session_id, project_hash, action, json.dumps(value or {}),
             status, now, approved_at),
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
    return {
        "id": row_id, "action": action, "value": value,
        "status": status, "queued_at": now,
    }


def approve(action_id: int) -> bool:
    """Move a pending action to approved. Returns True if the row changed."""
    now = time.time()
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "UPDATE actions SET status='approved', approved_at=?"
            " WHERE id=? AND status='pending'",
            (now, action_id),
        )
        changed = cur.rowcount > 0
        conn.commit()
        conn.close()
    return changed


def claim_batch(session_id: int, limit: int = 20) -> list:
    """Atomically claim up to `limit` approved actions for this session.

    Uses a single locked transaction so no two bridge sessions can claim the
    same row. Claimed actions are only returned to the claiming session and
    will never be returned to a different session.
    """
    now = time.time()
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, action, value FROM actions"
            " WHERE status='approved' ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        items = []
        for r in rows:
            conn.execute(
                "UPDATE actions SET status='claimed', claimed_at=?, session_id=?"
                " WHERE id=? AND status='approved'",
                (now, session_id, r[0]),
            )
            items.append({"id": r[0], "action": r[1], "value": json.loads(r[2])})
        conn.commit()
        conn.close()
    return items


def pending_since(last_id: int, limit: int = 50) -> list:
    """Return approved actions with id > last_id. Kept for test backward-compat."""
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, action, value FROM actions"
            " WHERE id > ? AND status IN ('queued','approved')"
            " ORDER BY id LIMIT ?",
            (last_id, limit),
        ).fetchall()
        conn.close()
    return [{"id": r[0], "action": r[1], "value": json.loads(r[2])} for r in rows]


def mark_executed(action_id: int):
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE actions SET status='executed', executed_at=? WHERE id=?",
            (time.time(), action_id),
        )
        conn.commit()
        conn.close()


def store_result(action_id: int, ok: bool, output=None, error=None):
    final_status = "done" if ok else "failed"
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO results (action_id, ok, output, error, received_at)"
            " VALUES (?,?,?,?,?)",
            (action_id, int(ok), json.dumps(output), error, time.time()),
        )
        conn.execute(
            "UPDATE actions SET status=?, executed_at=? WHERE id=?",
            (final_status, time.time(), action_id),
        )
        conn.commit()
        conn.close()


def recent_results(limit: int = 50) -> list:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            """SELECT r.id, r.action_id, r.ok, r.output, r.error, r.received_at, a.action
               FROM results r JOIN actions a ON a.id = r.action_id
               ORDER BY r.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
    return [
        {
            "id": r[0], "action_id": r[1], "ok": bool(r[2]),
            "output": json.loads(r[3]) if r[3] else None,
            "error": r[4], "received_at": r[5], "action": r[6],
        }
        for r in reversed(rows)
    ]


def queue_depth() -> int:
    with _lock:
        conn = _connect()
        n = conn.execute(
            "SELECT COUNT(*) FROM actions WHERE status IN ('pending','approved','claimed')"
        ).fetchone()[0]
        conn.close()
    return n


def ambiguous_actions(limit: int = 20) -> list:
    """Return actions that landed in 'ambiguous' state (claimed but bridge crashed)."""
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, action, value, queued_at, claimed_at"
            " FROM actions WHERE status='ambiguous' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
    return [
        {
            "id": r[0], "action": r[1], "value": json.loads(r[2]),
            "queued_at": r[3], "claimed_at": r[4],
        }
        for r in rows
    ]
