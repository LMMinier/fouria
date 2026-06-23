import re
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

# ── Synonym / slang expander ─────────────────────────────────────────────────

_SYNONYMS = {
    # beat making
    "cook":         "make",
    "sauté":        "make",
    "whip":         "make",
    "knock":        "beat",
    "banger":       "beat",
    "flip":         "make",
    "vibe":         "beat",
    "type beat":    "beat",
    "pack":         "beat",
    # tempo
    "tempo":        "bpm",
    "speed":        "bpm",
    "rate":         "bpm",
    # volume
    "bump up":      "increase volume",
    "bring up":     "increase volume",
    "push up":      "increase volume",
    "pull back":    "decrease volume",
    "bring down":   "decrease volume",
    "turn up":      "increase volume",
    "turn down":    "decrease volume",
    "louder":       "increase volume",
    "quieter":      "decrease volume",
    "softer":       "decrease volume",
    # mixing
    "muddy":        "low_mid excess",
    "boxy":         "low_mid excess",
    "harsh":        "upper_mid excess",
    "thin":         "low deficit",
    "boomy":        "low excess",
    "bright":       "presence boost",
    "dark":         "high cut",
    "airy":         "air boost",
    # channel operations
    "silence":      "mute",
    "quiet":        "mute",
    "unmute":       "unmute",
    "bring in":     "unmute",
    "isolate":      "solo",
    "hear only":    "solo",
    # general
    "fix":          "organize",
    "clean":        "organize",
    "tidy":         "organize",
    "set up":       "organize",
}


def _normalize(phrase: str) -> str:
    p = phrase.lower()
    for slang, canonical in _SYNONYMS.items():
        p = p.replace(slang, canonical)
    return p

# ── FL Studio default sample finder ─────────────────────────────────────────

_FL_SAMPLE_ROOTS = [
    Path(r"C:\Program Files\Image-Line\FL Studio 21\Data\Patches\Packs"),
    Path(r"C:\Program Files\Image-Line\FL Studio 20\Data\Patches\Packs"),
    Path(os.path.expanduser(r"~\Documents\Image-Line\FL Studio\Samples")),
    Path(os.path.expanduser(r"~\Documents\Image-Line\Data\Patches\Packs")),
]

_ROLE_KEYWORDS = {
    "kick":  ["kick", "bd", "bass drum", "bassdrum"],
    "snare": ["snare", "sd", "rimshot"],
    "hat":   ["hihat", "hi-hat", "hat", "hh", "cymbal"],
    "808":   ["808", "sub bass", "subbass"],
}


def _find_fl_sample(role: str, library_index: dict | None = None) -> str | None:
    """Search FL Studio sample library for a sample matching the role.
    Checks pre-built library index first (fast), then falls back to filesystem search.
    Returns absolute path string or None if not found."""
    # Try library index first (fast, pre-scanned)
    idx = library_index
    if idx is None:
        try:
            from library_index import get_active_index
            idx = get_active_index()
        except Exception:
            idx = {}
    if idx:
        try:
            from library_index import find_sample
            result = find_sample(role, idx)
            if result:
                return result
        except Exception:
            pass
    # Fall back to filesystem search
    keywords = _ROLE_KEYWORDS.get(role, [role])
    for root in _FL_SAMPLE_ROOTS:
        try:
            if not root.exists():
                continue
            for ext in ("*.wav", "*.flac"):
                for sample_path in root.rglob(ext):
                    name_lower = sample_path.stem.lower()
                    if any(kw in name_lower for kw in keywords):
                        return str(sample_path)
        except Exception:
            continue
    return None


def _resolve_named(items, phrase):
    phrase = phrase.lower()
    matches = []
    for item in items:
        name = str(item.get("name", "")).strip()
        if name and name.lower() in phrase:
            matches.append(item)
    return max(matches, key=lambda item: len(str(item.get("name", ""))), default=None)


def _safe_int_match(phrase):
    """Return the first integer found in phrase as a string, or None."""
    m = re.search(r'\b(\d+)\b', phrase)
    return m.group(1) if m else None


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
    # expanded slang triggers (applied after _normalize, but also match raw phrases)
    "cook up", "whip up", "knock me a", "flip me a", "run me a",
    "put together a", "let me hear a", "give me a beat", "drop a beat",
    "make something",
)

# Require "beat" somewhere in phrase when using the broad triggers
_BROAD_BEAT_TRIGGERS = {
    "make me a", "make a",
    "cook up", "whip up", "knock me a", "flip me a", "run me a",
    "put together a", "let me hear a", "make something",
}


def _volume_delta(phrase):
    """Return a volume delta (positive or negative) from phrase."""
    if "increase volume" in phrase or "turn up" in phrase:
        if any(w in phrase for w in ("a lot", "much", "way")):
            return 0.15
        if any(w in phrase for w in ("little", "bit", "slightly", "subtle")):
            return 0.05
        return 0.10
    if "decrease volume" in phrase or "turn down" in phrase:
        if any(w in phrase for w in ("a lot", "much", "way")):
            return -0.15
        if any(w in phrase for w in ("little", "bit", "slightly", "subtle")):
            return -0.05
        return -0.10
    return None



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


# Extended keyword sets for smarter drum channel detection
_KICK_KEYWORDS  = ("kick", "bd", "bass drum", "bassdrum")
_SNARE_KEYWORDS = ("snare", "sd", "rim", "rimshot")
_HAT_KEYWORDS   = ("hat", "hihat", "hi-hat", "hi hat", "hh", "cymbal", "open", "closed")
_808_KEYWORDS   = ("808", "sub bass", "subbass", "sub")


def _make_beat(phrase, channels, notes):
    """Build the list of FL actions for the make_beat intent."""
    from midi_tools import generate_drum_808_spec, generate_chord_midi_spec, generate_midi_spec

    bpm, key, scale, bars, style = _parse_beat_params(phrase)

    actions = []
    # Notify user immediately so they see FOURIA working
    actions.append({"action": "notify", "value": f"FOURIA cooking a {style} beat in {key} {scale} at {bpm} BPM…"})
    actions.append({"action": "set_tempo", "value": {"bpm": bpm}})

    # Drum patterns — 32-step
    DRUM_PATTERNS = {
        "kick":  {"steps": [0, 8, 10, 14], "length": 16},
        "snare": {"steps": [4, 12],        "length": 16},
        "hat":   {"steps": list(range(16)), "length": 16},
        "open":  {"steps": [7, 15],        "length": 32},
    }

    kick_ch   = _find_channel(channels, *_KICK_KEYWORDS)
    snare_ch  = _find_channel(channels, *_SNARE_KEYWORDS)
    hat_ch    = _find_channel(channels, *_HAT_KEYWORDS)
    open_ch   = _find_channel(channels, "open", "o hat", "open hat")

    # Auto-setup: if no recognizable drum channels found, name channels 0-3
    if not kick_ch and not snare_ch and not hat_ch:
        drum_setup = [
            (0, "Kick"),
            (1, "Snare"),
            (2, "Hi-Hat"),
            (3, "808"),
        ]
        for ch_idx, ch_name in drum_setup:
            if any(c["index"] == ch_idx for c in channels):
                actions.append({"action": "set_channel_name", "value": {"index": ch_idx, "name": ch_name}})
        # Try to load default FL samples
        for ch_idx, role in [(0, "kick"), (1, "snare"), (2, "hat"), (3, "808")]:
            if any(c["index"] == ch_idx for c in channels):
                sample = _find_fl_sample(role)
                if sample:
                    actions.append({"action": "load_sample", "value": {"index": ch_idx, "path": sample}})
                    notes.append(f"Loaded {role} sample: {Path(sample).name}")
        # Write step patterns to indices 0-3
        actions.append({"action": "set_steps_32", "value": {"index": 0, "steps": [0, 8, 10, 14], "length": 16}})
        actions.append({"action": "set_steps_32", "value": {"index": 1, "steps": [4, 12], "length": 16}})
        actions.append({"action": "set_steps_32", "value": {"index": 2, "steps": list(range(16)), "length": 16}})
        actions.append({"action": "set_steps_32", "value": {"index": 3, "steps": [0, 6, 12], "length": 16}})
        notes.append("Channels 0-3 renamed to Kick/Snare/Hi-Hat/808. Load your preferred samples into them.")
    else:
        if kick_ch:
            actions.append({"action": "set_steps_32", "value": {
                "index": kick_ch["index"], "steps": DRUM_PATTERNS["kick"]["steps"],
                "length": DRUM_PATTERNS["kick"]["length"],
            }})
        else:
            notes.append("No kick channel found — auto-naming skipped because other drum channels exist.")

        if snare_ch:
            actions.append({"action": "set_steps_32", "value": {
                "index": snare_ch["index"], "steps": DRUM_PATTERNS["snare"]["steps"],
                "length": DRUM_PATTERNS["snare"]["length"],
            }})
        else:
            notes.append("No snare channel found.")

        if hat_ch:
            actions.append({"action": "set_steps_32", "value": {
                "index": hat_ch["index"], "steps": DRUM_PATTERNS["hat"]["steps"],
                "length": DRUM_PATTERNS["hat"]["length"],
            }})
        else:
            notes.append("No hat channel found.")

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
    raw_phrase = " ".join(str(text or "").lower().split())
    phrase     = _normalize(raw_phrase)
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

        delta = _volume_delta(phrase)
        if delta is not None and not number:
            current = float(mixer_target.get("volume", 0.75))
            new_vol = max(0.0, min(1.0, current + delta))
            actions.append({"action": "set_mixer_volume",
                            "value": {"index": mixer_target["index"], "volume": new_vol}})
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

    # ── Render / export ──────────────────────────────────────────────────────
    if any(w in phrase for w in ("render", "export", "bounce", "export the song", "mixdown")):
        actions.append({"action": "render", "value": {}})
        notes.append("Opens FL Studio's export dialog. Configure file name and format in the dialog.")
        intent = "render"

    # ── Jump to start ────────────────────────────────────────────────────────
    if any(w in phrase for w in ("go to start", "rewind", "back to start", "beginning")):
        actions.append({"action": "jump_to_start", "value": {}})
        intent = "transport"

    # ── Clone / duplicate pattern ─────────────────────────────────────────────
    if "clone pattern" in phrase or "duplicate pattern" in phrase:
        pat_idx = int(_safe_int_match(phrase) or 0)
        actions.append({"action": "clone_pattern", "value": {"index": pat_idx}})
        intent = "pattern_edit"

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
