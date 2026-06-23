"""Tests for the pending→approved→claimed→done/failed safety flow."""
import os
import shutil
import tempfile
import importlib.util
from pathlib import Path


def _store(tmp):
    spec = importlib.util.spec_from_file_location(
        "action_store_af",
        Path(__file__).parent.parent / "server" / "action_store.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DB_PATH = Path(tmp) / "test.db"
    mod.init_db()
    return mod


# ── Status on enqueue ─────────────────────────────────────────────────────────

def test_safe_action_is_auto_approved():
    tmp = tempfile.mkdtemp()
    try:
        s = _store(tmp)
        item = s.enqueue("play", {})
        assert item["status"] == "approved"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_mutating_action_is_pending():
    tmp = tempfile.mkdtemp()
    try:
        s = _store(tmp)
        item = s.enqueue("set_mixer_volume", {"index": 1, "volume": 0.8})
        assert item["status"] == "pending"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_all_safe_actions_auto_approved():
    tmp = tempfile.mkdtemp()
    try:
        s = _store(tmp)
        for action in s.AUTO_APPROVE:
            item = s.enqueue(action, {})
            assert item["status"] == "approved", f"{action} should be auto-approved"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── approve() ────────────────────────────────────────────────────────────────

def test_approve_pending_returns_true():
    tmp = tempfile.mkdtemp()
    try:
        s = _store(tmp)
        item = s.enqueue("mute_mixer", {"index": 2, "enabled": True})
        assert s.approve(item["id"]) is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_approve_nonexistent_returns_false():
    tmp = tempfile.mkdtemp()
    try:
        s = _store(tmp)
        assert s.approve(99999) is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_approve_already_approved_returns_false():
    tmp = tempfile.mkdtemp()
    try:
        s = _store(tmp)
        item = s.enqueue("play", {})          # auto-approved
        assert s.approve(item["id"]) is False  # already approved — no-op
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── claim_batch() ─────────────────────────────────────────────────────────────

def test_claim_batch_returns_approved():
    tmp = tempfile.mkdtemp()
    try:
        s   = _store(tmp)
        sid = s.register_session("bridge-claim-test")
        s.enqueue("play", {})   # auto-approved
        s.enqueue("stop", {})   # auto-approved
        claimed = s.claim_batch(sid)
        assert len(claimed) == 2
        assert all(c["action"] in ("play", "stop") for c in claimed)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pending_action_not_claimable():
    tmp = tempfile.mkdtemp()
    try:
        s   = _store(tmp)
        sid = s.register_session("bridge-noclaim")
        s.enqueue("set_mixer_volume", {"index": 1, "volume": 0.8})  # pending
        claimed = s.claim_batch(sid)
        assert claimed == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_claimed_not_returned_again():
    tmp = tempfile.mkdtemp()
    try:
        s    = _store(tmp)
        sid  = s.register_session("bridge-once")
        s.enqueue("play", {})
        first  = s.claim_batch(sid)
        second = s.claim_batch(sid)
        assert len(first) == 1
        assert second == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_approve_then_claim():
    tmp = tempfile.mkdtemp()
    try:
        s    = _store(tmp)
        sid  = s.register_session("bridge-approve-claim")
        item = s.enqueue("mute_channel", {"index": 0, "enabled": True})
        assert s.claim_batch(sid) == []     # pending — not claimable yet
        s.approve(item["id"])
        claimed = s.claim_batch(sid)
        assert len(claimed) == 1 and claimed[0]["action"] == "mute_channel"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── store_result() ────────────────────────────────────────────────────────────

def test_result_ok_marks_done():
    tmp = tempfile.mkdtemp()
    try:
        s    = _store(tmp)
        sid  = s.register_session("bridge-result")
        item = s.enqueue("play", {})
        s.claim_batch(sid)
        s.store_result(item["id"], True, {"action": "play"})
        results = s.recent_results()
        r = next(x for x in results if x["action_id"] == item["id"])
        assert r["ok"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_result_failure_marks_failed():
    tmp = tempfile.mkdtemp()
    try:
        s    = _store(tmp)
        sid  = s.register_session("bridge-fail")
        item = s.enqueue("play", {})
        s.claim_batch(sid)
        s.store_result(item["id"], False, error="timeout")
        results = s.recent_results()
        r = next(x for x in results if x["action_id"] == item["id"])
        assert r["ok"] is False and r["error"] == "timeout"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
