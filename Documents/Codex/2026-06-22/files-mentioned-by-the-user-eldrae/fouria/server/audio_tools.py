import cmath
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


def _fft(samples):
    """Cooley-Tukey FFT — input length must be a power of 2."""
    n = len(samples)
    if n <= 1:
        return [complex(s) for s in samples]
    even = _fft(samples[0::2])
    odd  = _fft(samples[1::2])
    T = [cmath.exp(-2j * cmath.pi * k / n) * odd[k] for k in range(n // 2)]
    return [even[k] + T[k] for k in range(n // 2)] + [even[k] - T[k] for k in range(n // 2)]


def analyze_spectrum(path: str) -> dict:
    """Octave-band spectral analysis of a WAV file using a stdlib FFT."""
    target_path = Path(path)
    if not target_path.exists():
        return {"ok": False, "error": "file not found", "path": str(target_path)}
    try:
        with wave.open(str(target_path), "rb") as audio:
            channels = audio.getnchannels()
            width    = audio.getsampwidth()
            rate     = audio.getframerate()
            frames   = audio.getnframes()
            if width not in (1, 2, 3, 4):
                return {"ok": False, "error": f"unsupported sample width: {width}"}
            raw = audio.readframes(frames)
    except (wave.Error, OSError) as exc:
        return {"ok": False, "error": str(exc), "path": str(target_path)}

    maximum = float((1 << (width * 8 - 1)) - 1)
    if width == 1:
        raw_samples = [(v - 128) / 127.0 for v in raw]
    elif width == 2:
        raw_samples = [v / maximum for v in struct.unpack("<" + "h" * (len(raw) // 2), raw)]
    elif width == 4:
        raw_samples = [v / maximum for v in struct.unpack("<" + "i" * (len(raw) // 4), raw)]
    else:
        raw_samples = []
        for i in range(0, len(raw) - 2, 3):
            value = int.from_bytes(raw[i:i+3], "little", signed=True)
            raw_samples.append(value / maximum)

    if not raw_samples:
        return {"ok": False, "error": "audio has no samples"}

    # Mono downmix
    if channels > 1:
        mono = [
            sum(raw_samples[i + c] for c in range(channels)) / channels
            for i in range(0, len(raw_samples) - channels + 1, channels)
        ]
    else:
        mono = raw_samples

    # Downsample to at most 48000 samples for speed
    if len(mono) > 48000:
        step = len(mono) // 48000
        mono = mono[::step]

    window_size = 4096

    # Take middle window; pad with zeros if needed
    mid    = len(mono) // 2
    half_w = window_size // 2
    start  = max(0, mid - half_w)
    window = mono[start: start + window_size]
    if len(window) < window_size:
        window = window + [0.0] * (window_size - len(window))

    # Hann window
    hann     = [0.5 - 0.5 * math.cos(2 * math.pi * i / (window_size - 1)) for i in range(window_size)]
    windowed = [window[i] * hann[i] for i in range(window_size)]

    # FFT
    spectrum = _fft(windowed)

    # Compute per-bin magnitude-squared (only positive frequencies needed)
    mag2 = [abs(spectrum[k]) ** 2 for k in range(window_size // 2)]

    # Band definitions (Hz)
    BANDS = {
        "sub":       (20,   80),
        "low":       (80,   200),
        "low_mid":   (200,  800),
        "mid":       (800,  2500),
        "upper_mid": (2500, 5000),
        "presence":  (5000, 10000),
        "air":       (10000, 20000),
    }

    band_energy = {}
    for band_name, (f_lo, f_hi) in BANDS.items():
        bin_lo = max(1, int(f_lo * window_size / rate))
        bin_hi = min(window_size // 2 - 1, int(f_hi * window_size / rate))
        if bin_lo > bin_hi:
            band_energy[band_name] = 0.0
            continue
        energy = sum(mag2[k] for k in range(bin_lo, bin_hi + 1))
        count  = bin_hi - bin_lo + 1
        band_energy[band_name] = energy / count

    # Convert to dBFS relative to average across all bands
    avg_energy = sum(band_energy.values()) / len(band_energy)
    if avg_energy <= 0:
        avg_energy = 1e-30

    band_db = {}
    for name, energy in band_energy.items():
        band_db[name] = round(10 * math.log10(max(energy, 1e-30) / avg_energy), 2)

    issues = []
    for name, db in band_db.items():
        if db > 4:
            issues.append({"band": name, "type": "excess", "db": db})
        elif db < -4:
            issues.append({"band": name, "type": "deficit", "db": db})

    return {
        "ok":          True,
        "path":        str(target_path),
        "sample_rate": rate,
        "channels":    channels,
        "band_db":     band_db,
        "issues":      issues,
    }


def _freq_to_param(freq_hz: float) -> float:
    """Map Hz to Parametric EQ 2 freq param (0–1, log scale 10–20000 Hz)."""
    lo = math.log10(10)
    hi = math.log10(20000)
    return max(0.0, min(1.0, (math.log10(max(freq_hz, 10)) - lo) / (hi - lo)))


def _gain_to_param(gain_db: float) -> float:
    """Map dB gain to param (0.5 = 0dB, range -24 to +24)."""
    return max(0.0, min(1.0, (gain_db + 24) / 48))


def vocal_eq_params(spectrum_result: dict) -> dict:
    """Map analyze_spectrum output to Parametric EQ 2 band adjustments."""
    issues = {i["band"]: i for i in spectrum_result.get("issues", [])}

    # EQ type param values
    TYPE_LP    = 0.0
    TYPE_HP    = 0.17
    TYPE_LS    = 0.33
    TYPE_HS    = 0.5
    TYPE_PEAK  = 1.0

    eq_bands  = []
    fl_actions = []
    band_idx   = 0

    def add_band(description, freq_hz, gain_db, bw_param, type_param):
        nonlocal band_idx
        if band_idx >= 7:
            return
        b = band_idx
        fp   = _freq_to_param(freq_hz)
        gp   = _gain_to_param(gain_db)
        params = [
            {"param": b*4+0, "value": round(fp,   4), "description": f"Freq: {freq_hz}Hz"},
            {"param": b*4+1, "value": round(bw_param, 4), "description": "BW"},
            {"param": b*4+2, "value": round(gp,   4), "description": f"Gain: {gain_db}dB"},
            {"param": b*4+3, "value": round(type_param, 4), "description": f"Type param"},
        ]
        eq_bands.append({
            "band_index":  b,
            "description": description,
            "fl_params":   params,
        })
        for p in params:
            fl_actions.append({
                "action": "set_plugin_param",
                "value": {
                    "index": "__CHANNEL__",
                    "slot":  -1,
                    "param": p["param"],
                    "value": p["value"],
                },
            })
        band_idx += 1

    # Always add a high-pass on band 0 if there's sub excess, else add a gentle HP anyway
    if "sub" in issues and issues["sub"]["type"] == "excess":
        add_band("High-pass at 80Hz to remove sub rumble", 80, 0.0, 0.5, TYPE_HP)
    else:
        add_band("High-pass at 40Hz to protect sub shelf", 40, 0.0, 0.5, TYPE_HP)

    if "low" in issues:
        t = issues["low"]["type"]
        gain = -4.0 if t == "excess" else 2.0
        add_band(f"Low band {'cut' if t=='excess' else 'boost'} at 140Hz", 140, gain, 0.5, TYPE_PEAK)

    if "low_mid" in issues:
        t = issues["low_mid"]["type"]
        gain = -3.0 if t == "excess" else 2.0
        add_band(f"Low-mid {'cut' if t=='excess' else 'boost'} at 400Hz (mud control)", 400, gain, 0.5, TYPE_PEAK)

    if "mid" in issues:
        t = issues["mid"]["type"]
        gain = -2.5 if t == "excess" else 2.0
        add_band(f"Mid {'cut' if t=='excess' else 'boost'} at 1.5kHz (nasality)", 1500, gain, 0.6, TYPE_PEAK)

    if "upper_mid" in issues:
        t = issues["upper_mid"]["type"]
        gain = -3.0 if t == "excess" else 2.0
        add_band(f"Upper-mid {'cut' if t=='excess' else 'boost'} at 6kHz (de-ess area)", 6000, gain, 0.65, TYPE_PEAK)

    if "presence" in issues:
        t = issues["presence"]["type"]
        gain = -2.0 if t == "excess" else 2.5
        add_band(f"Presence {'cut' if t=='excess' else 'boost'} at 4kHz", 4000, gain, 0.5, TYPE_PEAK)

    if "air" in issues:
        t = issues["air"]["type"]
        gain = -2.0 if t == "excess" else 2.0
        add_band(f"Air high-shelf {'cut' if t=='excess' else 'boost'} at 10kHz", 10000, gain, 0.5, TYPE_HS)

    return {
        "ok":       True,
        "type":     "vocal_eq",
        "issues":   spectrum_result.get("issues", []),
        "eq_bands": eq_bands,
        "fl_actions": fl_actions,
        "note": (
            "Apply these to a Parametric EQ 2 on the vocal mixer insert. "
            "Verify by ear — spectral analysis is diagnostic, not prescriptive."
        ),
    }


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
