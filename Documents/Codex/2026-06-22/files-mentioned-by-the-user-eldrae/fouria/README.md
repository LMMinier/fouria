# FOURIA

FOURIA is a local woman-persona AI for FL Studio, music theory, beat making,
melody writing, arrangement, mixing direction, and production coaching.

Default smooth model:

- `fouria:studio`, built from local `qwen2.5-coder:3b`
- Chosen because it is already installed, small enough to run smoothly, and good
  at structured FL workflow/tool/script output.

FOURIA uses RAG first and fine-tuning later. Keep copyrighted FL Studio manuals,
paid course transcripts, and third-party material out of training unless you have
permission. Put your own notes, beat breakdowns, MIDI descriptions, and allowed
reference text in `data/corpus`.

## Quick Start

From this folder:

```powershell
ollama create fouria:studio -f Modelfile
powershell -ExecutionPolicy Bypass -File .\Start-FOURIA.ps1
```

Or run her in the background:

```powershell
powershell -ExecutionPolicy Bypass -File .\Start-FOURIA-Background.ps1
```

Open the face/body studio UI:

```text
http://127.0.0.1:11700/
```

Then test:

```powershell
Invoke-RestMethod http://127.0.0.1:11700/health
```

Chat:

```powershell
$body = @{
  messages = @(@{ role = "user"; content = "FOURIA, make me a dark trap chord progression in F minor." })
  stream = $false
} | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:11700/api/chat -Method POST -Body $body -ContentType "application/json"
```

Generate MIDI:

```powershell
$body = @{
  key = "F"
  scale = "minor"
  bpm = 140
  bars = 8
  style = "dark trap"
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11700/api/generate-midi -Method POST -Body $body -ContentType "application/json"
```

Generate a chord progression:

```powershell
$body = @{ key = "F"; scale = "minor"; bars = 8; style = "dark trap" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11700/api/progression -Method POST -Body $body -ContentType "application/json"
```

Generate drums and 808 MIDI:

```powershell
$body = @{ key = "F"; scale = "minor"; bpm = 140; bars = 8; style = "trap" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11700/api/drums-808 -Method POST -Body $body -ContentType "application/json"
```

Critique exported MIDI or stems:

```powershell
$body = @{ path = "C:\path\to\your.mid" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:11700/api/critique -Method POST -Body $body -ContentType "application/json"
```

## FL Studio Wiring

Install the FL bridge, desktop launcher, and auto-watcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-FOURIA.ps1
```

This installs `fl_bridge\device_fouria.py` into FL Studio's MIDI scripting
folder, creates a `FL Studio + FOURIA` desktop launcher, and adds a Windows
Startup watcher. When FL Studio opens, the watcher starts FOURIA and opens the
avatar UI.

Inside FL Studio, click `Options > MIDI settings > Update MIDI scripts`, then
select the FOURIA script. Current direct FL actions are play, stop, record,
save, undo, redo, show Channel Rack, show Mixer, show Playlist, show Piano Roll,
and notify.

You can run the watcher manually too:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Watch-FL-FOURIA.ps1
```

Save a good session into the training dataset:

```powershell
$body = @{
  rating = "great"
  tags = @("fl-studio", "dark-trap", "808")
  messages = @(
    @{ role = "user"; content = "Make me an F minor dark trap loop." },
    @{ role = "assistant"; content = "Key: F minor. Progression: Fm - Db - Ab - Eb..." }
  )
} | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:11700/api/save-session -Method POST -Body $body -ContentType "application/json"
```

## Project Layout

```text
fouria/
  Modelfile
  Start-FOURIA.ps1
  server/
    fouria_api.py
    model_client.py
    midi_tools.py
    persona.py
    rag.py
  scripts/
    build_dataset.py
    ingest_folder.py
    train_lora.py
  data/
    corpus/
    index/
    midi/
    training/
  fl_bridge/
    device_fouria.py
```

## MVP Endpoints

- `GET /health` - check server/model/corpus status.
- `POST /api/chat` - chat as FOURIA with local RAG context.
- `POST /api/progression` - structured chord progression JSON.
- `POST /api/generate-midi` - melody/chord MIDI plus JSON notes.
- `POST /api/drums-808` - drum and 808 MIDI plus pattern JSON.
- `POST /api/analyze-midi` - basic MIDI file inspection.
- `POST /api/critique` - critique MIDI now, stem metadata now, deeper audio analysis later.
- `POST /api/save-session` - append a good chat/session to `data/training/fouria_sessions.jsonl`.
- `POST /api/reindex` - rebuild local RAG after adding files to `data/corpus`.

## Training Path

1. Use RAG for FL Studio and music-production knowledge.
2. Save useful FOURIA sessions into `data/training`.
3. Fine-tune a LoRA on your own examples:
   - FL workflows you wrote
   - your MIDI exports
   - your beat breakdowns
   - allowed/open music theory material
4. Keep `qwen2.5-coder:3b` as the smooth daily model until you need a larger
   specialist.
