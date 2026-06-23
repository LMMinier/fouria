from __future__ import annotations

import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("FOURIA_MODEL", "fouria:studio")
TIMEOUT = int(os.environ.get("FOURIA_OLLAMA_TIMEOUT", "240"))
TOOL_CAPABLE_MODEL = os.environ.get("FOURIA_TOOL_MODEL", "qwen2.5:7b")

_TOOL_SUPPORT: dict = {}


def probe_tool_support(model: str) -> bool:
    if model in _TOOL_SUPPORT:
        return _TOOL_SUPPORT[model]
    probe_tool = [{
        "type": "function",
        "function": {
            "name": "ping",
            "description": "Test function",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    }]
    probe_messages = [{"role": "user", "content": "ping"}]
    try:
        payload = {"model": model, "messages": probe_messages, "tools": probe_tool, "stream": False}
        body = json.dumps(payload).encode("utf-8")
        req = Request(f"{OLLAMA_URL}/api/chat", data=body,
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        result = bool(data.get("message", {}).get("tool_calls"))
        _TOOL_SUPPORT[model] = result
        return result
    except Exception:
        _TOOL_SUPPORT[model] = False
        return False


def resolve_tool_model() -> str:
    """Return the best available model for tool-call dispatch."""
    primary = DEFAULT_MODEL
    if probe_tool_support(primary):
        return primary
    # Try the tool-capable fallback
    if probe_tool_support(TOOL_CAPABLE_MODEL):
        print(f"FOURIA: {primary!r} does not support tool_calls — using {TOOL_CAPABLE_MODEL!r} for orchestration", flush=True)
        return TOOL_CAPABLE_MODEL
    # Neither works — return primary anyway (will fall back to intent parsing)
    print(f"FOURIA: No tool-capable model found. Orchestrator will use intent parsing.", flush=True)
    return primary


def strip_thinking(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"(?is)<think>.*?</think>\s*", "", text).strip()
    idx = text.lower().rfind("</think>")
    if idx != -1:
        text = text[idx + len("</think>"):].strip()
    return text


def chat(messages: list[dict], model: str | None = None, options: dict | None = None) -> dict:
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "stream": False,
        "options": options or {},
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        f"{OLLAMA_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Ollama chat failed: {exc}") from exc
    if "message" in data and isinstance(data["message"], dict):
        data["message"]["content"] = strip_thinking(data["message"].get("content", ""))
    return data


def chat_with_tools(messages: list[dict], tools: list[dict], model: str | None = None) -> dict:
    """Send a chat request with tool definitions. Returns the raw Ollama response dict.

    If the model returns tool_calls, they are in response["message"]["tool_calls"].
    If it returns plain text, they are in response["message"]["content"].
    """
    effective_model = model or resolve_tool_model()
    payload = {
        "model": effective_model,
        "messages": messages,
        "tools": tools,
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        f"{OLLAMA_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Ollama tool chat failed: {exc}") from exc
    if "message" in data and isinstance(data["message"], dict):
        data["message"]["content"] = strip_thinking(data["message"].get("content", ""))
    return data

