import re


def _resolve_named(items, phrase):
    phrase = phrase.lower()
    matches = []
    for item in items:
        name = str(item.get("name", "")).strip()
        if name and name.lower() in phrase:
            matches.append(item)
    return max(matches, key=lambda item: len(str(item.get("name", ""))), default=None)


def plan_request(text, project):
    phrase = " ".join(str(text or "").lower().split())
    channels = project.get("channels") or []
    mixer = project.get("mixer") or []
    actions, notes = [], []
    intent = "production_help"

    if any(word in phrase for word in ("organize", "route everything", "set up mixer", "clean up project")):
        intent = "organize_project"
        actions.append({"action": "organize_project", "value": {}})
        notes.append("Routes channels to unique mixer inserts and mirrors channel names.")

    if any(word in phrase for word in ("gain stage", "gainstage", "initial mix", "rough mix")):
        intent = "gain_stage_mix"
        actions.append({"action": "gain_stage_mix", "value": {}})
        notes.append("Creates a conservative role-based static balance; this is not a finished audible mix.")

    mixer_target = _resolve_named(mixer, phrase)
    channel_target = _resolve_named(channels, phrase)
    number = re.search(r"(-?\d+(?:\.\d+)?)\s*%", phrase)

    if mixer_target and "mute" in phrase:
        actions.append({"action": "mute_mixer", "value": {"index": mixer_target["index"], "enabled": True}})
        intent = "mixer_edit"
    elif mixer_target and "solo" in phrase:
        actions.append({"action": "solo_mixer", "value": {"index": mixer_target["index"], "enabled": True}})
        intent = "mixer_edit"
    elif mixer_target and "pan" in phrase:
        pan = -0.35 if "left" in phrase else 0.35 if "right" in phrase else 0
        actions.append({"action": "set_mixer_pan", "value": {"index": mixer_target["index"], "pan": pan}})
        intent = "mixer_edit"
    elif mixer_target and number and any(word in phrase for word in ("volume", "level", "fader")):
        actions.append({"action": "set_mixer_volume", "value": {
            "index": mixer_target["index"], "volume": max(0, min(1, float(number.group(1)) / 100))
        }})
        intent = "mixer_edit"
    elif channel_target and "quantize" in phrase:
        actions.append({"action": "quantize_channel", "value": {"index": channel_target["index"], "start_only": True}})
        intent = "channel_edit"

    if "open mixer" in phrase:
        actions.append({"action": "show_mixer", "value": {}})
    if "open playlist" in phrase:
        actions.append({"action": "show_playlist", "value": {}})
    if "open piano roll" in phrase:
        actions.append({"action": "show_piano_roll", "value": {}})

    return {
        "ok": True, "intent": intent, "request": text, "actions": actions,
        "notes": notes, "requires_fl_bridge": bool(actions),
        "verification": "Each native action returns a bridge result and appears in the next project snapshot.",
    }
