"""Unit tests for action_store SQLite persistence layer."""
import sys, os, tempfile, shutil
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))


def _patched_store(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "action_store_test",
        os.path.join(os.path.dirname(__file__), "..", "server", "action_store.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DB_PATH = Path(tmp_path) / "test_fouria.db"
    mod.init_db()
    return mod


def test_enqueue_returns_dict_with_id():
    tmp = tempfile.mkdtemp()
    try:
        store = _patched_store(tmp)
        item = store.enqueue("mute_mixer", {"index": 3})
        assert isinstance(item["id"], int) and item["action"] == "mute_mixer"
    finally: shutil.rmtree(tmp, ignore_errors=True)

def test_pending_since_returns_queued():
    tmp = tempfile.mkdtemp()
    try:
        store = _patched_store(tmp)
        store.enqueue("play", {}); store.enqueue("stop", {})
        items = store.pending_since(0)
        names = [i["action"] for i in items]
        assert "play" in names and "stop" in names
    finally: shutil.rmtree(tmp, ignore_errors=True)

def test_pending_since_excludes_old():
    tmp = tempfile.mkdtemp()
    try:
        store = _patched_store(tmp)
        first = store.enqueue("play", {}); store.enqueue("stop", {})
        assert all(i["id"] > first["id"] for i in store.pending_since(first["id"]))
    finally: shutil.rmtree(tmp, ignore_errors=True)

def test_store_result_ok():
    tmp = tempfile.mkdtemp()
    try:
        store = _patched_store(tmp)
        item = store.enqueue("save", {})
        store.store_result(item["id"], True, {"saved": True})
        assert any(r["action_id"] == item["id"] and r["ok"] for r in store.recent_results())
    finally: shutil.rmtree(tmp, ignore_errors=True)

def test_failed_result_stored():
    tmp = tempfile.mkdtemp()
    try:
        store = _patched_store(tmp)
        item = store.enqueue("set_mixer_volume", {"index": 1, "volume": 0.8})
        store.store_result(item["id"], False, error="bridge timeout")
        failed = [r for r in store.recent_results() if r["action_id"] == item["id"]]
        assert failed and not failed[0]["ok"] and failed[0]["error"] == "bridge timeout"
    finally: shutil.rmtree(tmp, ignore_errors=True)

def test_queue_depth():
    tmp = tempfile.mkdtemp()
    try:
        store = _patched_store(tmp)
        store.enqueue("play", {}); store.enqueue("stop", {})
        assert store.queue_depth() >= 2
    finally: shutil.rmtree(tmp, ignore_errors=True)
