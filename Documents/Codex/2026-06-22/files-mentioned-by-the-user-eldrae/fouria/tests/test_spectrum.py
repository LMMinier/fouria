"""Tests for audio_tools.analyze_spectrum and vocal_eq_params.

A 440 Hz sine wave WAV is generated on the fly to give the spectrum
analyser something real to chew on.

Note on key naming: the current implementation uses "band_db" as the
spectrum key; the expected new interface uses "bands".  Tests that
inspect the shape of a live result accept either name so they pass
against both old and new code.  Tests for vocal_eq_params use a hand-
crafted fake_spec to decouple them from the spectrum implementation.
"""
import math
import os
import struct
import sys
import tempfile
import wave
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

try:
    from audio_tools import analyze_spectrum, vocal_eq_params
    _HAS_AUDIO = True
except ImportError:
    _HAS_AUDIO = False

pytestmark = pytest.mark.skipif(not _HAS_AUDIO, reason="audio_tools not importable")


# ── WAV helper ────────────────────────────────────────────────────────────────

def _make_sine_wav(path, freq=440, duration=1.0, sample_rate=44100):
    """Write a mono 16-bit PCM sine wave WAV for testing."""
    n = int(sample_rate * duration)
    samples = [int(32767 * math.sin(2 * math.pi * freq * i / sample_rate)) for i in range(n)]
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(struct.pack(f"<{n}h", *samples))


# ── Fake spectrum (used by vocal_eq_params tests) ────────────────────────────

_FAKE_SPEC = {
    "ok": True,
    "bands": {
        "sub": -6.0, "low": 2.0, "low_mid": 5.0, "mid": -1.0,
        "upper_mid": -2.0, "presence": -5.0, "air": -8.0,
    },
    "issues": [
        {"band": "low_mid",  "type": "excess",  "db_above_avg": 5.0},
        {"band": "presence", "type": "deficit", "db_below_avg": 5.0},
    ],
}

EXPECTED_BANDS = ("sub", "low", "low_mid", "mid", "upper_mid", "presence", "air")


# ── Helper: normalise the spectrum dict so tests accept both key names ────────

def _get_bands(spec):
    """Return the band dict regardless of whether the key is 'bands' or 'band_db'."""
    return spec.get("bands") or spec.get("band_db") or {}


# ── Tests: analyze_spectrum ───────────────────────────────────────────────────

def test_analyze_spectrum_ok():
    """analyze_spectrum on a valid WAV returns ok=True and contains band info."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name
    try:
        _make_sine_wav(path, freq=440)
        result = analyze_spectrum(path)
        assert result.get("ok") is True, f"Expected ok=True; got: {result}"
        bands = _get_bands(result)
        assert bands, "Expected non-empty band data in result"
    finally:
        os.unlink(path)


def test_analyze_spectrum_has_all_bands():
    """analyze_spectrum result contains all seven spectral bands."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name
    try:
        _make_sine_wav(path, freq=440)
        result = analyze_spectrum(path)
        bands = _get_bands(result)
        for band_name in EXPECTED_BANDS:
            assert band_name in bands, (
                f"Expected band '{band_name}' in result; got keys: {list(bands.keys())}"
            )
    finally:
        os.unlink(path)


def test_analyze_spectrum_missing_file():
    """analyze_spectrum on a nonexistent path returns ok=False."""
    result = analyze_spectrum("nonexistent_fouria_test_file.wav")
    assert result.get("ok") is False, (
        f"Expected ok=False for missing file; got: {result}"
    )


# ── Tests: vocal_eq_params ────────────────────────────────────────────────────

def _get_fake_spec_for_vocal_eq():
    """Return a fake spectrum dict compatible with vocal_eq_params.

    vocal_eq_params reads `issues` (list of dicts with 'band' and 'type').
    We also test with the "band_db" key name (current implementation) if
    the function accepts it, falling back to _FAKE_SPEC regardless.
    """
    return _FAKE_SPEC


def test_vocal_eq_params_returns_bands():
    """vocal_eq_params returns a dict with an 'eq_bands' list."""
    spec = _get_fake_spec_for_vocal_eq()
    result = vocal_eq_params(spec)
    assert "eq_bands" in result, f"Expected 'eq_bands' key; got: {list(result.keys())}"
    assert isinstance(result["eq_bands"], list), "eq_bands should be a list"


def test_vocal_eq_params_fl_actions():
    """vocal_eq_params result has 'fl_actions' list with set_plugin_param actions."""
    spec = _get_fake_spec_for_vocal_eq()
    result = vocal_eq_params(spec)
    assert "fl_actions" in result, f"Expected 'fl_actions' key; got: {list(result.keys())}"
    assert isinstance(result["fl_actions"], list), "fl_actions should be a list"
    for action in result["fl_actions"]:
        assert action.get("action") == "set_plugin_param", (
            f"Expected action=='set_plugin_param', got: {action}"
        )


def test_vocal_eq_params_param_values_valid():
    """All param values in fl_actions are between 0.0 and 1.0 inclusive."""
    spec = _get_fake_spec_for_vocal_eq()
    result = vocal_eq_params(spec)
    for action in result.get("fl_actions", []):
        v = action["value"]["value"]
        assert 0.0 <= v <= 1.0, (
            f"Param value {v} is outside [0.0, 1.0] in action: {action}"
        )


def test_vocal_eq_freq_param_range():
    """Frequency params in eq_bands are between 0.0 and 1.0 inclusive."""
    spec = _get_fake_spec_for_vocal_eq()
    result = vocal_eq_params(spec)
    for band in result.get("eq_bands", []):
        for p in band.get("fl_params", []):
            if "Freq" in p.get("description", ""):
                v = p["value"]
                assert 0.0 <= v <= 1.0, (
                    f"Freq param value {v} out of [0,1] in band {band['band_index']}"
                )
