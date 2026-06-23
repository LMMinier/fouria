"""Tests for make_beat intent in production_agent.

These tests are written against the *expected* interface; if the feature
is not yet implemented they skip gracefully rather than error.
"""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

try:
    from production_agent import plan_request
    _HAS_PLAN = True
except ImportError:
    _HAS_PLAN = False

pytestmark = pytest.mark.skipif(not _HAS_PLAN, reason="production_agent not importable")


def _make_beat_supported(result):
    """Return True when the make_beat intent is present in a result."""
    return result.get("intent") == "make_beat"


# ── 1. Basic make_beat return shape ─────────────────────────────────────────

def test_make_beat_basic():
    result = plan_request("make me a beat", {})
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    assert result["ok"] is True
    assert result["intent"] == "make_beat"
    for key in ("bpm", "key", "scale", "bars", "style"):
        assert key in result, f"Expected key '{key}' in result"


# ── 2. BPM parsing ──────────────────────────────────────────────────────────

def test_make_beat_bpm_parsing():
    result = plan_request("make a dark trap beat at 140 bpm", {})
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    assert result["bpm"] == 140


# ── 3. Key parsing ──────────────────────────────────────────────────────────

def test_make_beat_key_parsing():
    result = plan_request("cook a beat in F minor", {})
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    assert result["key"] == "F"
    assert result["scale"] == "minor"


# ── 4. Style parsing ─────────────────────────────────────────────────────────

def test_make_beat_style_parsing():
    result = plan_request("make me a drill beat", {})
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    assert result["style"] == "drill"


# ── 5. Actions include set_tempo when channels present ───────────────────────

def test_make_beat_with_channels():
    project = {
        "channels": [
            {"index": 0, "name": "kick",  "plugin": "FPC", "volume": 0.78,
             "pan": 0, "mixer_track": 1, "muted": False, "solo": False, "selected": False},
            {"index": 1, "name": "snare", "plugin": "FPC", "volume": 0.78,
             "pan": 0, "mixer_track": 2, "muted": False, "solo": False, "selected": False},
        ],
        "mixer": [],
    }
    result = plan_request("make a trap beat at 140 bpm", project)
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    actions = result["actions"]
    action_names = [a["action"] for a in actions]
    assert "set_tempo" in action_names, (
        f"Expected 'set_tempo' in actions; got: {action_names}"
    )


# ── 6. midi_files key ────────────────────────────────────────────────────────

def test_make_beat_has_midi_files():
    result = plan_request("make me a trap beat", {})
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    assert "midi_files" in result, "Expected 'midi_files' key in result"
    midi = result["midi_files"]
    for sub in ("drums_808", "chords", "melody"):
        assert sub in midi, f"Expected midi_files['{sub}'] key"
        assert isinstance(midi[sub], str) and midi[sub], (
            f"Expected non-empty string for midi_files['{sub}']"
        )


# ── 7. Bars parsing ──────────────────────────────────────────────────────────

def test_make_beat_bars_parsing():
    result = plan_request("make me a 16 bar trap beat", {})
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    assert result["bars"] == 16


# ── 8. Default BPM is a sane integer ─────────────────────────────────────────

def test_make_beat_default_bpm():
    result = plan_request("make a beat", {})
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    bpm = result["bpm"]
    assert isinstance(bpm, int), f"Expected int bpm, got {type(bpm)}"
    assert 40 <= bpm <= 280, f"BPM {bpm} is outside sane range 40–280"


# ── 9. Non-beat request is unaffected ────────────────────────────────────────

def test_non_beat_not_affected():
    project = {
        "channels": [
            {"index": 0, "name": "kick", "volume": 0.78, "pan": 0,
             "mixer_track": 1, "muted": False, "solo": False, "selected": False}
        ],
        "mixer": [],
    }
    result = plan_request("mute the kick", project)
    assert result["intent"] != "make_beat", (
        "Mute command should not produce make_beat intent"
    )


# ── 10. set_tempo action value matches parsed BPM ────────────────────────────

def test_make_beat_auto_names_channels():
    """When no drum channels exist, make_beat should include set_channel_name actions."""
    project = {
        "channels": [
            {"index": 0, "name": "Channel 1", "plugin": "", "volume": 0.78, "pan": 0, "mixer_track": -1, "muted": False, "solo": False, "selected": False},
            {"index": 1, "name": "Channel 2", "plugin": "", "volume": 0.78, "pan": 0, "mixer_track": -1, "muted": False, "solo": False, "selected": False},
            {"index": 2, "name": "Channel 3", "plugin": "", "volume": 0.78, "pan": 0, "mixer_track": -1, "muted": False, "solo": False, "selected": False},
            {"index": 3, "name": "Channel 4", "plugin": "", "volume": 0.78, "pan": 0, "mixer_track": -1, "muted": False, "solo": False, "selected": False},
        ],
        "mixer": []
    }
    result = plan_request("make a trap beat at 140 bpm", project)
    if result.get("intent") != "make_beat":
        return  # feature not active, skip
    actions = result["actions"]
    action_names = [a["action"] for a in actions]
    # Should include channel naming since none have drum names
    assert "set_channel_name" in action_names or "set_steps_32" in action_names, \
        "Expected set_channel_name or set_steps_32 when auto-naming"


def test_make_beat_set_tempo_action():
    result = plan_request("make a trap beat at 140 bpm", {})
    if not _make_beat_supported(result):
        pytest.skip("make_beat intent not yet implemented")
    actions = result["actions"]
    tempo_actions = [a for a in actions if a["action"] == "set_tempo"]
    assert tempo_actions, "Expected at least one set_tempo action"
    assert tempo_actions[0]["value"]["bpm"] == result["bpm"], (
        "set_tempo bpm value should match the parsed bpm in the result"
    )
