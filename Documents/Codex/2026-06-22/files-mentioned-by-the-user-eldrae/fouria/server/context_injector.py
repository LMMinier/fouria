"""Builds the project-context block injected into every chat system prompt.
The bridge sends a full FL_STATE snapshot every 2 s; this module formats it
into a compact, model-readable summary so FOURIA always knows what is loaded.
"""
from __future__ import annotations


def _db(value) -> str:
    if value is None:
        return ""
    try:
        return f" ({float(value):+.1f} dB)"
    except (TypeError, ValueError):
        return ""


def _pan_str(pan) -> str:
    try:
        v = float(pan)
        if abs(v) < 0.02:
            return "C"
        side = "R" if v > 0 else "L"
        return f"{side}{abs(int(v * 100))}"
    except (TypeError, ValueError):
        return ""


def build_project_context(fl_state: dict) -> str:
    """Return a formatted string describing the current FL Studio project state.
    Returns an empty string when no project is loaded or fl_state is empty.
    """
    project = fl_state.get("project") or {}
    if not project:
        return ""

    lines = []

    # Header
    title  = project.get("title") or "Untitled"
    author = project.get("author") or ""
    genre  = project.get("genre") or ""
    state  = "playing" if project.get("playing") else "stopped"
    parts  = [f"Project: {title}"]
    if author: parts.append(f"by {author}")
    if genre:  parts.append(f"[{genre}]")
    parts.append(f"| {state}")
    lines.append("FL STUDIO PROJECT CONTEXT")
    lines.append(" — ".join(parts))
    lines.append("")

    # Channels
    channels = project.get("channels") or []
    if channels:
        lines.append(f"Channels ({len(channels)}):")
        for ch in channels[:32]:
            name   = ch.get("name") or f"Ch{ch['index']}"
            plugin = ch.get("plugin") or ""
            vol    = ch.get("volume", "")
            pan    = _pan_str(ch.get("pan", 0))
            route  = ch.get("mixer_track", -1)
            flags  = []
            if ch.get("muted"): flags.append("MUTED")
            if ch.get("solo"):  flags.append("SOLO")
            lines.append(
                f"  [{ch['index']}] {name}"
                + (f" [{plugin}]" if plugin else "")
                + f"  vol={vol}{_db(ch.get('volume_db'))}  pan={pan}"
                + (f" -> Mix{route}" if route and route > 0 else "")
                + (f" ({', '.join(flags)})" if flags else "")
            )
        if len(channels) > 32:
            lines.append(f"  ... {len(channels) - 32} more channels not shown")
        lines.append("")

    # Mixer
    mixer_tracks = project.get("mixer") or []
    active = [m for m in mixer_tracks if m.get("name") or m.get("peak")]
    if active:
        lines.append(f"Mixer ({len(active)} active inserts):")
        for m in active[:24]:
            name  = m.get("name") or f"Insert{m['index']}"
            vol   = m.get("volume", "")
            pan   = _pan_str(m.get("pan", 0))
            peak  = m.get("peak") or 0
            flags = []
            if m.get("muted"): flags.append("MUTED")
            if m.get("solo"):  flags.append("SOLO")
            slots = [s.get("plugin", "") for s in (m.get("slots") or []) if s.get("plugin")]
            lines.append(
                f"  [{m['index']}] {name}"
                + f"  vol={vol}{_db(m.get('volume_db'))}  pan={pan}  peak={peak:.3f}"
                + (f" ({', '.join(flags)})" if flags else "")
                + (f" FX:[{', '.join(slots)}]" if slots else "")
            )
        if len(active) > 24:
            lines.append(f"  ... {len(active) - 24} more inserts not shown")

    return "\n".join(lines)
