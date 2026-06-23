import json
import os
import random
import time
from pathlib import Path


ROOT = Path(os.environ.get("FOURIA_ROOT", Path(__file__).resolve().parents[1]))
MIDI_DIR = ROOT / "data" / "midi"

NOTE_BASE = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5,
             "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10,
             "BB": 10, "B": 11}
SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
}
PROGRESSIONS = {
    "minor": [[1, 6, 3, 7], [1, 4, 6, 5], [1, 7, 6, 7], [1, 3, 7, 6]],
    "major": [[1, 5, 6, 4], [1, 4, 5, 4], [6, 4, 1, 5]],
}
ROMAN = {
    "minor": {1: "i", 2: "ii dim", 3: "III", 4: "iv", 5: "v", 6: "VI", 7: "VII"},
    "major": {1: "I", 2: "ii", 3: "iii", 4: "IV", 5: "V", 6: "vi", 7: "vii dim"},
}
DRUM_NOTES = {"kick": 36, "snare": 38, "clap": 39, "closed_hat": 42, "open_hat": 46, "perc": 75}


def _vlq(value: int) -> bytes:
    value = max(0, int(value))
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(out)


def _note_num(name: str, octave: int = 4) -> int:
    n = name.strip().upper().replace("♭", "B").replace("♯", "#")
    return 12 * (octave + 1) + NOTE_BASE.get(n, 0)


def _note_name(num: int) -> str:
    names = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    octave = (num // 12) - 1
    return f"{names[num % 12]}{octave}"


def _degree_notes(key: str, scale: str, degree: int, octave: int = 4) -> list[int]:
    intervals = SCALES.get(scale, SCALES["minor"])
    root = _note_num(key, octave)
    d = degree - 1
    base = root + intervals[d % len(intervals)] + 12 * (d // len(intervals))
    third = root + intervals[(d + 2) % len(intervals)] + 12 * ((d + 2) // len(intervals))
    fifth = root + intervals[(d + 4) % len(intervals)] + 12 * ((d + 4) // len(intervals))
    return [base, third, fifth]


def chord_progression_spec(key: str = "F", scale: str = "minor",
                           bars: int = 8, style: str = "dark trap") -> dict:
    scale = scale.lower().replace(" ", "_")
    if scale not in SCALES:
        scale = "minor"
    bars = max(1, min(64, int(bars)))
    progression = random.choice(PROGRESSIONS.get(scale, PROGRESSIONS["minor"]))
    chords = []
    for bar in range(bars):
        degree = progression[bar % len(progression)]
        notes = _degree_notes(key, scale, degree, octave=3)
        chords.append({
            "bar": bar + 1,
            "degree": degree,
            "roman": ROMAN.get(scale, ROMAN["minor"]).get(degree, str(degree)),
            "notes": [_note_name(n) for n in notes],
            "duration_bars": 1,
            "voicing_tip": "Double the top note one octave up for lift." if (bar + 1) % 4 == 0 else "Keep the voicing tight so the 808 owns the bottom.",
        })
    return {
        "ok": True,
        "type": "chord_progression",
        "key": key,
        "scale": scale,
        "bars": bars,
        "style": style,
        "progression_degrees": progression,
        "chords": chords,
        "fl_steps": [
            f"Open Piano Roll and enable scale highlighting: {key} {scale.replace('_', ' ')}.",
            "Lay one chord per bar, then use Alt+R lightly for velocity variation.",
            "Use a pad, bell, piano, or half-time texture for the chord layer.",
            "Keep notes below C3 sparse if an 808 will follow the root.",
        ],
    }


def _event(delta: int, data: bytes) -> bytes:
    return _vlq(delta) + data


def write_midi(path: Path, bpm: int, events: list[dict], ticks_per_beat: int = 480) -> None:
    tempo = int(60_000_000 / max(30, min(240, bpm)))
    track = bytearray()
    track += _event(0, b"\xff\x51\x03" + tempo.to_bytes(3, "big"))
    last_tick = 0
    note_events = []
    for ev in events:
        note = int(ev["note"])
        start = int(ev["start"])
        dur = int(ev["duration"])
        vel = int(ev.get("velocity", 88))
        note_events.append((start, b"\x90" + bytes([note, vel])))
        note_events.append((start + dur, b"\x80" + bytes([note, 0])))
    note_events.sort(key=lambda x: (x[0], x[1][0]))
    for tick, data in note_events:
        track += _event(tick - last_tick, data)
        last_tick = tick
    track += _event(0, b"\xff\x2f\x00")
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + ticks_per_beat.to_bytes(2, "big")
    body = b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + body)


def generate_midi_spec(key: str = "F", scale: str = "minor", bpm: int = 140,
                       bars: int = 8, style: str = "dark trap") -> dict:
    scale = scale.lower().replace(" ", "_")
    if scale not in SCALES:
        scale = "minor"
    progression = random.choice(PROGRESSIONS.get(scale, PROGRESSIONS["minor"]))
    tpq = 480
    bar_ticks = tpq * 4
    events = []
    chord_names = []
    for bar in range(bars):
        degree = progression[bar % len(progression)]
        chord = _degree_notes(key, scale, degree, octave=3)
        chord_names.append(str(degree))
        start = bar * bar_ticks
        for n in chord:
            events.append({"note": n, "start": start, "duration": bar_ticks, "velocity": 72})
        melody_pool = [(_note_num(key, 5) + i) for i in SCALES[scale]]
        rhythm = [0, 240, 480, 720, 960, 1440]
        for off in rhythm:
            if random.random() < 0.82:
                events.append({
                    "note": random.choice(melody_pool),
                    "start": start + off,
                    "duration": random.choice([180, 240, 360]),
                    "velocity": random.choice([78, 86, 94]),
                })
    stem = f"fouria_{key}_{scale}_{int(time.time())}.mid".replace("#", "sharp")
    path = MIDI_DIR / stem
    write_midi(path, bpm, events, tpq)
    return {
        "ok": True,
        "type": "melody_midi",
        "path": str(path),
        "key": key,
        "scale": scale,
        "bpm": bpm,
        "bars": bars,
        "style": style,
        "progression_degrees": chord_names[:len(progression)],
        "events": events[:80],
        "fl_steps": [
            "Drag the MIDI file into FL Studio.",
            "Put the chord layer on a piano, pad, or bell.",
            "Put the melody notes on a lead or pluck.",
            "Use scale highlighting in the Piano Roll to stay in key.",
            "Humanize velocity and move a few notes slightly off-grid for bounce.",
        ],
    }


def generate_chord_midi_spec(key: str = "F", scale: str = "minor", bpm: int = 140,
                             bars: int = 8, style: str = "trap") -> dict:
    scale = scale.lower().replace(" ", "_")
    if scale not in SCALES:
        scale = "minor"
    bars = max(1, min(64, int(bars)))
    progression = random.choice(PROGRESSIONS.get(scale, PROGRESSIONS["minor"]))
    tpq, bar_ticks = 480, 1920
    events, chords = [], []
    for bar in range(bars):
        degree = progression[bar % len(progression)]
        notes = _degree_notes(key, scale, degree, octave=3)
        for note in notes:
            events.append({"note": note, "start": bar * bar_ticks, "duration": bar_ticks - 30, "velocity": 74})
        chords.append({"bar": bar + 1, "degree": degree, "notes": [_note_name(n) for n in notes]})
    stem = f"fouria_chords_{key}_{scale}_{int(time.time())}.mid".replace("#", "sharp")
    path = MIDI_DIR / stem
    write_midi(path, bpm, events, tpq)
    return {"ok": True, "type": "chord_midi", "path": str(path), "key": key, "scale": scale,
            "bpm": bpm, "bars": bars, "style": style, "chords": chords}


def generate_drum_808_spec(key: str = "F", scale: str = "minor", bpm: int = 140,
                           bars: int = 8, style: str = "trap") -> dict:
    scale = scale.lower().replace(" ", "_")
    if scale not in SCALES:
        scale = "minor"
    bars = max(1, min(64, int(bars)))
    tpq = 480
    bar_ticks = tpq * 4
    step = tpq // 2
    progression = random.choice(PROGRESSIONS.get(scale, PROGRESSIONS["minor"]))
    drum_events = []
    bass_events = []
    pattern = []
    for bar in range(bars):
        start = bar * bar_ticks
        placements = [
            ("kick", 0, 112),
            ("snare", 2 * step, 104),
            ("clap", 2 * step, 88),
            ("kick", random.choice([3, 5, 6]) * step, 104),
            ("closed_hat", 0, 68),
            ("closed_hat", step, 58),
            ("closed_hat", 2 * step, 72),
            ("closed_hat", 3 * step, 56),
            ("closed_hat", 4 * step, 70),
            ("closed_hat", 5 * step, 58),
            ("closed_hat", 6 * step, 74),
            ("closed_hat", 7 * step, 55),
        ]
        if bar % 2 == 1:
            placements.append(("open_hat", 7 * step, 78))
        for lane, off, vel in placements:
            drum_events.append({
                "note": DRUM_NOTES[lane],
                "start": start + off,
                "duration": 90 if "hat" in lane else 180,
                "velocity": vel,
                "lane": lane,
            })
            pattern.append({"bar": bar + 1, "beat": round((off / tpq) + 1, 2), "lane": lane, "velocity": vel})
        degree = progression[bar % len(progression)]
        root = _degree_notes(key, scale, degree, octave=1)[0]
        for off in [0, 3 * step, 6 * step]:
            bass_events.append({
                "note": root,
                "start": start + off,
                "duration": random.choice([step, step + 120, tpq]),
                "velocity": random.choice([96, 108, 118]),
                "lane": "808",
            })
    stem = f"fouria_drums_808_{key}_{scale}_{int(time.time())}.mid".replace("#", "sharp")
    path = MIDI_DIR / stem
    write_midi(path, bpm, drum_events + bass_events, tpq)
    return {
        "ok": True,
        "type": "drums_808_midi",
        "path": str(path),
        "key": key,
        "scale": scale,
        "bpm": bpm,
        "bars": bars,
        "style": style,
        "pattern": pattern[:128],
        "808_notes": [
            {"bar": (ev["start"] // bar_ticks) + 1, "note": _note_name(ev["note"]), "duration_ticks": ev["duration"]}
            for ev in bass_events
        ],
        "fl_steps": [
            "Drag the MIDI into FL Studio, then split drums and 808 to separate instruments if needed.",
            "Route kick and 808 to separate mixer inserts.",
            "Tune the 808 sampler root note and cut polyphony so notes do not overlap unless intended.",
            "Add hat rolls manually around phrase endings; keep the first pass simple and bouncy.",
        ],
    }


def analyze_midi(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "file not found"}
    data = p.read_bytes()
    if not data.startswith(b"MThd"):
        return {"ok": False, "error": "not a standard MIDI file"}
    fmt = int.from_bytes(data[8:10], "big")
    tracks = int.from_bytes(data[10:12], "big")
    tpq = int.from_bytes(data[12:14], "big")
    note_on = data.count(b"\x90")
    return {
        "ok": True,
        "path": str(p),
        "format": fmt,
        "tracks": tracks,
        "ticks_per_beat": tpq,
        "rough_note_on_count": note_on,
        "advice": [
            "If the melody feels robotic, vary note lengths and velocity.",
            "If the beat feels empty, add call-and-response between melody and 808.",
            "If the mix feels muddy, keep low melody notes away from the 808 range.",
        ],
    }
