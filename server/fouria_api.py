#!/usr/bin/env python3
"""FOURIA v0.2 API server.

Safety architecture:
  - All /api/* routes require Bearer token authentication.
  - Mutating FL actions start as 'pending'; they require explicit /approve before
    the bridge sees them. Safe (transport/window) actions are auto-approved.
  - The bridge registers a session_id on connect; actions are bound to it.
  - Claimed actions that are never executed become 'ambiguous' on reconnect
    and are never silently replayed.
  - Every mutating execution requires a fresh, fail-closed safeToEdit check
    performed by the bridge, not the server.
"""
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import action_store
import model_client
import rag
from orchestrator import TOOLS, handle_tool, tool_names
from audio_tools import analyze_spectrum, analyze_wav, master_plan, mix_plan, vocal_eq_params
from capabilities import report as capability_report
from context_injector import build_project_context
import library_index as _lib_mod
import desktop_executor
from library_index import build_library_index, load_library_index, find_sample, library_context_block
from midi_tools import (
    analyze_midi, chord_progression_spec,
    generate_chord_midi_spec, generate_drum_808_spec, generate_midi_spec,
)
from persona import FOURIA_SYSTEM
from production_agent import plan_request

ROOT  = Path(os.environ.get("FOURIA_ROOT", Path(__file__).resolve().parents[1]))
_LIBRARY_INDEX_PATH = ROOT / "data" / "library_index.json"
_LIBRARY_INDEX: dict = {}
PORT  = int(os.environ.get("FOURIA_PORT", "11700"))
BIND  = os.environ.get("FOURIA_BIND", "127.0.0.1")

# Printed to console at startup. Set FOURIA_TOKEN env var to pin a fixed token.
SESSION_TOKEN = os.environ.get("FOURIA_TOKEN") or secrets.token_hex(16)

STATE_LOCK = threading.Lock()
FL_STATE   = {"last_seen": 0, "project": {}, "bridge_version": None, "session_id": None}

# Actions that write FL Studio state — require explicit user approval before dispatch.
DESTRUCTIVE_ACTIONS = frozenset({
    "organize_project", "gain_stage_mix",
    "set_channel_name", "set_channel_volume", "set_channel_pan", "set_channel_pitch",
    "mute_channel", "solo_channel", "select_channel", "route_channel",
    "quantize_channel", "set_steps",
    "set_mixer_name", "set_mixer_volume", "set_mixer_pan", "set_mixer_stereo",
    "mute_mixer", "solo_mixer", "select_mixer", "route_mixer", "set_route_level",
    "set_plugin_mix", "set_plugin_param", "next_preset", "previous_preset",
    "set_pattern_name", "select_pattern", "set_playlist_name", "mute_playlist", "solo_playlist",
    "set_tempo", "load_sample", "set_channel_color", "set_pattern_length", "set_steps_32",
    "set_playlist_track_color", "clone_pattern", "set_pattern_color", "randomize_preset",
})
SAFE_ACTIONS = frozenset({
    "play", "stop", "record", "save", "undo", "redo",
    "show_channel_rack", "show_mixer", "show_playlist", "show_piano_roll", "notify",
    "render", "toggle_record_mode", "jump_to_start", "jump_to_end", "tempo_tap",
})
ALLOWED_FL_ACTIONS = SAFE_ACTIONS | DESTRUCTIVE_ACTIONS


def _validate_action_value(action: str, value: dict) -> str | None:
    """Return an error string if the action/value pair is invalid, else None."""
    if action not in ALLOWED_FL_ACTIONS:
        return f"unknown action: {action!r}"
    if action in SAFE_ACTIONS:
        return None  # safe actions need no value validation
    v = value or {}
    idx = v.get("index")
    if action.startswith("set_channel_") or action in ("mute_channel", "solo_channel", "select_channel", "route_channel", "quantize_channel", "set_steps"):
        if not isinstance(idx, int) or idx < 0:
            return f"index must be a non-negative integer for {action!r}"
    if action.startswith("set_mixer_") or action in ("mute_mixer", "solo_mixer", "select_mixer", "route_mixer", "set_route_level"):
        if not isinstance(idx, int) or idx < 0:
            return f"index must be a non-negative integer for {action!r}"
    if action == "set_channel_volume":
        vol = v.get("volume")
        if not isinstance(vol, (int, float)) or not (0.0 <= float(vol) <= 1.0):
            return "volume must be a float in [0.0, 1.0]"
    if action == "set_mixer_volume":
        vol = v.get("volume")
        if not isinstance(vol, (int, float)) or not (0.0 <= float(vol) <= 1.0):
            return "volume must be a float in [0.0, 1.0]"
    if action == "set_plugin_param":
        val = v.get("value")
        if not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.0):
            return "value must be a float in [0.0, 1.0] for set_plugin_param"
        if not isinstance(v.get("param"), int):
            return "param must be an integer for set_plugin_param"
    if action == "set_tempo":
        if not (40 <= float(v.get("bpm", 0)) <= 280):
            return "bpm must be 40–280"
    if action == "load_sample":
        if not v.get("path"):
            return "path required"
        if not isinstance(v.get("index", -1), int):
            return "index must be int"
    if action == "set_steps_32":
        steps = v.get("steps", [])
        if not isinstance(steps, list):
            return "steps must be a list"
        if any(not (0 <= int(s) <= 63) for s in steps):
            return "step indices must be 0–63"
    return None


FL_ACTION_LABELS = {
    "play": "playback", "stop": "stop", "record": "record",
    "save": "save project", "undo": "undo", "redo": "redo",
    "show_channel_rack": "Channel Rack", "show_mixer": "Mixer",
    "show_playlist": "Playlist", "show_piano_roll": "Piano Roll",
    "notify": "notification",
}

# Endpoints that bypass token check (bridge heartbeat + health only).
# Bridge still uses the same token but via Authorization header.
_NO_AUTH_PATHS = frozenset({"/", "/index.html", "/health"})


def _project_hash(project: dict) -> str:
    return project.get("title") or ""


class FouriaHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    # ── auth ─────────────────────────────────────────────────────────────────

    def _check_token(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == SESSION_TOKEN
        return self.headers.get("X-Fouria-Token") == SESSION_TOKEN

    def _require_token(self) -> bool:
        """Returns True if the request is authorized. Sends 401 and returns False otherwise."""
        if not self._check_token():
            self._send({"ok": False, "error": "Unauthorized — include 'Authorization: Bearer <token>' header"}, 401)
            return False
        return True

    # ── helpers ──────────────────────────────────────────────────────────────

    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:11700")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Fouria-Token")
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

    def _queue_fl_action(self, action, value=None) -> dict | None:
        """Enqueue an action into SQLite. Returns the action dict or None if unknown/invalid."""
        err = _validate_action_value(action, value or {})
        if err:
            return None
        with STATE_LOCK:
            sid = FL_STATE.get("session_id")
            ph  = _project_hash(FL_STATE.get("project") or {})
        return action_store.enqueue(action, value or {}, session_id=sid, project_hash=ph)

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
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:11700")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Fouria-Token")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path

        # Public endpoints — UI is served with token pre-injected so no manual copy-paste needed
        if path in ("/", "/index.html"):
            ui_file = ROOT / "ui" / "index.html"
            if not ui_file.exists():
                return self._send({"ok": False, "error": "UI not found"}, 404)
            html = ui_file.read_text(encoding="utf-8")
            inject = f'<script>window.FOURIA_TOKEN={json.dumps(SESSION_TOKEN)};window.FOURIA_AUTO=true;</script>'
            html = html.replace("</head>", inject + "\n</head>", 1)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:11700")
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/health":
            with STATE_LOCK:
                fl = dict(FL_STATE)
                fl["connected"] = bool(fl["last_seen"] and time.time() - fl["last_seen"] < 8)
            return self._send({
                "ok":        True,
                "name":      "FOURIA",
                "version":   "0.2.0",
                "model":     model_client.DEFAULT_MODEL,
                "root":      str(ROOT),
                "token_hint": SESSION_TOKEN[:4] + "...",
                "corpus_docs": len(rag.load_index().get("docs", [])),
                "fl_studio": fl,
            })

        # All /api/* require token
        if path.startswith("/api/") and not self._require_token():
            return

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
                fl = dict(FL_STATE)
                fl["connected"] = bool(fl["last_seen"] and time.time() - fl["last_seen"] < 8)
            return self._send({
                "ok":       True,
                "fl_studio": fl,
                "queued":   action_store.queue_depth(),
            })

        if path == "/api/fl/actions":
            since = int(parse_qs(urlsplit(self.path).query).get("since", ["0"])[0] or 0)
            return self._send({"ok": True, "actions": action_store.pending_since(since)[-20:]})

        if path == "/api/fl/actions/claim":
            qs  = parse_qs(urlsplit(self.path).query)
            sid = qs.get("session_id", [None])[0]
            if not sid:
                return self._send({"ok": False, "error": "session_id required"}, 400)
            try:
                sid_int = int(sid)
            except ValueError:
                return self._send({"ok": False, "error": "session_id must be integer"}, 400)
            claimed = action_store.claim_batch(sid_int)
            return self._send({"ok": True, "actions": claimed})

        if path == "/api/fl/results":
            return self._send({"ok": True, "results": action_store.recent_results(50)})

        if path == "/api/fl/ambiguous":
            return self._send({"ok": True, "ambiguous": action_store.ambiguous_actions()})
        if path == "/api/agent/jobs":
            return self._send({"ok": True, "jobs": desktop_executor.recent_jobs()})

        if path == "/api/capabilities":
            return self._send(capability_report())

        if path == "/api/piano_roll/ports":
            from midi_output import list_midi_ports
            return self._send(list_midi_ports())

        if path == "/api/library":
            return self._send({"ok": True, "sample_count": _LIBRARY_INDEX.get("sample_count", 0), "preset_count": _LIBRARY_INDEX.get("preset_count", 0), "role_counts": _LIBRARY_INDEX.get("role_counts", {}), "fl_install": _LIBRARY_INDEX.get("fl_install")})

        return self._send({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        path = urlsplit(self.path).path

        # Public for health only; all /api/* require token
        if path.startswith("/api/") and not self._require_token():
            return

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
            plan   = plan_request(str(p.get("request", "")), project)
            queued = []
            for action in plan["actions"]:
                item = self._queue_fl_action(action["action"], action.get("value"))
                if item:
                    queued.append(item)
            plan["queued"]       = queued
            plan["fl_connected"] = bool(FL_STATE.get("last_seen") and
                                        time.time() - FL_STATE["last_seen"] < 8)
            return self._send(plan)

        if path == "/api/fl/action":
            p = self._read_json()
            if p is None: return
            action = str(p.get("action", ""))
            value  = p.get("value") or {}
            err    = _validate_action_value(action, value)
            if err:
                return self._send({"ok": False, "error": err}, 400)
            item = self._queue_fl_action(action, value)
            if item is None:
                return self._send({"ok": False, "error": "unsupported action"}, 400)
            return self._send({"ok": True, "action": item})

        # Approve a pending action — mutating actions must pass through here
        # before the bridge will claim and execute them.
        m = re.fullmatch(r"/api/fl/action/(\d+)/approve", path)
        if m:
            action_id = int(m.group(1))
            changed   = action_store.approve(action_id)
            if not changed:
                return self._send(
                    {"ok": False, "error": "action not found or already past pending state"}, 404
                )
            return self._send({"ok": True, "action_id": action_id, "status": "approved"})

        if path == "/api/fl/batch":
            p = self._read_json()
            if p is None: return
            queued = []
            for raw in (p.get("actions") or []):
                item = self._queue_fl_action(str(raw.get("action", "")), raw.get("value"))
                if item:
                    queued.append(item)
            return self._send({"ok": True, "queued": queued})

        if path == "/api/fl/register":
            p = self._read_json()
            if p is None: return
            bridge_id    = str(p.get("bridge_id", ""))
            project_hash = str(p.get("project_hash", ""))
            if not bridge_id:
                return self._send({"ok": False, "error": "bridge_id required"}, 400)
            session_id = action_store.register_session(bridge_id, project_hash)
            with STATE_LOCK:
                FL_STATE["session_id"] = session_id
            return self._send({"ok": True, "session_id": session_id})

        if path == "/api/fl/sync":
            p = self._read_json()
            if p is None: return
            project = p.get("project") or {}
            sid     = p.get("session_id")
            with STATE_LOCK:
                FL_STATE.update({
                    "last_seen":      time.time(),
                    "project":        project,
                    "bridge_version": p.get("bridge_version"),
                })
                if sid:
                    FL_STATE["session_id"] = sid
            if sid and isinstance(sid, int):
                action_store.refresh_session(sid, _project_hash(project))
            return self._send({"ok": True})

        if path == "/api/fl/result":
            p = self._read_json()
            if p is None: return
            action_id = p.get("id")
            if isinstance(action_id, int):
                action_store.store_result(
                    action_id,
                    bool(p.get("ok")),
                    output=p.get("output"),
                    error=p.get("error"),
                )
            return self._send({"ok": True})

        if path == "/api/progression":
            return self._progression()
        if path == "/api/generate-midi":
            return self._generate_midi()
        if path == "/api/chord-midi":
            p = self._read_json()
            if p is None: return
            return self._send(generate_chord_midi_spec(
                key=str(p.get("key", "F")), scale=str(p.get("scale", "minor")),
                bpm=int(p.get("bpm", 130)), bars=int(p.get("bars", 8)),
                style=str(p.get("style", "trap"))))
        if path == "/api/drums-808":
            return self._drums_808()
        if path == "/api/analyze-midi":
            return self._analyze_midi()
        if path == "/api/analyze-audio":
            p = self._read_json()
            if p is None: return
            return self._send(analyze_wav(str(p.get("path", ""))))
        if path == "/api/analyze/eq":
            p = self._read_json()
            if p is None: return
            wav_path = p.get("path", "")
            if not wav_path:
                return self._send({"ok": False, "error": "path required"}, 400)
            spec = analyze_spectrum(wav_path)
            if not spec.get("ok"):
                return self._send(spec, 400)
            eq = vocal_eq_params(spec)
            return self._send({**spec, **eq})
        if path == "/api/mix-plan":
            p = self._read_json()
            if p is None: return
            return self._send(mix_plan(str(p.get("style", "modern")), str(p.get("target", "full beat"))))
        if path == "/api/master-plan":
            p = self._read_json()
            if p is None: return
            return self._send(master_plan(str(p.get("style", "modern")), str(p.get("delivery", "streaming"))))
        if path == "/api/critique":
            return self._critique()
        if path == "/api/save-session":
            return self._save_session()
        if path == "/api/reindex":
            p = self._read_json()
            if p is None: return
            index = rag.build_index()
            return self._send({"ok": True, "docs": len(index.get("docs", []))})

        if path == "/api/library/rescan":
            global _LIBRARY_INDEX
            try:
                _LIBRARY_INDEX = build_library_index(_LIBRARY_INDEX_PATH)
                _lib_mod.set_active_index(_LIBRARY_INDEX)
                return self._send({"ok": True, "sample_count": _LIBRARY_INDEX["sample_count"], "preset_count": _LIBRARY_INDEX["preset_count"], "role_counts": _LIBRARY_INDEX["role_counts"]})
            except Exception as exc:
                return self._send({"ok": False, "error": str(exc)}, 500)

        if path == "/api/piano_roll/send":
            p = self._read_json()
            if p is None: return
            from midi_output import send_notes_to_piano_roll, list_midi_ports
            events = p.get("events", [])
            bpm = int(p.get("bpm", 140))
            if not events:
                return self._send({"ok": False, "error": "events required"})
            import threading
            def _send_async():
                send_notes_to_piano_roll(events, bpm)
            threading.Thread(target=_send_async, daemon=True).start()
            return self._send({"ok": True, "notes_queued": len(events), "bpm": bpm,
                                "note": "Notes sending to Piano Roll via virtual MIDI. Make sure FL Studio is armed to record on the target channel."})

        if path == "/api/beat":
            p = self._read_json()
            if p is None: return
            text = "make a beat " + str(p.get("description", ""))
            with STATE_LOCK:
                project = FL_STATE.get("project", {})
            plan = plan_request(text, project)
            session_id = FL_STATE.get("session_id")
            for act in plan.get("actions", []):
                try:
                    action_store.enqueue(act["action"], act.get("value", {}),
                                        session_id, project.get("title", ""))
                except Exception:
                    pass
            connected = bool(FL_STATE.get("last_seen") and time.time() - FL_STATE["last_seen"] < 8)
            if (
                not connected
                and p.get("execute", True)
                and os.environ.get("FOURIA_DESKTOP_EXECUTOR") == "1"
            ):
                plan["desktop_job"] = desktop_executor.start_beat(plan)
            return self._send(plan)

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

        normalized = " ".join(latest.lower().split())
        if normalized in {
            "connect to fl", "connect to fl studio", "are you connected to fl",
            "are you connected to fl studio", "check fl connection",
        }:
            with STATE_LOCK:
                connected = bool(
                    FL_STATE.get("last_seen")
                    and time.time() - FL_STATE["last_seen"] < 8
                )
                bridge = FL_STATE.get("bridge_version")
                project = dict(FL_STATE.get("project") or {})
            if connected:
                content = (
                    f"Connected to FL Studio through bridge {bridge}. "
                    f"Active project: {project.get('title') or 'untitled'}."
                )
            else:
                content = (
                    "Not connected to FL Studio. I will not claim control until FL is open "
                    "and FOURIA AI Studio Assistant is active on an enabled MIDI input."
                )
            return self._send({
                "ok": True,
                "message": {"role": "assistant", "content": content},
                "reply": content,
                "fl_connected": connected,
            })

        inferred_action = self._infer_fl_action(latest)
        queued_action   = None
        if inferred_action and payload.get("execute_fl", True):
            queued_action = self._queue_fl_action(inferred_action)
            if len(latest.split()) <= 10:
                label = FL_ACTION_LABELS.get(inferred_action, inferred_action)
                return self._send({
                    "ok":      True,
                    "message": {"role": "assistant", "content": f"Queued {label} for FL Studio."},
                    "fl_action": queued_action,
                })

        proposed_plan = None
        if not inferred_action:
            with STATE_LOCK:
                project = dict(FL_STATE.get("project") or {})
            plan = plan_request(latest, project)
            if plan["actions"]:
                for a in plan["actions"]:
                    a["requires_confirmation"] = a["action"] in DESTRUCTIVE_ACTIONS
                proposed_plan = plan

        # Build system prompt: base persona + RAG context + live project context
        with STATE_LOCK:
            fl_snapshot = dict(FL_STATE)
        project_ctx = build_project_context(fl_snapshot)
        rag_ctx     = rag.context_block(latest)
        lib_ctx     = library_context_block(_LIBRARY_INDEX)
        system      = FOURIA_SYSTEM
        if project_ctx:
            system += "\n\n" + project_ctx
        if rag_ctx:
            system += "\n\n" + rag_ctx
        if lib_ctx:
            system += "\n\n" + lib_ctx

        ollama_msgs = [{"role": "system", "content": system}]
        ollama_msgs.extend(
            m for m in messages
            if isinstance(m, dict) and m.get("role") in {"user", "assistant"}
        )
        try:
            resp = model_client.chat_with_tools(
                ollama_msgs,
                TOOLS,
                model=payload.get("model") or model_client.DEFAULT_MODEL,
            )
        except RuntimeError as exc:
            return self._send({"ok": False, "error": str(exc)}, 502)

        msg        = resp.get("message", {})
        tool_calls = msg.get("tool_calls", [])

        if tool_calls:
            call      = tool_calls[0]
            fn        = call.get("function", {})
            tool_name = fn.get("name", "")
            tool_args = fn.get("arguments", {})
            print(f"FOURIA orchestrator: tool_calls → {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:120]})", flush=True)
            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except Exception:
                    tool_args = {}

            with STATE_LOCK:
                project = FL_STATE.get("project", {})

            tool_result = handle_tool(tool_name, tool_args, project)
            connected = bool(
                FL_STATE.get("last_seen")
                and time.time() - FL_STATE["last_seen"] < 8
            )
            if (
                tool_result.get("intent") == "make_beat"
                and payload.get("execute_fl", True)
                and not connected
                and os.environ.get("FOURIA_DESKTOP_EXECUTOR") == "1"
            ):
                tool_result["desktop_job"] = desktop_executor.start_beat(tool_result)

            session_id = FL_STATE.get("session_id")
            for act in tool_result.get("actions", []):
                try:
                    action_store.enqueue(act["action"], act.get("value", {}), session_id, project.get("title", ""))
                except Exception:
                    pass

            summary_messages = ollama_msgs + [
                {"role": "assistant", "content": "", "tool_calls": tool_calls},
                {"role": "tool", "name": tool_name, "content": json.dumps(tool_result, ensure_ascii=False)},
            ]
            try:
                summary = model_client.chat(summary_messages)
            except RuntimeError as exc:
                return self._send({"ok": False, "error": str(exc)}, 502)

            reply_text = summary.get("message", {}).get("content", "Done.")

            return self._send({
                "ok":               True,
                "reply":            reply_text,
                "message":          {"role": "assistant", "content": reply_text},
                "tool_used":        tool_name,
                "tool_result":      tool_result,
                "proposed_fl_plan": tool_result if tool_result.get("actions") else None,
                "fouria_context_used": bool(project_ctx or rag_ctx),
            })

        # ── No tool_calls — plain text path (existing behaviour) ──────────────
        print(f"FOURIA orchestrator: plain-text path (intent parsing)", flush=True)
        data = resp
        data["ok"]                  = True
        data["fouria_context_used"] = bool(project_ctx or rag_ctx)

        if queued_action:
            label = FL_ACTION_LABELS.get(queued_action["action"], queued_action["action"])
            data["fl_action"] = queued_action
            if isinstance(data.get("message"), dict):
                content = str(data["message"].get("content", "")).rstrip()
                data["message"]["content"] = f"{content}\n\nQueued {label} for FL Studio."

        if proposed_plan:
            data["proposed_fl_plan"] = proposed_plan

        return self._send(data)

    def _progression(self):
        p = self._read_json()
        if p is None: return
        return self._send(chord_progression_spec(
            key=str(p.get("key", "F")), scale=str(p.get("scale", "minor")),
            bars=int(p.get("bars", 8)), style=str(p.get("style", "dark trap"))))

    def _generate_midi(self):
        p = self._read_json()
        if p is None: return
        return self._send(generate_midi_spec(
            key=str(p.get("key", "F")), scale=str(p.get("scale", "minor")),
            bpm=int(p.get("bpm", 140)), bars=int(p.get("bars", 8)),
            style=str(p.get("style", "dark trap"))))

    def _drums_808(self):
        p = self._read_json()
        if p is None: return
        return self._send(generate_drum_808_spec(
            key=str(p.get("key", "F")), scale=str(p.get("scale", "minor")),
            bpm=int(p.get("bpm", 140)), bars=int(p.get("bars", 8)),
            style=str(p.get("style", "trap"))))

    def _analyze_midi(self):
        p = self._read_json()
        if p is None: return
        return self._send(analyze_midi(str(p.get("path", ""))))

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
                "ok":      True,
                "path":    str(path),
                "type":    path.suffix.lower().lstrip(".") or "file",
                "size_mb": round(path.stat().st_size / 1_048_576, 3),
                "advice": [
                    "Export dry and wet stems so FOURIA can compare arrangement versus mix decisions.",
                    "Name stems by role: kick, 808, snare, hats, melody, counter, vocal, fx.",
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
            "messages": messages,
            "metadata": {
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
    global _LIBRARY_INDEX
    action_store.init_db()
    _LIBRARY_INDEX = load_library_index(_LIBRARY_INDEX_PATH)
    if not _LIBRARY_INDEX:
        print("FOURIA: scanning your FL Studio library (first run)…", flush=True)
        try:
            _LIBRARY_INDEX = build_library_index(_LIBRARY_INDEX_PATH)
            print(f"FOURIA: library indexed — {_LIBRARY_INDEX['sample_count']} samples, {_LIBRARY_INDEX['preset_count']} presets.", flush=True)
        except Exception as exc:
            print(f"FOURIA: library scan failed ({exc}); continuing without library index.", flush=True)
            _LIBRARY_INDEX = {}
    else:
        print(f"FOURIA: library index loaded — {_LIBRARY_INDEX.get('sample_count', 0)} samples.", flush=True)
    _lib_mod.set_active_index(_LIBRARY_INDEX)
    from model_client import resolve_tool_model, DEFAULT_MODEL, TOOL_CAPABLE_MODEL  # noqa: F401
    tool_model = resolve_tool_model()
    print(f"Orchestration model: {tool_model}", flush=True)
    (ROOT / "data" / "corpus").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "midi").mkdir(parents=True, exist_ok=True)
    token_file = ROOT / "data" / "fouria.token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(SESSION_TOKEN, encoding="utf-8")
    server = ThreadingHTTPServer((BIND, PORT), FouriaHandler)
    print(f"FOURIA v0.2 listening at http://{BIND}:{PORT}", flush=True)
    print(f"Model:  {model_client.DEFAULT_MODEL}", flush=True)
    print(f"Token:  {SESSION_TOKEN}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
