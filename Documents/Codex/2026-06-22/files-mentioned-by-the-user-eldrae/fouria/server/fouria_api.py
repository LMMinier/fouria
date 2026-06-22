#!/usr/bin/env python3
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import model_client
import rag
from audio_tools import analyze_wav, master_plan, mix_plan
from capabilities import report as capability_report
from production_agent import plan_request
from midi_tools import (analyze_midi, chord_progression_spec,
                        generate_chord_midi_spec, generate_drum_808_spec,
                        generate_midi_spec)
from persona import FOURIA_SYSTEM


ROOT   = Path(os.environ.get("FOURIA_ROOT",  Path(__file__).resolve().parents[1]))
PORT   = int(os.environ.get("FOURIA_PORT",   "11700"))
BIND   = os.environ.get("FOURIA_BIND",       "127.0.0.1")

# Session token — generated once at startup, printed to console.
# Set FOURIA_TOKEN env var to pin a fixed token (useful for launcher scripts).
SESSION_TOKEN = os.environ.get("FOURIA_TOKEN") or secrets.token_hex(16)

STATE_LOCK   = threading.Lock()
FL_STATE     = {"last_seen": 0, "project": {}, "bridge_version": None, "results": []}
ACTION_QUEUE = []
_action_id   = 0
_id_lock     = threading.Lock()

# Actions that write to FL Studio — require token + confirmation flow
MUTATING_PATHS = {
    "/api/fl/action",
    "/api/fl/batch",
    "/api/agent/execute",
}
# Mutating actions that are safe enough to auto-execute from chat
# (window commands / transport only)
SAFE_ACTIONS = {
    "play", "stop", "record", "save", "undo", "redo",
    "show_channel_rack", "show_mixer", "show_playlist", "show_piano_roll", "notify",
}
# Everything else requires explicit confirmation from the UI
DESTRUCTIVE_ACTIONS = {
    "organize_project", "gain_stage_mix",
    "set_channel_name", "set_channel_volume", "set_channel_pan", "set_channel_pitch",
    "mute_channel", "solo_channel", "select_channel", "route_channel",
    "quantize_channel", "set_steps",
    "set_mixer_name", "set_mixer_volume", "set_mixer_pan", "set_mixer_stereo",
    "mute_mixer", "solo_mixer", "select_mixer", "route_mixer", "set_route_level",
    "set_plugin_mix", "set_plugin_param", "next_preset", "previous_preset",
    "set_pattern_name", "select_pattern", "set_playlist_name", "mute_playlist", "solo_playlist",
}
ALLOWED_FL_ACTIONS = SAFE_ACTIONS | DESTRUCTIVE_ACTIONS

FL_ACTION_LABELS = {
    "play": "playback", "stop": "stop", "record": "record",
    "save": "save project", "undo": "undo", "redo": "redo",
    "show_channel_rack": "Channel Rack", "show_mixer": "Mixer",
    "show_playlist": "Playlist", "show_piano_roll": "Piano Roll",
    "notify": "notification",
}


def _next_id() -> int:
    global _action_id
    with _id_lock:
        _action_id += 1
        return _action_id


class FouriaHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin",  "http://127.0.0.1:11700")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Fouria-Token")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        if not path.exists():
            return self._send({"ok": False, "error": "file not found"}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:11700")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 10_000_000:
            self._send({"ok": False, "error": "request too large"}, 413)
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send({"ok": False, "error": "invalid json"}, 400)
            return None

    def _check_token(self) -> bool:
        """Return True if the request carries a valid session token."""
        return self.headers.get("X-Fouria-Token") == SESSION_TOKEN

    def _queue_fl_action(self, action, value=None):
        if action not in ALLOWED_FL_ACTIONS:
            return None
        item = {"id": _next_id(), "action": action, "value": value}
        with STATE_LOCK:
            ACTION_QUEUE.append(item)
            del ACTION_QUEUE[:-100]
        return item

    def _infer_fl_action(self, text):
        t = " " + " ".join(str(text or "").lower().replace("-", " ").split()) + " "
        checks = [
            ("show_piano_roll",   (" piano roll ",  " open keys ",  " open notes ")),
            ("show_channel_rack", (" channel rack ", " step sequencer ")),
            ("show_playlist",     (" playlist ",     " arrangement view ")),
            ("show_mixer",        (" mixer ",        " mix window ")),
            ("record",            (" record ",       " start recording ")),
            ("stop",              (" stop fl ",      " stop playback ",  " pause fl ",   " halt playback ")),
            ("play",              (" play fl ",      " start playback ", " press play ", " run playback ")),
            ("save",              (" save project ", " save flp ",       " save this project ")),
            ("undo",              (" undo ",         " go back ")),
            ("redo",              (" redo ",         " redo that ")),
        ]
        for action, needles in checks:
            if any(needle in t for needle in needles):
                return action
        return None

    # ── routing ──────────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin",  "http://127.0.0.1:11700")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Fouria-Token")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path

        if path in ("/", "/index.html"):
            return self._send_file(ROOT / "ui" / "index.html", "text/html; charset=utf-8")

        if path == "/health":
            with STATE_LOCK:
                fl = dict(FL_STATE)
                fl["connected"] = bool(fl["last_seen"] and time.time() - fl["last_seen"] < 8)
            return self._send({
                "ok": True,
                "name":        "FOURIA",
                "model":       model_client.DEFAULT_MODEL,
                "root":        str(ROOT),
                "token_hint":  SESSION_TOKEN[:4] + "...",
                "corpus_docs": len(rag.load_index().get("docs", [])),
                "fl_studio":   fl,
            })

        if path == "/api/search":
            q = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
            return self._send({"ok": True, "results": rag.search(q)})

        if path == "/api/avatar/state":
            with STATE_LOCK:
                fl        = dict(FL_STATE)
                connected = bool(fl["last_seen"] and time.time() - fl["last_seen"] < 8)
            return self._send({"ok": True, "state": {
                "name":         "FOURIA",
                "mood":         "ready" if connected else "focused",
                "status":       "wired to FL Studio bridge" if connected else "waiting for FL Studio",
                "fl_connected": connected,
                "project":      fl.get("project", {}),
            }})

        if path == "/api/fl/status":
            with STATE_LOCK:
                fl     = dict(FL_STATE)
                fl["connected"] = bool(fl["last_seen"] and time.time() - fl["last_seen"] < 8)
                queued = len(ACTION_QUEUE)
            return self._send({"ok": True, "fl_studio": fl, "queued": queued})

        if path == "/api/capabilities":
            return self._send(capability_report())

        if path == "/api/fl/actions":
            since = int(parse_qs(urlsplit(self.path).query).get("since", ["0"])[0] or 0)
            with STATE_LOCK:
                actions = [a for a in ACTION_QUEUE if a["id"] > since]
            return self._send({"ok": True, "actions": actions[-20:]})

        if path == "/api/fl/results":
            with STATE_LOCK:
                results = list(FL_STATE.get("results") or [])
            return self._send({"ok": True, "results": results[-50:]})

        return self._send({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        path = urlsplit(self.path).path

        # Token guard on all mutating endpoints
        if path in MUTATING_PATHS and not self._check_token():
            return self._send({"ok": False, "error": "unauthorized – include X-Fouria-Token header"}, 401)

        if path == "/api/chat":
            return self._chat()

        if path == "/api/agent/plan":
            p = self._read_json()
            if p is None: return
            with STATE_LOCK:
                project = dict(FL_STATE.get("project") or {})
            plan = plan_request(str(p.get("request", "")), project)
            for a in plan["actions"]:
                a["requires_confirmation"] = a["action"] in DESTRUCTIVE_ACTIONS
            return self._send(plan)

        if path == "/api/agent/execute":
            p = self._read_json()
            if p is None: return
            with STATE_LOCK:
                project = dict(FL_STATE.get("project") or {})
            plan    = plan_request(str(p.get("request", "")), project)
            queued  = []
            for action in plan["actions"]:
                item = self._queue_fl_action(action["action"], action.get("value"))
                if item: queued.append(item)
            plan["queued"]       = queued
            plan["fl_connected"] = bool(FL_STATE.get("last_seen") and
                                        time.time() - FL_STATE["last_seen"] < 8)
            return self._send(plan)

        if path == "/api/progression":
            return self._progression()
        if path == "/api/generate-midi":
            return self._generate_midi()
        if path == "/api/chord-midi":
            p = self._read_json()
            if p is None: return
            return self._send(generate_chord_midi_spec(
                key=str(p.get("key","F")), scale=str(p.get("scale","minor")),
                bpm=int(p.get("bpm",130)), bars=int(p.get("bars",8)),
                style=str(p.get("style","trap"))))
        if path == "/api/drums-808":
            return self._drums_808()
        if path == "/api/analyze-midi":
            return self._analyze_midi()
        if path == "/api/analyze-audio":
            p = self._read_json()
            if p is None: return
            return self._send(analyze_wav(str(p.get("path",""))))
        if path == "/api/mix-plan":
            p = self._read_json()
            if p is None: return
            return self._send(mix_plan(str(p.get("style","modern")), str(p.get("target","full beat"))))
        if path == "/api/master-plan":
            p = self._read_json()
            if p is None: return
            return self._send(master_plan(str(p.get("style","modern")), str(p.get("delivery","streaming"))))
        if path == "/api/critique":
            return self._critique()
        if path == "/api/save-session":
            return self._save_session()

        if path == "/api/fl/sync":
            p = self._read_json()
            if p is None: return
            with STATE_LOCK:
                FL_STATE.update({"last_seen": time.time(),
                                 "project":        p.get("project") or {},
                                 "bridge_version": p.get("bridge_version")})
            return self._send({"ok": True})

        if path == "/api/fl/result":
            p = self._read_json()
            if p is None: return
            p["received_at"] = time.time()
            with STATE_LOCK:
                FL_STATE.setdefault("results", []).append(p)
                del FL_STATE["results"][:-100]
            return self._send({"ok": True})

        if path == "/api/fl/batch":
            p = self._read_json()
            if p is None: return
            queued = []
            for raw in p.get("actions") or []:
                item = self._queue_fl_action(str(raw.get("action","")), raw.get("value"))
                if item: queued.append(item)
            return self._send({"ok": True, "queued": queued})

        if path == "/api/fl/action":
            p = self._read_json()
            if p is None: return
            item = self._queue_fl_action(str(p.get("action","")), p.get("value"))
            if item is None:
                return self._send({"ok": False, "error": "unsupported action"}, 400)
            return self._send({"ok": True, "queued": item})

        if path == "/api/reindex":
            p = self._read_json()
            if p is None: return
            index = rag.build_index()
            return self._send({"ok": True, "docs": len(index.get("docs", []))})

        return self._send({"ok": False, "error": "not found"}, 404)

    # ── handlers ─────────────────────────────────────────────────────────────

    def _chat(self):
        payload  = self._read_json()
        if payload is None:
            return
        messages = payload.get("messages") or []
        latest   = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                latest = str(m.get("content", ""))
                break

        # 1. Simple transport/window intent
        inferred_action = self._infer_fl_action(latest)
        queued_action   = None
        if inferred_action and payload.get("execute_fl", True):
            queued_action = self._queue_fl_action(inferred_action)
            if len(latest.split()) <= 10:
                label = FL_ACTION_LABELS.get(inferred_action, inferred_action)
                return self._send({
                    "ok": True,
                    "message":   {"role": "assistant", "content": f"Queued {label} for FL Studio."},
                    "fl_action": queued_action,
                })

        # 2. Production intent — propose but do NOT auto-execute destructive actions from chat
        proposed_plan = None
        if not inferred_action:
            with STATE_LOCK:
                project = dict(FL_STATE.get("project") or {})
            plan = plan_request(latest, project)
            if plan["actions"]:
                for a in plan["actions"]:
                    a["requires_confirmation"] = a["action"] in DESTRUCTIVE_ACTIONS
                proposed_plan = plan

        # 3. LLM response
        context         = rag.context_block(latest)
        system          = FOURIA_SYSTEM
        if context:
            system += "\n\n" + context
        ollama_messages = [{"role": "system", "content": system}]
        ollama_messages.extend(
            m for m in messages
            if isinstance(m, dict) and m.get("role") in {"user", "assistant"}
        )

        try:
            data = model_client.chat(
                ollama_messages,
                model   = payload.get("model") or model_client.DEFAULT_MODEL,
                options = payload.get("options") or {"num_predict": 650},
            )
        except RuntimeError as exc:
            return self._send({"ok": False, "error": str(exc)}, 502)

        data["ok"]                  = True
        data["fouria_context_used"] = bool(context)

        if queued_action:
            label = FL_ACTION_LABELS.get(queued_action["action"], queued_action["action"])
            data["fl_action"] = queued_action
            if isinstance(data.get("message"), dict):
                content = str(data["message"].get("content","")).rstrip()
                data["message"]["content"] = f"{content}\n\nQueued {label} for FL Studio."

        if proposed_plan:
            data["proposed_fl_plan"] = proposed_plan

        return self._send(data)

    def _progression(self):
        p = self._read_json()
        if p is None: return
        return self._send(chord_progression_spec(
            key=str(p.get("key","F")), scale=str(p.get("scale","minor")),
            bars=int(p.get("bars",8)), style=str(p.get("style","dark trap"))))

    def _generate_midi(self):
        p = self._read_json()
        if p is None: return
        return self._send(generate_midi_spec(
            key=str(p.get("key","F")), scale=str(p.get("scale","minor")),
            bpm=int(p.get("bpm",140)), bars=int(p.get("bars",8)),
            style=str(p.get("style","dark trap"))))

    def _drums_808(self):
        p = self._read_json()
        if p is None: return
        return self._send(generate_drum_808_spec(
            key=str(p.get("key","F")), scale=str(p.get("scale","minor")),
            bpm=int(p.get("bpm",140)), bars=int(p.get("bars",8)),
            style=str(p.get("style","trap"))))

    def _analyze_midi(self):
        p = self._read_json()
        if p is None: return
        return self._send(analyze_midi(str(p.get("path",""))))

    def _critique(self):
        p = self._read_json()
        if p is None: return
        paths = p.get("paths") or ([p.get("path")] if p.get("path") else [])
        items = []
        for raw in paths:
            path = Path(str(raw))
            if not path.exists():
                items.append({"path": str(path), "ok": False, "error": "file not found"})
                continue
            if path.suffix.lower() in {".mid", ".midi"}:
                items.append(analyze_midi(str(path)))
                continue
            items.append({
                "ok": True, "path": str(path),
                "type":    path.suffix.lower().lstrip(".") or "file",
                "size_mb": round(path.stat().st_size / 1_048_576, 3),
                "advice":  [
                    "Export dry and wet stems so FOURIA can compare arrangement vs mix choices.",
                    "Name stems by role: kick, 808, snare, hats, melody, counter, vocal, fx.",
                    "Next build: add waveform/FFT analysis to detect mud, clipping, and stereo issues.",
                ],
            })
        return self._send({"ok": True, "items": items})

    def _save_session(self):
        p = self._read_json()
        if p is None: return
        messages = p.get("messages")
        if not isinstance(messages, list) or not messages:
            return self._send({"ok": False, "error": "messages must be a non-empty list"}, 400)
        entry = {
            "messages":  messages,
            "metadata":  {
                "source":     "fouria_api",
                "rating":     p.get("rating", "good"),
                "tags":       p.get("tags", []),
                "created_at": int(time.time()),
            },
        }
        out = ROOT / "data" / "training" / "fouria_sessions.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return self._send({"ok": True, "path": str(out)})


def main():
    (ROOT / "data" / "corpus").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "midi").mkdir(parents=True, exist_ok=True)
    print(f"FOURIA session token: {SESSION_TOKEN}", flush=True)
    print(f"FOURIA listening at http://{BIND}:{PORT}", flush=True)
    print(f"Model: {model_client.DEFAULT_MODEL}", flush=True)
    server = ThreadingHTTPServer((BIND, PORT), FouriaHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
