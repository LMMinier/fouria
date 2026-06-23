"""Virtual MIDI output — sends notes to FL Studio Piano Roll via loopMIDI or Windows MIDI.

Requires either:
  - loopMIDI installed (https://www.tobias-erichsen.de/software/loopmidi.html)
    which creates a virtual MIDI port named 'loopMIDI Port'
  - OR python-rtmidi: pip install python-rtmidi

Falls back gracefully if neither is available.
"""
from __future__ import annotations
import time
import json
import struct
from pathlib import Path
from typing import Optional


_rtmidi_available = False
_mido_available = False

try:
    import rtmidi
    _rtmidi_available = True
except ImportError:
    pass


def _find_fouria_port(out):
    """Find a loopMIDI or virtual MIDI port to use."""
    ports = out.get_ports()
    # Prefer a port named 'loopMIDI Port' or 'FOURIA'
    for i, name in enumerate(ports):
        if any(kw in name.lower() for kw in ("loopmidi", "fouria", "virtual", "loop")):
            return i, name
    # Fall back to first available port
    if ports:
        return 0, ports[0]
    return None, None


def send_notes_to_piano_roll(events: list[dict], bpm: int = 140) -> dict:
    """Send note events to FL Studio via virtual MIDI port.

    events: list of {"note": int, "start_ticks": int, "duration_ticks": int,
                      "velocity": int, "ticks_per_beat": int}

    Returns {"ok": bool, "method": str, "port": str, "notes_sent": int}
    """
    if not _rtmidi_available:
        return {
            "ok": False,
            "error": "python-rtmidi not installed. Run: pip install python-rtmidi",
            "alternative": "Use the generated .mid file and drag it into FL Studio's Piano Roll.",
        }

    try:
        out = rtmidi.MidiOut()
        port_idx, port_name = _find_fouria_port(out)
        if port_idx is None:
            return {
                "ok": False,
                "error": "No virtual MIDI port found. Install loopMIDI and create a port named 'loopMIDI Port'.",
                "download": "https://www.tobias-erichsen.de/software/loopmidi.html",
            }
        out.open_port(port_idx)
    except Exception as exc:
        return {"ok": False, "error": f"MIDI port open failed: {exc}"}

    # Convert ticks to seconds
    tpb = events[0].get("ticks_per_beat", 480) if events else 480
    beat_duration = 60.0 / max(30, bpm)
    tick_duration = beat_duration / tpb

    # Build timeline of (time_seconds, msg_bytes)
    timeline = []
    for ev in events:
        note = int(ev["note"]) & 0x7F
        vel  = int(ev.get("velocity", 88)) & 0x7F
        t_on  = ev["start_ticks"] * tick_duration
        t_off = (ev["start_ticks"] + ev["duration_ticks"]) * tick_duration
        timeline.append((t_on,  [0x90, note, vel]))   # note on
        timeline.append((t_off, [0x80, note, 0]))      # note off

    timeline.sort(key=lambda x: x[0])

    notes_sent = 0
    start_time = time.time()
    for t_sec, msg in timeline:
        target = start_time + t_sec
        now = time.time()
        if target > now:
            time.sleep(target - now)
        out.send_message(msg)
        if msg[0] == 0x90:
            notes_sent += 1

    out.close_port()
    return {"ok": True, "method": "rtmidi", "port": port_name, "notes_sent": notes_sent}


def list_midi_ports() -> dict:
    """List available MIDI output ports."""
    if not _rtmidi_available:
        return {"ok": False, "error": "python-rtmidi not installed"}
    try:
        out = rtmidi.MidiOut()
        ports = out.get_ports()
        return {"ok": True, "ports": ports}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
