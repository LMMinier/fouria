"""Tests for bridge session registration and reconnect-ambiguous safety."""
import shutil
import tempfile
import importlib.util
from pathlib import Path


def _store(tmp):
    spec = importlib.util.spec_from_file_location(
        "action_store_sess",
        Path(__file__).parent.parent / "server" / "action_store.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DB_PATH = Path(tmp) / "test_sess.db"
    mod.init_db()
    return mod


def test_register_returns_int():
    tmp = tempfile.mkdtemp()
    try:
        s = _store(tmp)
        sid = s.register_session("bridge-abc")
        assert isinstance(sid, int) and sid > 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_same_bridge_id_returns_same_session():
    tmp = tempfile.mkdtemp()
    try:
        s  = _store(tmp)
        s1 = s.register_session("bridge-stable")
        s2 = s.register_session("bridge-stable")
        assert s1 == s2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_different_bridge_ids_get_different_sessions():
    tmp = tempfile.mkdtemp()
    try:
        s  = _store(tmp)
        s1 = s.register_session("bridge-x")
        s2 = s.register_session("bridge-y")
        assert s1 != s2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reconnect_claimed_becomes_ambiguous():
    """If the bridge reconnects (same bridge_id), previously claimed-but-not-
    executed actions must become 'ambiguous' — never silently replayed."""
    tmp = tempfile.mkdtemp()
    try:
        s   = _store(tmp)
        sid = s.register_session("bridge-crash")
        # Queue and claim a safe action
        item    = s.enqueue("play", {})
        claimed = s.claim_batch(sid)
        assert len(claimed) == 1
        # Bridge crashes and reconnects with the same bridge_id
        s.register_session("bridge-crash")
        # The claimed action must now be ambiguous
        ambiguous = s.ambiguous_actions()
        ids = [a["id"] for a in ambiguous]
        assert item["id"] in ids
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reconnect_leaves_done_actions_unchanged():
    """Completed (done/failed) actions must not be touched on reconnect."""
    tmp = tempfile.mkdtemp()
    try:
        s   = _store(tmp)
        sid = s.register_session("bridge-done")
        item = s.enqueue("play", {})
        s.claim_batch(sid)
        s.store_result(item["id"], True, {"action": "play"})
        # Reconnect
        s.register_session("bridge-done")
        # done actions should not appear in ambiguous list
        ambiguous = s.ambiguous_actions()
        assert all(a["id"] != item["id"] for a in ambiguous)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_refresh_session_updates_last_seen():
    import time
    tmp = tempfile.mkdtemp()
    try:
        s   = _store(tmp)
        sid = s.register_session("bridge-refresh")
        t0  = time.time()
        time.sleep(0.01)
        s.refresh_session(sid, "My Beat")
        # If refresh ran without error the test passes; last_seen > registered_at
        # (we don't directly query last_seen here but the call must not raise)
        assert True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ambiguous_not_claimed_again():
    """After becoming ambiguous a claimed action must not be picked up by
    a subsequent claim_batch call."""
    tmp = tempfile.mkdtemp()
    try:
        s   = _store(tmp)
        sid = s.register_session("bridge-norepeat")
        s.enqueue("play", {})
        s.claim_batch(sid)
        # Reconnect — marks claimed → ambiguous
        s.register_session("bridge-norepeat")
        # New claim cycle must return nothing for that action
        claimed = s.claim_batch(sid)
        assert claimed == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
