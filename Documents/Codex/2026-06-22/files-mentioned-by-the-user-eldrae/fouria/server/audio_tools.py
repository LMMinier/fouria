import math
import struct
import wave
from pathlib import Path


def analyze_wav(path: str) -> dict:
    target = Path(path)
    if not target.exists():
        return {"ok": False, "error": "file not found", "path": str(target)}
    try:
        with wave.open(str(target), "rb") as audio:
            channels = audio.getnchannels()
            width = audio.getsampwidth()
            rate = audio.getframerate()
            frames = audio.getnframes()
            if width not in (1, 2, 3, 4):
                return {"ok": False, "error": f"unsupported sample width: {width}"}
            raw = audio.readframes(frames)
    except (wave.Error, OSError) as exc:
        return {"ok": False, "error": str(exc), "path": str(target)}

    maximum = float((1 << (width * 8 - 1)) - 1)
    samples = []
    if width == 1:
        samples = [(v - 128) / 127.0 for v in raw]
    elif width == 2:
        samples = [v / maximum for v in struct.unpack("<" + "h" * (len(raw) // 2), raw)]
    elif width == 4:
        samples = [v / maximum for v in struct.unpack("<" + "i" * (len(raw) // 4), raw)]
    else:
        for i in range(0, len(raw) - 2, 3):
            value = int.from_bytes(raw[i:i+3], "little", signed=True)
            samples.append(value / maximum)
    if not samples:
        return {"ok": False, "error": "audio has no samples"}

    peak = max(abs(v) for v in samples)
    rms = math.sqrt(sum(v*v for v in samples) / len(samples))
    mean = sum(samples) / len(samples)
    clipped = sum(1 for v in samples if abs(v) >= 0.999)
    crest = 20 * math.log10(max(peak, 1e-12) / max(rms, 1e-12))
    result = {
        "ok": True, "path": str(target), "channels": channels, "sample_rate": rate,
        "bit_depth": width * 8, "duration_seconds": round(frames / rate, 3),
        "peak_dbfs": round(20 * math.log10(max(peak, 1e-12)), 2),
        "rms_dbfs": round(20 * math.log10(max(rms, 1e-12)), 2),
        "crest_factor_db": round(crest, 2), "dc_offset": round(mean, 6),
        "clipped_samples": clipped,
    }
    advice = []
    if clipped:
        advice.append("Clipped samples detected. Lower gain before limiting or rendering.")
    if result["peak_dbfs"] > -1:
        advice.append("Peak is above -1 dBFS; leave more true-peak safety for delivery.")
    if abs(mean) > 0.01:
        advice.append("Noticeable DC offset detected; correct it before dynamics processing.")
    if crest < 6:
        advice.append("Low crest factor suggests heavy density/limiting; check transient loss.")
    if result["rms_dbfs"] < -24:
        advice.append("Low average level; inspect gain staging before adding a limiter.")
    result["advice"] = advice or ["Basic level metrics look usable; continue with spectral and reference checks."]
    return result


def mix_plan(style="modern", target="full beat") -> dict:
    return {
        "ok": True, "type": "mix_plan", "style": style, "target": target,
        "stages": [
            {"stage": "prep", "actions": ["name and route channels", "remove unused audio", "set static balance", "preserve headroom"]},
            {"stage": "low_end", "actions": ["tune bass/808", "resolve kick-bass timing", "check mono", "remove non-musical sub energy"]},
            {"stage": "tone", "actions": ["correct source problems", "EQ only audible conflicts", "control harshness and mud"]},
            {"stage": "dynamics", "actions": ["shape envelopes", "compress for a defined reason", "preserve groove and punch"]},
            {"stage": "space", "actions": ["establish front/back depth", "use sends", "filter effects returns", "automate transitions"]},
            {"stage": "translation", "actions": ["level-match references", "check low volume", "check mono/headphones/speakers", "render test"]},
        ],
        "verification_required": True,
    }


def master_plan(style="modern", delivery="streaming") -> dict:
    return {
        "ok": True, "type": "master_plan", "style": style, "delivery": delivery,
        "stages": [
            "verify mix headroom and clipping", "level-match references", "make small broad tonal corrections",
            "control only problematic dynamics", "add density/saturation if needed",
            "limit while monitoring transients and distortion", "check mono, codec, and true-peak safety",
            "export archival and delivery versions",
        ],
        "targets": {"true_peak_ceiling_db": -1.0, "loudness": "genre- and delivery-dependent; do not normalize by guess"},
        "verification_required": True,
    }
