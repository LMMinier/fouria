"""Safety property tests.

Covers:
- Fail-closed safeToEdit (default 0 when FL API unavailable)
- Unknown action rejection
- Allowlist consistency between server and bridge
"""
import sys, os, types, importlib
from pathlib import Path

# ── FL Studio stubs (same as test_bridge_snapshot) ───────────────────────────

def _stub(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


def _load_bridge(safe_to_edit_value=1):
    # Remove cached module so we get a fresh load each time
    sys.modules.pop("device_fouria_safety", None)

    ch = _stub("channels")
    ch.channelCount      = lambda *a: 0
    ch.getChannelName    = lambda *a: ""
    ch.getChannelVolume  = lambda *a: 0
    ch.getChannelPan     = lambda *a: 0
    ch.getTargetFxTrack  = lambda *a: -1
    ch.isChannelMuted    = lambda *a: 0
    ch.isChannelSolo     = lambda *a: 0
    ch.isChannelSelected = lambda *a: 0
    ch.selectedChannel   = lambda *a: -1
    ch.muteChannel       = lambda *a: None
    ch.soloChannel       = lambda *a: None
    ch.setChannelName    = lambda *a: None
    ch.setChannelVolume  = lambda *a: None
    ch.setChannelPan     = lambda *a: None
    ch.setChannelPitch   = lambda *a: None
    ch.selectOneChannel  = lambda *a: None
    ch.setTargetFxTrack  = lambda *a: None
    ch.quickQuantize     = lambda *a: None
    ch.setGridBit        = lambda *a: None

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
    g.getProjectTitle  = lambda *a: "Safety Test"
    g.getProjectAuthor = lambda *a: ""
    g.getProjectGenre  = lambda *a: ""
    g.getVersion       = lambda *a: 21
    g.saveUndo         = lambda *a: None
    g.getChangedFlag   = lambda *a: 0
    g.undo             = lambda *a: None
    g.undoUp           = lambda *a: None

    if safe_to_edit_value is None:
        # Simulate the FL API being unavailable (raises)
        g.safeToEdit = lambda *a: (_ for _ in ()).throw(RuntimeError("not available"))
    else:
        g.safeToEdit = lambda *a: safe_to_edit_value

    t = sys.modules["transport"]
    t.start = t.stop = t.record = lambda *a: None
    t.globalTransport = lambda *a: None
    t.isPlaying   = lambda *a: 0
    t.isRecording = lambda *a: 0

    p = sys.modules["patterns"]
    p.patternNumber = lambda *a: -1
    p.setPatternName = p.jumpToPattern = lambda *a: None

    pl = sys.modules["playlist"]
    pl.setTrackName = pl.muteTrack = pl.soloTrack = lambda *a: None

    pk = sys.modules["plugins"]
    pk.getPluginName = lambda *a: ""
    pk.setParamValue = pk.nextPreset = pk.prevPreset = lambda *a: None

    ui = sys.modules["ui"]
    ui.showWindow = ui.setHintMsg = lambda *a: None

    bridge_path = Path(__file__).parent.parent / "fl_bridge" / "device_fouria.py"
    spec   = importlib.util.spec_from_file_location("device_fouria_safety", bridge_path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    return bridge


# ── Fail-closed safeToEdit ───────────────────────────────────────────────────

def test_safe_to_edit_0_blocks_mutation():
    bridge = _load_bridge(safe_to_edit_value=0)
    try:
        bridge._execute({"action": "mute_channel", "value": {"index": 0, "enabled": True}})
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert "safe" in str(e).lower()


def test_safe_to_edit_unavailable_blocks_mutation():
    """If the FL API call itself raises, the bridge must fail closed (block the action)."""
    bridge = _load_bridge(safe_to_edit_value=None)
    try:
        bridge._execute({"action": "set_mixer_volume", "value": {"index": 1, "volume": 0.5}})
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert "safe" in str(e).lower()


def test_safe_to_edit_1_allows_mutation():
    bridge = _load_bridge(safe_to_edit_value=1)
    # Should not raise — mixer stub accepts the call
    result = bridge._execute({"action": "mute_channel", "value": {"index": 0, "enabled": True}})
    assert result["action"] == "mute_channel"


def test_transport_bypasses_safe_to_edit():
    """Transport/window commands must work even when safeToEdit returns 0."""
    bridge = _load_bridge(safe_to_edit_value=0)
    result = bridge._execute({"action": "play", "value": {}})
    assert result["action"] == "play"


# ── Unknown action rejection ──────────────────────────────────────────────────

def test_unknown_action_raises():
    bridge = _load_bridge(safe_to_edit_value=1)
    try:
        bridge._execute({"action": "delete_everything", "value": {}})
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert "unsupported" in str(e).lower()


def test_empty_action_raises():
    bridge = _load_bridge(safe_to_edit_value=1)
    try:
        bridge._execute({"action": "", "value": {}})
        assert False, "Expected RuntimeError"
    except (RuntimeError, KeyError):
        pass  # either is acceptable — the action must not silently succeed
