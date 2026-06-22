"""Unit tests for production_agent.plan_request()."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
from production_agent import plan_request, _pan_value


FAKE_PROJECT = {
    "channels": [
        {"index": 0, "name": "Kick"},
        {"index": 1, "name": "808"},
        {"index": 2, "name": "Hats"},
        {"index": 3, "name": "Vocal"},
    ],
    "mixer": [
        {"index": 1, "name": "Kick"},
        {"index": 2, "name": "808"},
        {"index": 3, "name": "Vocal"},
        {"index": 4, "name": "Hats"},
    ],
}

# pan value helper
def test_pan_hard_right():    assert _pan_value("pan hard right") == 1.0
def test_pan_hard_left():     assert _pan_value("pan hard left") == -1.0
def test_pan_slightly_right():assert _pan_value("pan slightly right") == 0.15
def test_pan_slightly_left(): assert _pan_value("pan slightly left") == -0.15
def test_pan_default_right(): assert _pan_value("pan right") == 0.35
def test_pan_default_left():  assert _pan_value("pan left") == -0.35

# organize + named track coexist
def test_organize_and_named_track_coexist():
    result = plan_request("organize my project and mute the kick", FAKE_PROJECT)
    names = [a["action"] for a in result["actions"]]
    assert "organize_project" in names
    assert "mute_channel" in names

def test_gain_stage_independent():
    result = plan_request("gain stage the mix", FAKE_PROJECT)
    assert any(a["action"] == "gain_stage_mix" for a in result["actions"])

# named track resolution
def test_mute_mixer_track():
    result = plan_request("mute the vocal", FAKE_PROJECT)
    acts = [a for a in result["actions"] if a["action"] == "mute_mixer"]
    assert acts and acts[0]["value"]["index"] == 3

def test_solo_mixer_track():
    result = plan_request("solo the 808", FAKE_PROJECT)
    acts = [a for a in result["actions"] if a["action"] == "solo_mixer"]
    assert acts and acts[0]["value"]["index"] == 2

def test_pan_mixer_track_hard_right():
    result = plan_request("pan the hats hard right", FAKE_PROJECT)
    acts = [a for a in result["actions"] if a["action"] == "set_mixer_pan"]
    assert acts and acts[0]["value"]["pan"] == 1.0

def test_pan_mixer_track_center():
    result = plan_request("pan the kick center", FAKE_PROJECT)
    acts = [a for a in result["actions"] if a["action"] == "set_mixer_pan"]
    assert acts and acts[0]["value"]["pan"] == 0.0

def test_set_mixer_volume_percent():
    result = plan_request("set the vocal level to 70%", FAKE_PROJECT)
    acts = [a for a in result["actions"] if a["action"] == "set_mixer_volume"]
    assert acts and abs(acts[0]["value"]["volume"] - 0.70) < 0.001

def test_quantize_channel():
    result = plan_request("quantize the hats", FAKE_PROJECT)
    acts = [a for a in result["actions"] if a["action"] == "quantize_channel"]
    assert acts and acts[0]["value"]["index"] == 2

def test_mute_channel():
    result = plan_request("mute the kick channel", FAKE_PROJECT)
    acts = [a for a in result["actions"] if a["action"] == "mute_channel"]
    assert acts and acts[0]["value"]["index"] == 0

# window commands
def test_open_mixer_window():
    assert any(a["action"] == "show_mixer" for a in plan_request("open mixer", {})["actions"])

def test_open_piano_roll_window():
    assert any(a["action"] == "show_piano_roll" for a in plan_request("open piano roll", {})["actions"])

# empty / unknown
def test_unknown_request_returns_ok():
    r = plan_request("what key should I use?", FAKE_PROJECT)
    assert r["ok"] is True and r["actions"] == []

def test_empty_string():
    r = plan_request("", {})
    assert r["ok"] is True
