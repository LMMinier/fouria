# FOURIA Piano Roll Engine — virtual_midi

C++ Windows MIDI sender that plays note events into FL Studio's Piano Roll via a virtual MIDI loopback port.

## Prerequisites

1. Install **loopMIDI** (free): https://www.tobias-erichsen.de/software/loopmidi.html
2. In loopMIDI, create a port named `loopMIDI Port` (the default name works).
3. In FL Studio: **Options > MIDI Settings**, add `loopMIDI Port` as an **Input** device and enable it.
4. Arm a channel in the FL Studio Channel Rack (click the record button on the channel).
5. Enable pattern recording: **Transport > Record** (or press R).

## Build

**With MSVC (recommended):**

```bat
cd piano_roll_engine
build.bat
```

This produces `virtual_midi.exe` and copies it to `../data/`.

**With CMake + MSVC:**

```bat
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

## Usage

```
virtual_midi.exe notes.json
```

### notes.json format

```json
{
  "bpm": 140,
  "ticks_per_beat": 480,
  "events": [
    {"note": 60, "start_ticks": 0,   "duration_ticks": 480, "velocity": 88},
    {"note": 62, "start_ticks": 480, "duration_ticks": 480, "velocity": 80},
    {"note": 65, "start_ticks": 960, "duration_ticks": 960, "velocity": 92}
  ]
}
```

- `note`: MIDI note number (0–127; middle C = 60)
- `start_ticks`: start time in ticks
- `duration_ticks`: note duration in ticks
- `velocity`: MIDI velocity (0–127)
- `bpm`: project tempo
- `ticks_per_beat`: ticks per quarter note (default 480)

## Python alternative

If you prefer not to compile, use the Python sender in `server/midi_output.py`:

```python
from midi_output import send_notes_to_piano_roll
result = send_notes_to_piano_roll(events, bpm=140)
```

Requires `pip install python-rtmidi` and loopMIDI running.

## API endpoint

`POST /api/piano_roll/send` with JSON body:

```json
{
  "bpm": 140,
  "events": [
    {"note": 60, "start_ticks": 0, "duration_ticks": 480, "velocity": 88, "ticks_per_beat": 480}
  ]
}
```

`GET /api/piano_roll/ports` — list available MIDI output ports.

## Troubleshooting

- **No port found**: Make sure loopMIDI is running and has an active port.
- **Notes not landing in Piano Roll**: Verify FL Studio has the loopMIDI port enabled as MIDI input AND the target channel is armed to record.
- **Timing drift**: For large files with many notes, use the C++ binary — it uses `QueryPerformanceCounter` for sub-millisecond accuracy vs Python's `time.sleep`.
