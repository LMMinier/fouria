"""Persistent SQLite-backed action queue and result store.
Replaces the in-memory ACTION_QUEUE list so actions survive server restarts
and the bridge can always pick up from the last executed ID.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path
import os

ROOT = Path(os.environ.get("FOURIA_ROOT", Path(__file__).resolve().parents[1]))
DB_PATH = ROOT / "data" / "fouria.db"

_lock = threading.Lock()


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    with _lock:
        conn = _connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS actions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT    NOT NULL,
                value       TEXT    NOT NULL DEFAULT '{}',
                status      TEXT    NOT NULL DEFAULT 'queued',
                queued_at   REAL    NOT NULL,
                executed_at REAL
            );
            CREATE TABLE IF NOT EXISTS results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id   INTEGER NOT NULL,
                ok          INTEGER NOT NULL,
                output      TEXT,
                error       TEXT,
                received_at REAL    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);
            CREATE INDEX IF NOT EXISTS idx_actions_id     ON actions(id);
            CREATE INDEX IF NOT EXISTS idx_results_aid   ON results(action_id);
        """)
        conn.commit()
        conn.close()


def enqueue(action: str, value: dict) -> dict:
    """Insert a new queued action, return the row as a dict."""
    with _lock:
        conn = _connect()
        now = time.time()
        cur = conn.execute(
            "INSERT INTO actions (action, value, status, queued_at) VALUES (?, ?, 'queued', ?)",
            (action, json.dumps(value or {}), now),
        )
        row_id = cur.lastrowid
        conn.commit()
        conn.close()
    return {"id": row_id, "action": action, "value": value, "status": "queued", "queued_at": now}


def pending_since(last_id: int, limit: int = 50) -> list:
    """Return queued actions with id > last_id, ordered ascending."""
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, action, value FROM actions WHERE id > ? AND status = 'queued' ORDER BY id LIMIT ?",
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
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO results (action_id, ok, output, error, received_at) VALUES (?, ?, ?, ?, ?)",
            (action_id, int(ok), json.dumps(output), error, time.time()),
        )
        if ok:
            conn.execute(
                "UPDATE actions SET status='done', executed_at=? WHERE id=?",
                (time.time(), action_id),
            )
        else:
            conn.execute("UPDATE actions SET status='failed' WHERE id=?", (action_id,))
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
        {"id": r[0], "action_id": r[1], "ok": bool(r[2]),
         "output": json.loads(r[3]) if r[3] else None,
         "error": r[4], "received_at": r[5], "action": r[6]}
        for r in reversed(rows)
    ]


def queue_depth() -> int:
    with _lock:
        conn = _connect()
        n = conn.execute("SELECT COUNT(*) FROM actions WHERE status='queued'").fetchone()[0]
        conn.close()
    return n
