"""FOURIA tool orchestrator — spider brain that dispatches to specialized tools."""
import json

from audio_tools import analyze_spectrum, vocal_eq_params
from midi_tools import generate_drum_808_spec, generate_chord_midi_spec, generate_midi_spec
from production_agent import plan_request, _parse_beat_params


# ── Tool definitions (sent to Ollama as tool schemas) ─────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "make_beat",
            "description": "Generate a complete beat: sets tempo, writes drum step patterns to FL Studio channels, generates drum+808, chord, and melody MIDI files. Use when the user asks to make, build, cook, or create a beat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bpm":   {"type": "integer", "description": "Tempo in BPM (40-280)", "default": 140},
                    "key":   {"type": "string",  "description": "Musical key, e.g. 'F', 'C#', 'Bb'", "default": "F"},
                    "scale": {"type": "string",  "description": "Scale: minor, major, harmonic_minor, phrygian", "default": "minor"},
                    "bars":  {"type": "integer", "description": "Number of bars (1-64)", "default": 8},
                    "style": {"type": "string",  "description": "Style: trap, drill, lo-fi, boom_bap, afrobeats", "default": "trap"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_eq",
            "description": "Analyze a WAV audio file spectrally and return Parametric EQ 2 parameter suggestions. Use when the user wants to EQ a vocal, fix a sample, or analyze audio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the WAV file"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_tempo",
            "description": "Set the FL Studio project tempo/BPM. Use when the user says 'set tempo', 'change BPM', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bpm": {"type": "number", "description": "Target BPM (40-280)"},
                },
                "required": ["bpm"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "organize_project",
            "description": "Route all channels to unique mixer inserts and mirror channel names to mixer tracks. Use when the user says 'organize', 'set up the mixer', 'clean up the project'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gain_stage",
            "description": "Apply an initial role-based static balance to all mixer tracks. Use when the user says 'gain stage', 'initial mix', 'rough balance'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_sample",
            "description": "Load a sample file into a specific FL Studio channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_index": {"type": "integer", "description": "Channel rack index (0-based)"},
                    "path": {"type": "string", "description": "Absolute path to the sample file (.wav, .flac, .mp3)"},
                },
                "required": ["channel_index", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "production_help",
            "description": "Give production advice, answer a music question, explain a concept, suggest settings, or discuss a mix. Use for anything that doesn't require a specific FL Studio action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "What the user is asking about"},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_project",
            "description": "Open FL Studio's render/export dialog to bounce the project to audio. Use when user says 'render', 'export', 'bounce', 'mixdown'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arrange_pattern",
            "description": "Clone or organize patterns in the FL Studio playlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern_index": {"type": "integer", "description": "Pattern index to clone/arrange"},
                    "operation": {"type": "string", "description": "clone or color", "enum": ["clone", "color"]},
                },
                "required": ["operation"],
            },
        },
    },
]


# ── Tool handlers ──────────────────────────────────────────────────────────────

def handle_tool(name: str, args: dict, fl_project: dict) -> dict:
    """Execute a tool by name and return structured result."""

    if name == "make_beat":
        bpm   = int(args.get("bpm", 140))
        key   = str(args.get("key", "F"))
        scale = str(args.get("scale", "minor"))
        bars  = int(args.get("bars", 8))
        style = str(args.get("style", "trap"))
        # Delegate to production_agent for full plan (includes FL actions)
        phrase = f"make a {style} beat in {key} {scale} at {bpm} bpm {bars} bars"
        return plan_request(phrase, fl_project)

    if name == "analyze_eq":
        path = str(args.get("path", ""))
        spec = analyze_spectrum(path)
        if not spec.get("ok"):
            return spec
        eq = vocal_eq_params(spec)
        return {**spec, **eq}

    if name == "set_tempo":
        bpm = float(args.get("bpm", 140))
        return {
            "ok": True, "intent": "set_tempo",
            "actions": [{"action": "set_tempo", "value": {"bpm": bpm}}],
            "requires_fl_bridge": True,
            "verification": f"Check transport bar shows {int(bpm)} BPM.",
        }

    if name == "organize_project":
        return {
            "ok": True, "intent": "organize_project",
            "actions": [{"action": "organize_project", "value": {}}],
            "requires_fl_bridge": True,
            "verification": "Check mixer — each channel should have a named insert.",
        }

    if name == "gain_stage":
        return {
            "ok": True, "intent": "gain_stage_mix",
            "actions": [{"action": "gain_stage_mix", "value": {}}],
            "requires_fl_bridge": True,
            "verification": "Check mixer faders; verify levels against reference.",
        }

    if name == "load_sample":
        return {
            "ok": True, "intent": "load_sample",
            "actions": [{"action": "load_sample", "value": {
                "index": int(args.get("channel_index", 0)),
                "path": str(args.get("path", "")),
            }}],
            "requires_fl_bridge": True,
            "verification": "Check the channel in the channel rack shows the new sample.",
        }

    if name == "production_help":
        # No FL actions — just return topic for the caller to generate a chat reply
        return {"ok": True, "intent": "production_help", "topic": args.get("topic", ""), "actions": []}

    if name == "render_project":
        return {
            "ok": True, "intent": "render",
            "actions": [{"action": "render", "value": {}}],
            "requires_fl_bridge": True,
            "verification": "FL Studio render dialog should open. Configure output settings.",
        }

    if name == "arrange_pattern":
        op = args.get("operation", "clone")
        idx = int(args.get("pattern_index", 0))
        if op == "clone":
            return {
                "ok": True, "intent": "pattern_edit",
                "actions": [{"action": "clone_pattern", "value": {"index": idx}}],
                "requires_fl_bridge": True,
                "verification": "Check FL Studio playlist for new cloned pattern.",
            }
        return {"ok": False, "error": "Unknown operation"}

    return {"ok": False, "error": f"Unknown tool: {name}"}


def tool_names() -> list:
    return [t["function"]["name"] for t in TOOLS]
