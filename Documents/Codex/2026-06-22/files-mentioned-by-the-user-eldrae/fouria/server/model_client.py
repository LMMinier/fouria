from __future__ import annotations

import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("FOURIA_MODEL", "fouria:studio")
TIMEOUT = int(os.environ.get("FOURIA_OLLAMA_TIMEOUT", "240"))


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
    payload = {
        "model": model or DEFAULT_MODEL,
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

