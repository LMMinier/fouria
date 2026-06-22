"""Unit tests for context_injector.build_project_context()."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
from context_injector import build_project_context

SAMPLE_STATE = {
    "project": {
        "title": "Dark Trap Beat", "author": "Producer", "genre": "Trap", "playing": False,
        "channels": [
            {"index": 0, "name": "Kick",  "plugin": "FPC",   "volume": 0.78, "volume_db": -4.2,
             "pan": 0.0,  "mixer_track": 1, "muted": False, "solo": False, "selected": False},
            {"index": 1, "name": "808",   "plugin": "3xOSC", "volume": 0.70, "volume_db": -6.0,
             "pan": 0.0,  "mixer_track": 2, "muted": False, "solo": False, "selected": False},
            {"index": 2, "name": "Hats",  "plugin": "FPC",   "volume": 0.55, "volume_db": -9.0,
             "pan": 0.15, "mixer_track": 3, "muted": True,  "solo": False, "selected": False},
        ],
        "mixer": [
            {"index": 1, "name": "Kick", "volume": 0.78, "volume_db": -4.2, "pan": 0.0,
             "stereo_sep": 0, "muted": False, "solo": False, "peak": 0.812, "slots": []},
            {"index": 2, "name": "808",  "volume": 0.70, "volume_db": -6.0, "pan": 0.0,
             "stereo_sep": 0, "muted": False, "solo": False, "peak": 0.620,
             "slots": [{"slot": 0, "plugin": "Parametric EQ 2", "mix": 1.0}]},
            {"index": 3, "name": "Hats", "volume": 0.55, "volume_db": -9.0, "pan": 0.15,
             "stereo_sep": 0, "muted": True,  "solo": False, "peak": 0.0,   "slots": []},
        ],
    }
}

def test_returns_nonempty():          assert build_project_context(SAMPLE_STATE).strip() != ""
def test_title():                     assert "Dark Trap Beat" in build_project_context(SAMPLE_STATE)
def test_channel_names():             ctx = build_project_context(SAMPLE_STATE); assert "Kick" in ctx and "808" in ctx
def test_muted_flag():                assert "MUTED" in build_project_context(SAMPLE_STATE)
def test_mixer_fx():                  assert "Parametric EQ 2" in build_project_context(SAMPLE_STATE)
def test_empty_state():               assert build_project_context({}) == ""
def test_empty_project():             assert build_project_context({"project": {}}) == ""
def test_pan_right_shows_r():         assert "R15" in build_project_context(SAMPLE_STATE)
