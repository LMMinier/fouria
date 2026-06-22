import re


def _resolve_named(items, phrase):
    phrase = phrase.lower()
    matches = []
    for item in items:
        name = str(item.get("name", "")).strip()
        if name and name.lower() in phrase:
            matches.append(item)
    return max(matches, key=lambda item: len(str(item.get("name", ""))), default=None)


def _pan_value(phrase):
    """Return a pan float from phrase modifiers."""
    if any(w in phrase for w in ("hard", "full", "100%", "all the way")):
        return 1.0 if "right" in phrase else -1.0
    if any(w in phrase for w in ("slightly", "a bit", "little", "subtle", "gently")):
        return 0.15 if "right" in phrase else -0.15
    if any(w in phrase for w in ("moderate", "medium", "halfway")):
        return 0.6 if "right" in phrase else -0.6
    # default moderate push
    return 0.35 if "right" in phrase else -0.35


def plan_request(text, project):
    phrase   = " ".join(str(text or "").lower().split())
    channels = project.get("channels") or []
    mixer    = project.get("mixer")    or []
    actions, notes = [], []
    intent = "production_help"

    # ── Global project operations (independent of named-track resolution) ────
    if any(w in phrase for w in ("organize", "route everything", "set up mixer", "clean up project")):
        intent = "organize_project"
        actions.append({"action": "organize_project", "value": {}})
        notes.append("Routes channels to unique mixer inserts and mirrors channel names.")

    if any(w in phrase for w in ("gain stage", "gainstage", "initial mix", "rough mix")):
        intent = "gain_stage_mix"
        actions.append({"action": "gain_stage_mix", "value": {}})
        notes.append("Creates a conservative role-based static balance — not a finished audible mix.")

    # ── Named-track operations ───────────────────────────────────────────────
    mixer_target   = _resolve_named(mixer,    phrase)
    channel_target = _resolve_named(channels, phrase)
    number         = re.search(r"(-?\d+(?:\.\d+)?)\s*%", phrase)

    if mixer_target:
        if "mute" in phrase:
            actions.append({"action": "mute_mixer",
                            "value": {"index": mixer_target["index"], "enabled": True}})
            intent = "mixer_edit"

        if "solo" in phrase:
            actions.append({"action": "solo_mixer",
                            "value": {"index": mixer_target["index"], "enabled": True}})
            intent = "mixer_edit"

        if "pan" in phrase and any(d in phrase for d in ("left", "right", "center", "centre")):
            if "center" in phrase or "centre" in phrase:
                pan = 0.0
            else:
                pan = _pan_value(phrase)
            actions.append({"action": "set_mixer_pan",
                            "value": {"index": mixer_target["index"], "pan": pan}})
            intent = "mixer_edit"

        if number and any(w in phrase for w in ("volume", "level", "fader")):
            actions.append({"action": "set_mixer_volume",
                            "value": {
                                "index":  mixer_target["index"],
                                "volume": max(0.0, min(1.0, float(number.group(1)) / 100)),
                            }})
            intent = "mixer_edit"

    if channel_target:
        if "quantize" in phrase:
            actions.append({"action": "quantize_channel",
                            "value": {"index": channel_target["index"], "start_only": True}})
            intent = "channel_edit"

        if "mute" in phrase:
            actions.append({"action": "mute_channel",
                            "value": {"index": channel_target["index"], "enabled": True}})
            intent = "channel_edit"

        if "solo" in phrase:
            actions.append({"action": "solo_channel",
                            "value": {"index": channel_target["index"], "enabled": True}})
            intent = "channel_edit"

    # ── Window commands (always append if mentioned) ─────────────────────────
    if "open mixer" in phrase:
        actions.append({"action": "show_mixer", "value": {}})
    if "open playlist" in phrase:
        actions.append({"action": "show_playlist", "value": {}})
    if "open piano roll" in phrase:
        actions.append({"action": "show_piano_roll", "value": {}})
    if "open channel rack" in phrase or "open step sequencer" in phrase:
        actions.append({"action": "show_channel_rack", "value": {}})

    return {
        "ok":                True,
        "intent":            intent,
        "request":           text,
        "actions":           actions,
        "notes":             notes,
        "requires_fl_bridge": bool(actions),
        "verification":      "Each native action returns a bridge result and appears in the next project snapshot.",
    }
