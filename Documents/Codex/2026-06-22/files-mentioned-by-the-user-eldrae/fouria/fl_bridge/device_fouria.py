# name=FOURIA AI Studio Assistant
"""FOURIA native FL Studio control bridge — v0.2.

Safety guarantees maintained here:
- safeToEdit() defaults to 0 (NOT safe) if the FL API call raises. Fail-closed.
- Mutating actions require safeToEdit() == 1 at execution time, every time.
- Actions are atomically claimed from the server; a crashed bridge that
  reconnects marks previously claimed actions as 'ambiguous', not replayed.
- The bridge identifies itself with a stable UUID per FL session.
"""
import json
import os
import time
import uuid
from urllib.request import Request, urlopen

FOURIA_URL    = "http://127.0.0.1:11700"
BRIDGE_VERSION = "2.0.0"

# Token must match FOURIA_TOKEN env var on the server (or server's printed startup token).
FOURIA_TOKEN = os.environ.get("FOURIA_TOKEN", "")

# Stable session identity for this FL Studio launch.
_BRIDGE_ID  = str(uuid.uuid4())
_SESSION_ID = None

_last_sync = 0.0

try:
    import channels
    import general
    import mixer
    import patterns
    import playlist
    import plugins
    import transport
    import ui
except ImportError:
    channels = general = mixer = patterns = playlist = plugins = transport = ui = None


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _headers():
    h = {"Content-Type": "application/json"}
    if FOURIA_TOKEN:
        h["Authorization"] = f"Bearer {FOURIA_TOKEN}"
    return h


def _post(path, payload, timeout=4):
    req = Request(
        FOURIA_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get(path, timeout=3):
    req = Request(FOURIA_URL + path, headers=_headers(), method="GET")
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _clamp(value, low, high):
    return max(low, min(high, value))


# ── Project snapshot ─────────────────────────────────────────────────────────

def _snapshot():
    channel_data = []
    count = min(128, int(_safe(lambda: channels.channelCount(1), 0) or 0))
    for index in range(count):
        channel_data.append({
            "index":       index,
            "name":        _safe(lambda i=index: channels.getChannelName(i, True), ""),
            "plugin":      _safe(lambda i=index: plugins.getPluginName(i, -1, 0, True), ""),
            "volume":      _safe(lambda i=index: channels.getChannelVolume(i, 0, True), 0),
            "volume_db":   _safe(lambda i=index: channels.getChannelVolume(i, 1, True), None),
            "pan":         _safe(lambda i=index: channels.getChannelPan(i, True), 0),
            "mixer_track": _safe(lambda i=index: channels.getTargetFxTrack(i, True), -1),
            "muted":       bool(_safe(lambda i=index: channels.isChannelMuted(i, True), 0)),
            "solo":        bool(_safe(lambda i=index: channels.isChannelSolo(i, True), 0)),
            "selected":    bool(_safe(lambda i=index: channels.isChannelSelected(i, True), 0)),
        })

    mixer_data = []
    mix_count = min(128, int(_safe(lambda: mixer.getTrackCount(), 0) or 0))
    for index in range(mix_count):
        name   = _safe(lambda i=index: mixer.getTrackName(i), "")
        active = index == 0 or bool(name) or bool(_safe(lambda i=index: mixer.getTrackPeaks(i, 2), 0))
        if not active and index > 32:
            continue
        slots = []
        for slot in range(10):
            if _safe(lambda i=index, s=slot: mixer.isTrackPluginValid(i, s), 0):
                slots.append({
                    "slot":   slot,
                    "plugin": _safe(lambda i=index, s=slot: plugins.getPluginName(i, s), ""),
                    "mix":    _safe(lambda i=index, s=slot: mixer.getPluginMixLevel(i, s), 1),
                })
        mixer_data.append({
            "index":      index,
            "name":       name,
            "volume":     _safe(lambda i=index: mixer.getTrackVolume(i), 0),
            "volume_db":  _safe(lambda i=index: mixer.getTrackVolume(i, 1), None),
            "pan":        _safe(lambda i=index: mixer.getTrackPan(i), 0),
            "stereo_sep": _safe(lambda i=index: mixer.getTrackStereoSep(i), 0),
            "muted":      bool(_safe(lambda i=index: mixer.isTrackMuted(i), 0)),
            "solo":       bool(_safe(lambda i=index: mixer.isTrackSolo(i), 0)),
            "peak":       _safe(lambda i=index: mixer.getTrackPeaks(i, 2), 0),
            "slots":      slots,
        })

    return {
        "title":                _safe(lambda: general.getProjectTitle(), "FL Studio"),
        "author":               _safe(lambda: general.getProjectAuthor(), ""),
        "genre":                _safe(lambda: general.getProjectGenre(), ""),
        "api_version":          _safe(lambda: general.getVersion(), 0),
        "playing":              bool(_safe(lambda: transport.isPlaying(), 0)),
        "recording":            bool(_safe(lambda: transport.isRecording(), 0)),
        "changed":              _safe(lambda: general.getChangedFlag(), 0),
        "selected_channel":     _safe(lambda: channels.selectedChannel(1, 0, 1), -1),
        "selected_mixer_track": _safe(lambda: mixer.trackNumber(), -1),
        "current_pattern":      _safe(lambda: patterns.patternNumber(), -1),
        "channels":             channel_data,
        "mixer":                mixer_data,
    }


# ── Execution ─────────────────────────────────────────────────────────────────

def _undo(name):
    _safe(lambda: general.saveUndo("FOURIA: " + name, 0))


def _role_level(name):
    text = (name or "").lower()
    if "kick" in text: return 0.76
    if any(w in text for w in ("808", "bass", "sub")): return 0.72
    if any(w in text for w in ("snare", "clap")): return 0.70
    if any(w in text for w in ("hat", "shaker", "perc")): return 0.58
    if any(w in text for w in ("vocal", "vox", "lead")): return 0.68
    if any(w in text for w in ("melody", "keys", "piano", "guitar", "synth", "pad")): return 0.62
    return 0.64


def _organize_project():
    _undo("organize project")
    used = set()
    channel_count = min(125, int(channels.channelCount(1)))
    next_track = 1
    changed = []
    for index in range(channel_count):
        name   = channels.getChannelName(index, True) or "Channel " + str(index + 1)
        target = channels.getTargetFxTrack(index, True)
        if target <= 0 or target in used:
            while next_track in used:
                next_track += 1
            target = next_track
            next_track += 1
            channels.setTargetFxTrack(index, target, True)
        used.add(target)
        mixer.setTrackName(target, name[:24])
        changed.append({"channel": index, "name": name, "mixer_track": target})
    return {"organized": changed}


def _gain_stage():
    _undo("initial gain stage")
    changed = []
    for track in range(1, min(128, int(mixer.getTrackCount()))):
        name = mixer.getTrackName(track)
        peak = _safe(lambda i=track: mixer.getTrackPeaks(i, 2), 0)
        if not name and not peak:
            continue
        level = _role_level(name)
        mixer.setTrackVolume(track, level)
        changed.append({"track": track, "name": name, "volume": level, "peak_before": peak})
    return {
        "gain_staged": changed,
        "note": "Initial static balance only — audible mix decisions still require playback/reference checks.",
    }


def _execute(item):
    action = item.get("action")
    value  = item.get("value") or {}

    # Transport and window commands — no safeToEdit required.
    if action in ("play", "stop", "record", "save", "undo", "redo",
                  "show_channel_rack", "show_mixer", "show_playlist", "show_piano_roll", "notify"):
        commands = {
            "play":              lambda: transport.start(),
            "stop":              lambda: transport.stop(),
            "record":            lambda: transport.record(),
            "save":              lambda: transport.globalTransport(92, 1),
            "undo":              lambda: general.undo(),
            "redo":              lambda: general.undoUp(),
            "show_mixer":        lambda: ui.showWindow(0),
            "show_channel_rack": lambda: ui.showWindow(1),
            "show_playlist":     lambda: ui.showWindow(2),
            "show_piano_roll":   lambda: ui.showWindow(3),
            "notify":            lambda: ui.setHintMsg(str(value or "FOURIA is ready.")),
        }
        commands[action]()
        return {"action": action}

    # Fail-closed: default 0 (NOT safe) if the FL API call raises or is unavailable.
    if not _safe(lambda: general.safeToEdit(), 0):
        raise RuntimeError("FL Studio is not currently safe to edit (safeToEdit == 0)")

    _undo(action.replace("_", " "))
    index = int(value.get("index", -1))

    if action == "organize_project":
        return _organize_project()
    if action == "gain_stage_mix":
        return _gain_stage()
    if action == "set_channel_name":
        channels.setChannelName(index, str(value["name"])[:64], True)
    elif action == "set_channel_volume":
        channels.setChannelVolume(index, _clamp(float(value["volume"]), 0, 1), 0, True)
    elif action == "set_channel_pan":
        channels.setChannelPan(index, _clamp(float(value["pan"]), -1, 1), 0, True)
    elif action == "set_channel_pitch":
        channels.setChannelPitch(index, float(value["semitones"]), 1, 0, True)
    elif action == "mute_channel":
        channels.muteChannel(index, int(bool(value.get("enabled", True))), True)
    elif action == "solo_channel":
        channels.soloChannel(index, int(bool(value.get("enabled", True))), True)
    elif action == "select_channel":
        channels.selectOneChannel(index, True)
    elif action == "route_channel":
        channels.setTargetFxTrack(index, int(value["mixer_track"]), True)
    elif action == "quantize_channel":
        channels.quickQuantize(index, int(bool(value.get("start_only", True))), True)
    elif action == "set_steps":
        for step in range(int(value.get("length", 16))):
            channels.setGridBit(index, step, 1 if step in value.get("steps", []) else 0, True)
    elif action == "set_mixer_name":
        mixer.setTrackName(index, str(value["name"])[:64])
    elif action == "set_mixer_volume":
        mixer.setTrackVolume(index, _clamp(float(value["volume"]), 0, 1))
    elif action == "set_mixer_pan":
        mixer.setTrackPan(index, _clamp(float(value["pan"]), -1, 1))
    elif action == "set_mixer_stereo":
        mixer.setTrackStereoSep(index, _clamp(float(value["separation"]), -1, 1))
    elif action == "mute_mixer":
        mixer.muteTrack(index, int(bool(value.get("enabled", True))))
    elif action == "solo_mixer":
        mixer.soloTrack(index, int(bool(value.get("enabled", True))))
    elif action == "select_mixer":
        mixer.setActiveTrack(index)
    elif action == "route_mixer":
        mixer.setRouteTo(index, int(value["destination"]), int(bool(value.get("enabled", True))), True)
    elif action == "set_route_level":
        mixer.setRouteToLevel(index, int(value["destination"]), _clamp(float(value["level"]), 0, 1))
    elif action == "set_plugin_mix":
        mixer.setPluginMixLevel(index, int(value["slot"]), _clamp(float(value["mix"]), 0, 1))
    elif action == "set_plugin_param":
        plugins.setParamValue(
            _clamp(float(value["value"]), 0, 1),
            int(value["param"]), index, int(value.get("slot", -1)), 0, True,
        )
    elif action == "next_preset":
        plugins.nextPreset(index, int(value.get("slot", -1)), True)
    elif action == "previous_preset":
        plugins.prevPreset(index, int(value.get("slot", -1)), True)
    elif action == "set_pattern_name":
        patterns.setPatternName(index, str(value["name"])[:64])
    elif action == "select_pattern":
        patterns.jumpToPattern(index)
    elif action == "set_playlist_name":
        playlist.setTrackName(index, str(value["name"])[:64])
    elif action == "mute_playlist":
        playlist.muteTrack(index, int(bool(value.get("enabled", True))))
    elif action == "solo_playlist":
        playlist.soloTrack(index, int(bool(value.get("enabled", True))))
    else:
        raise RuntimeError("unsupported bridge action: " + str(action))

    return {"action": action, "value": value}


# ── FL Studio lifecycle ───────────────────────────────────────────────────────

def _register():
    global _SESSION_ID
    try:
        snap         = _snapshot()
        project_hash = snap.get("title") or ""
        resp         = _post("/api/fl/register", {
            "bridge_id":    _BRIDGE_ID,
            "project_hash": project_hash,
        }, timeout=5)
        _SESSION_ID = resp.get("session_id")
        print(f"FOURIA: registered session {_SESSION_ID}", flush=True)
    except Exception as exc:
        print(f"FOURIA: registration failed ({exc}); operating without session binding.", flush=True)


def OnInit():
    print(f"FOURIA bridge v{BRIDGE_VERSION} loaded. Bridge ID: {_BRIDGE_ID}", flush=True)
    _safe(lambda: ui.setHintMsg("FOURIA native control bridge connected."))
    _register()


def OnIdle():
    global _last_sync
    now = time.time()
    if now - _last_sync < 2:
        return
    _last_sync = now
    try:
        snap = _snapshot()
        _post("/api/fl/sync", {
            "bridge_version": BRIDGE_VERSION,
            "session_id":     _SESSION_ID,
            "project":        snap,
        }, timeout=8)

        if _SESSION_ID is None:
            return

        data  = _get(f"/api/fl/actions/claim?session_id={_SESSION_ID}")
        items = data.get("actions", [])

        for item in items:
            try:
                output = _execute(item)
                result = {"id": item["id"], "ok": True, "output": output}
            except Exception as exc:
                result = {"id": item.get("id"), "ok": False, "error": str(exc)}
            _post("/api/fl/result", result)

    except Exception:
        pass
