"""Tests for new bridge actions: set_tempo, load_sample, set_steps_32.

Mirrors the stub pattern from test_safety.py — a fresh bridge is loaded
for each test with a minimal FL Studio API surface stubbed out.
"""
import sys
import types
import importlib
import pytest
from pathlib import Path


# ── FL Studio stub helpers ────────────────────────────────────────────────────

def _stub(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


def _load_bridge_extended(safe_to_edit_value=1):
    """Load device_fouria with stubs that include new action methods."""
    sys.modules.pop("device_fouria_extended", None)

    ch = _stub("channels")
    ch.channelCount             = lambda *a: 0
    ch.getChannelName           = lambda *a: ""
    ch.getChannelVolume         = lambda *a: 0
    ch.getChannelPan            = lambda *a: 0
    ch.getTargetFxTrack         = lambda *a: -1
    ch.isChannelMuted           = lambda *a: 0
    ch.isChannelSolo            = lambda *a: 0
    ch.isChannelSelected        = lambda *a: 0
    ch.selectedChannel          = lambda *a: -1
    ch.muteChannel              = lambda *a: None
    ch.soloChannel              = lambda *a: None
    ch.setChannelName           = lambda *a: None
    ch.setChannelVolume         = lambda *a: None
    ch.setChannelPan            = lambda *a: None
    ch.setChannelPitch          = lambda *a: None
    ch.selectOneChannel         = lambda *a: None
    ch.setTargetFxTrack         = lambda *a: None
    ch.quickQuantize            = lambda *a: None
    ch.setGridBit               = lambda *a: None
    # New stubs required by additional bridge actions
    ch.setChannelSampleFile     = lambda *a: None
    ch.setStepParameterByIndex  = lambda *a: None
    ch.setChannelColor          = lambda *a: None

    mx = _stub("mixer")
    mx.getTrackCount     = lambda *a: 0
    mx.getTrackName      = lambda *a: ""
    mx.getTrackVolume    = lambda *a: 0
    mx.getTrackPan       = lambda *a: 0
    mx.getTrackStereoSep = lambda *a: 0
    mx.isTrackMuted      = lambda *a: 0
    mx.isTrackSolo       = lambda *a: 0
    mx.getTrackPeaks     = lambda *a: 0
    mx.isTrackPluginValid= lambda *a: False
    mx.trackNumber       = lambda *a: -1

    for n in ("general", "patterns", "playlist", "plugins", "transport", "ui"):
        _stub(n)

    g = sys.modules["general"]
    g.getProjectTitle   = lambda *a: "Bridge Test"
    g.getProjectAuthor  = lambda *a: ""
    g.getProjectGenre   = lambda *a: ""
    g.getVersion        = lambda *a: 21
    g.saveUndo          = lambda *a: None
    g.getChangedFlag    = lambda *a: 0
    g.undo              = lambda *a: None
    g.undoUp            = lambda *a: None
    # New stub for set_tempo
    g.setProjectTempo   = lambda *a: None
    g.safeToEdit        = lambda *a: safe_to_edit_value

    t = sys.modules["transport"]
    t.start = t.stop = t.record = lambda *a: None
    t.globalTransport = lambda *a: None
    t.isPlaying   = lambda *a: 0
    t.isRecording = lambda *a: 0

    p = sys.modules["patterns"]
    p.patternNumber  = lambda *a: -1
    p.setPatternName = p.jumpToPattern = lambda *a: None

    pl = sys.modules["playlist"]
    pl.setTrackName = pl.muteTrack = pl.soloTrack = lambda *a: None

    pk = sys.modules["plugins"]
    pk.getPluginName = lambda *a: ""
    pk.setParamValue = pk.nextPreset = pk.prevPreset = lambda *a: None

    ui = sys.modules["ui"]
    ui.showWindow = ui.setHintMsg = lambda *a: None

    bridge_path = Path(__file__).parent.parent / "fl_bridge" / "device_fouria.py"
    spec   = importlib.util.spec_from_file_location("device_fouria_extended", bridge_path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    return bridge


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_set_tempo_executes():
    """set_tempo with a valid BPM returns the expected result dict."""
    bridge = _load_bridge_extended()
    result = bridge._execute({"action": "set_tempo", "value": {"bpm": 140}})
    assert result["action"] == "set_tempo"


def test_set_tempo_clamped():
    """set_tempo with an out-of-range BPM clamps rather than raising."""
    bridge = _load_bridge_extended()
    # Should not raise — bridge is expected to clamp to max 280
    result = bridge._execute({"action": "set_tempo", "value": {"bpm": 999}})
    assert result["action"] == "set_tempo"


def test_load_sample_executes():
    """load_sample with a valid index and path does not raise."""
    bridge = _load_bridge_extended()
    result = bridge._execute({
        "action": "load_sample",
        "value": {"index": 0, "path": "C:/test.wav"},
    })
    assert isinstance(result, dict)


def test_set_steps_32_executes():
    """set_steps_32 with a typical kick pattern does not raise."""
    bridge = _load_bridge_extended()
    result = bridge._execute({
        "action": "set_steps_32",
        "value": {"index": 0, "steps": [0, 4, 8, 12], "length": 16},
    })
    assert isinstance(result, dict)


def test_set_steps_32_empty_pattern():
    """set_steps_32 with an empty steps list (silence) does not raise."""
    bridge = _load_bridge_extended()
    result = bridge._execute({
        "action": "set_steps_32",
        "value": {"index": 0, "steps": [], "length": 16},
    })
    assert isinstance(result, dict)
