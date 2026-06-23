import re
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


def _resolve_named(items, phrase):
    phrase = phrase.lower()
    matches = []
    for item in items:
        name = str(item.get("name", "")).strip()
        if name and name.lower() in phrase:
            matches.append(item)
    return max(matches, key=lambda item: len(str(item.get("name", ""))), default=None)


def _pan_value(phrase):
    """Return a pan float from phrase modifiers."""
    if any(w in phrase for w in ("hard", "full", "100%", "all the way")):
        return 1.0 if "right" in phrase else -1.0
    if any(w in phrase for w in ("slightly", "a bit", "little", "subtle", "gently")):
        return 0.15 if "right" in phrase else -0.15
    if any(w in phrase for w in ("moderate", "medium", "halfway")):
        return 0.6 if "right" in phrase else -0.6
    # default moderate push
    return 0.35 if "right" in phrase else -0.35


_BEAT_TRIGGERS = (
    "make a beat", "make me a beat", "make beat", "build a beat",
    "create a beat", "cook a beat", "generate a beat",
    # also catch "make me a dark trap beat", "make a hard beat", etc.
    "make me a", "make a",
)

# Require "beat" somewhere in phrase when using the broad triggers
_BROAD_BEAT_TRIGGERS = {"make me a", "make a"}



def _parse_beat_params(phrase):
    """Extract BPM, key, scale, bars, style from a phrase."""
    # BPM
    bpm = 140
    m = re.search(r"(\d{2,3})\s*(?:bpm|tempo)", phrase)
    if not m:
        m = re.search(r"at\s+(\d{2,3})\b", phrase)
    if m:
        bpm = max(40, min(280, int(m.group(1))))

    # Key
    key = "F"
    m = re.search(r"(?:in|key of)\s+([A-Ga-g][#b]?)\b", phrase)
    if m:
        key = m.group(1).upper().replace("b", "b")  # keep lowercase b for flats

    # Scale
    scale = "minor"
    if "harmonic minor" in phrase:
        scale = "harmonic_minor"
    elif "phrygian" in phrase:
        scale = "phrygian"
    elif "major" in phrase and "minor" not in phrase:
        scale = "major"
    elif "minor" in phrase:
        scale = "minor"

    # Bars
    bars = 8
    m = re.search(r"(\d+)\s*bar", phrase)
    if m:
        bars = max(1, min(64, int(m.group(1))))

    # Style
    style = "trap"
    for s in ("drill", "lo-fi", "lofi", "boom bap", "afrobeats", "trap"):
        if s in phrase:
            style = s
            break

    return bpm, key, scale, bars, style


def _find_channel(channels, *keywords):
    """Return first channel whose name contains any keyword (case-insensitive)."""
    for ch in channels:
        name = str(ch.get("name", "")).lower()
        if any(kw in name for kw in keywords):
            return ch
    return None


def _make_beat(phrase, channels, notes):
    """Build the list of FL actions for the make_beat intent."""
    from midi_tools import generate_drum_808_spec, generate_chord_midi_spec, generate_midi_spec

    bpm, key, scale, bars, style = _parse_beat_params(phrase)

    actions = []
    actions.append({"action": "set_tempo", "value": {"bpm": bpm}})
    actions.append({"action": "notify", "value": f"FOURIA beat builder running — {key} {scale} @ {bpm} BPM…"})

    # Drum patterns — 32-step
    DRUM_PATTERNS = {
        "kick":  {"steps": [0, 8, 10, 14], "length": 16},
        "snare": {"steps": [4, 12],        "length": 16},
        "hat":   {"steps": list(range(16)), "length": 16},
        "open":  {"steps": [7, 15],        "length": 32},
    }

    kick_ch   = _find_channel(channels, "kick")
    snare_ch  = _find_channel(channels, "snare")
    hat_ch    = _find_channel(channels, "hat", "hihat", "hi-hat", "hh", "hats")
    open_ch   = _find_channel(channels, "open", "o hat", "open hat")

    if kick_ch:
        actions.append({"action": "set_steps_32", "value": {
            "index": kick_ch["index"], "steps": DRUM_PATTERNS["kick"]["steps"],
            "length": DRUM_PATTERNS["kick"]["length"],
        }})
    else:
        notes.append("No channel named 'Kick' found — rename a channel to 'Kick' for auto-pattern write.")

    if snare_ch:
        actions.append({"action": "set_steps_32", "value": {
            "index": snare_ch["index"], "steps": DRUM_PATTERNS["snare"]["steps"],
            "length": DRUM_PATTERNS["snare"]["length"],
        }})
    else:
        notes.append("No channel named 'Snare' found — rename a channel to 'Snare' for auto-pattern write.")

    if hat_ch:
        actions.append({"action": "set_steps_32", "value": {
            "index": hat_ch["index"], "steps": DRUM_PATTERNS["hat"]["steps"],
            "length": DRUM_PATTERNS["hat"]["length"],
        }})
    else:
        notes.append("No channel named 'Hat'/'Hats'/'HiHat' found — rename for auto-pattern write.")

    if open_ch and open_ch != hat_ch:
        actions.append({"action": "set_steps_32", "value": {
            "index": open_ch["index"], "steps": DRUM_PATTERNS["open"]["steps"],
            "length": DRUM_PATTERNS["open"]["length"],
        }})

    # Generate MIDI files
    try:
        drum_result  = generate_drum_808_spec(key=key, scale=scale, bpm=bpm, bars=bars, style=style)
        chord_result = generate_chord_midi_spec(key=key, scale=scale, bpm=bpm, bars=bars, style=style)
        melody_result = generate_midi_spec(key=key, scale=scale, bpm=bpm, bars=bars, style=style)
    except Exception as exc:
        notes.append(f"MIDI generation error: {exc}")
        drum_result = chord_result = melody_result = {"path": None}

    fl_steps = [
        f"Tempo set to {bpm} BPM.",
        "Drum patterns written to channels named Kick/Snare/Hat.",
        f"Drag {drum_result.get('path')} → drums/808 instrument.",
        f"Drag {chord_result.get('path')} → keys/pad/chord synth.",
        f"Drag {melody_result.get('path')} → lead synth.",
        "Use Piano Roll scale highlight for the key to add your own variations.",
    ]

    return {
        "ok": True,
        "intent": "make_beat",
        "bpm": bpm,
        "key": key,
        "scale": scale,
        "bars": bars,
        "style": style,
        "actions": actions,
        "midi_files": {
            "drums_808": drum_result.get("path"),
            "chords":    chord_result.get("path"),
            "melody":    melody_result.get("path"),
        },
        "notes": notes,
        "fl_steps": fl_steps,
        "requires_fl_bridge": bool(actions),
        "verification": "Check FL Studio channel rack for patterns; verify tempo in transport bar.",
    }


def plan_request(text, project):
    phrase   = " ".join(str(text or "").lower().split())
    channels = project.get("channels") or []
    mixer    = project.get("mixer")    or []
    actions, notes = [], []
    intent = "production_help"

    # ── Beat builder ─────────────────────────────────────────────────────────
    _beat_detected = False
    for t in _BEAT_TRIGGERS:
        if t in phrase:
            # Broad triggers ("make a", "make me a") only fire if "beat" is also in the phrase
            if t in _BROAD_BEAT_TRIGGERS and "beat" not in phrase:
                continue
            _beat_detected = True
            break
    if _beat_detected:
        result = _make_beat(phrase, channels, notes)
        result["request"] = text
        return result

    # ── Global project operations (independent of named-track resolution) ────
    if any(w in phrase for w in ("organize", "route everything", "set up mixer", "clean up project")):
        intent = "organize_project"
        actions.append({"action": "organize_project", "value": {}})
        notes.append("Routes channels to unique mixer inserts and mirrors channel names.")

    if any(w in phrase for w in ("gain stage", "gainstage", "initial mix", "rough mix")):
        intent = "gain_stage_mix"
        actions.append({"action": "gain_stage_mix", "value": {}})
        notes.append("Creates a conservative role-based static balance — not a finished audible mix.")

    # ── Named-track operations ───────────────────────────────────────────────
    mixer_target   = _resolve_named(mixer,    phrase)
    channel_target = _resolve_named(channels, phrase)
    number         = re.search(r"(-?\d+(?:\.\d+)?)\s*%", phrase)

    if mixer_target:
        if "mute" in phrase:
            actions.append({"action": "mute_mixer",
                            "value": {"index": mixer_target["index"], "enabled": True}})
            intent = "mixer_edit"

        if "solo" in phrase:
            actions.append({"action": "solo_mixer",
                            "value": {"index": mixer_target["index"], "enabled": True}})
            intent = "mixer_edit"

        if "pan" in phrase and any(d in phrase for d in ("left", "right", "center", "centre")):
            if "center" in phrase or "centre" in phrase:
                pan = 0.0
            else:
                pan = _pan_value(phrase)
            actions.append({"action": "set_mixer_pan",
                            "value": {"index": mixer_target["index"], "pan": pan}})
            intent = "mixer_edit"

        if number and any(w in phrase for w in ("volume", "level", "fader")):
            actions.append({"action": "set_mixer_volume",
                            "value": {
                                "index":  mixer_target["index"],
                                "volume": max(0.0, min(1.0, float(number.group(1)) / 100)),
                            }})
            intent = "mixer_edit"

    if channel_target:
        if "quantize" in phrase:
            actions.append({"action": "quantize_channel",
                            "value": {"index": channel_target["index"], "start_only": True}})
            intent = "channel_edit"

        if "mute" in phrase:
            actions.append({"action": "mute_channel",
                            "value": {"index": channel_target["index"], "enabled": True}})
            intent = "channel_edit"

        if "solo" in phrase:
            actions.append({"action": "solo_channel",
                            "value": {"index": channel_target["index"], "enabled": True}})
            intent = "channel_edit"

    # ── Window commands (always append if mentioned) ─────────────────────────
    if "open mixer" in phrase:
        actions.append({"action": "show_mixer", "value": {}})
    if "open playlist" in phrase:
        actions.append({"action": "show_playlist", "value": {}})
    if "open piano roll" in phrase:
        actions.append({"action": "show_piano_roll", "value": {}})
    if "open channel rack" in phrase or "open step sequencer" in phrase:
        actions.append({"action": "show_channel_rack", "value": {}})

    return {
        "ok":                True,
        "intent":            intent,
        "request":           text,
        "actions":           actions,
        "notes":             notes,
        "requires_fl_bridge": bool(actions),
        "verification":      "Each native action returns a bridge result and appears in the next project snapshot.",
    }
