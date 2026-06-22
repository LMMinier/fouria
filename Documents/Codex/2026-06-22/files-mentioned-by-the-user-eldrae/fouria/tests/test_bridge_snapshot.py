"""Smoke tests for bridge _snapshot() and _execute() using FL Studio stubs.
No real FL Studio installation required.
"""
import sys, os, types, importlib, unittest

def _stub(name):
    m = types.ModuleType(name); sys.modules[name] = m; return m

ch = _stub("channels")
ch.channelCount        = lambda *a: 3
ch.getChannelName      = lambda i, *a: ["Kick","808","Hats"][i] if i < 3 else ""
ch.getChannelVolume    = lambda i, *a: 0.78
ch.getChannelPan       = lambda i, *a: 0.0
ch.getTargetFxTrack    = lambda i, *a: i + 1
ch.isChannelMuted      = lambda i, *a: 0
ch.isChannelSolo       = lambda i, *a: 0
ch.isChannelSelected   = lambda i, *a: 0
ch.muteChannel         = lambda *a: None
ch.soloChannel         = lambda *a: None
ch.setChannelName      = lambda *a: None
ch.setChannelVolume    = lambda *a: None
ch.setChannelPan       = lambda *a: None
ch.setTargetFxTrack    = lambda *a: None
ch.quickQuantize       = lambda *a: None
ch.setGridBit          = lambda *a: None
ch.selectedChannel     = lambda *a: 0
ch.selectOneChannel    = lambda *a: None
ch.setChannelPitch     = lambda *a: None

mx = _stub("mixer")
mx.getTrackCount       = lambda *a: 4
mx.getTrackName        = lambda i, *a: ["","Kick","808","Hats"][i] if i < 4 else ""
mx.getTrackVolume      = lambda i, *a: 0.80
mx.getTrackPan         = lambda i, *a: 0.0
mx.getTrackStereoSep   = lambda i, *a: 0.0
mx.isTrackMuted        = lambda i, *a: 0
mx.isTrackSolo         = lambda i, *a: 0
mx.getTrackPeaks       = lambda i, *a: 0.5
mx.isTrackPluginValid  = lambda i, s, *a: False
mx.setTrackName        = lambda *a: None
mx.setTrackVolume      = lambda *a: None
mx.setTrackPan         = lambda *a: None
mx.setTrackStereoSep   = lambda *a: None
mx.muteTrack           = lambda *a: None
mx.soloTrack           = lambda *a: None
mx.setActiveTrack      = lambda *a: None
mx.setRouteTo          = lambda *a: None
mx.setRouteToLevel     = lambda *a: None
mx.setPluginMixLevel   = lambda *a: None
mx.trackNumber         = lambda *a: 1

for n in ("general","patterns","playlist","plugins","transport","ui"):
    _stub(n)
g = sys.modules["general"]
g.getProjectTitle  = lambda *a: "Test Project"
g.getProjectAuthor = lambda *a: "Tester"
g.getProjectGenre  = lambda *a: "Trap"
g.getVersion       = lambda *a: 21
g.saveUndo         = lambda *a: None
g.getChangedFlag   = lambda *a: 0
g.safeToEdit       = lambda *a: 1
g.undo             = lambda *a: None
g.undoUp           = lambda *a: None
t = sys.modules["transport"]
t.start = t.stop = t.record = lambda *a: None
t.globalTransport  = lambda *a: None
t.isPlaying        = lambda *a: 0
t.isRecording      = lambda *a: 0
p = sys.modules["patterns"]
p.patternNumber    = lambda *a: 1
p.setPatternName   = p.jumpToPattern = lambda *a: None
pl = sys.modules["playlist"]
pl.setTrackName    = pl.muteTrack = pl.soloTrack = lambda *a: None
pk = sys.modules["plugins"]
pk.getPluginName   = lambda *a: "TestPlugin"
pk.setParamValue   = pk.nextPreset = pk.prevPreset = lambda *a: None
ui = sys.modules["ui"]
ui.showWindow      = ui.setHintMsg = lambda *a: None

BRIDGE = os.path.join(os.path.dirname(__file__), "..", "fl_bridge", "device_fouria.py")
spec = importlib.util.spec_from_file_location("device_fouria", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class TestSnapshot(unittest.TestCase):
    def test_has_channels(self):     self.assertIn("channels", bridge._snapshot())
    def test_channel_count(self):    self.assertGreater(len(bridge._snapshot()["channels"]), 0)
    def test_kick_in_channels(self): self.assertIn("Kick", [c["name"] for c in bridge._snapshot()["channels"]])
    def test_has_mixer(self):        self.assertIn("mixer", bridge._snapshot())
    def test_title(self):            self.assertEqual(bridge._snapshot()["title"], "Test Project")

class TestExecute(unittest.TestCase):
    def test_play(self):             self.assertEqual(bridge._execute({"action":"play","value":{}})["action"], "play")
    def test_stop(self):             self.assertEqual(bridge._execute({"action":"stop","value":{}})["action"], "stop")
    def test_show_mixer(self):       self.assertEqual(bridge._execute({"action":"show_mixer","value":{}})["action"], "show_mixer")
    def test_mute_channel(self):     self.assertIn("action", bridge._execute({"action":"mute_channel","value":{"index":0,"enabled":True}}))
    def test_set_mixer_volume(self): self.assertIn("action", bridge._execute({"action":"set_mixer_volume","value":{"index":1,"volume":0.7}}))
    def test_bad_action_raises(self):
        with self.assertRaises(RuntimeError): bridge._execute({"action":"nuke_project","value":{}})

if __name__ == "__main__": unittest.main()
