"""Scans and indexes the user's FL Studio sample library and plugin presets.

Writes a JSON index to data/library_index.json.
The index is loaded into context so FOURIA knows what sounds are available.
"""
import json
import os
import winreg
from pathlib import Path


# ── FL Studio path detection ──────────────────────────────────────────────────

def _fl_install_path() -> Path | None:
    """Read FL Studio install path from Windows registry."""
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Image-Line\FL Studio 21"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Image-Line\FL Studio 20"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Image-Line\FL Studio 21"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Image-Line\FL Studio 20"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Image-Line\FL Studio 21"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Image-Line\FL Studio 20"),
    ]
    for hive, key_path in registry_keys:
        try:
            with winreg.OpenKey(hive, key_path) as k:
                value, _ = winreg.QueryValueEx(k, "Install_Dir")
                p = Path(str(value))
                if p.exists():
                    return p
        except (FileNotFoundError, OSError):
            continue
    # Fallback: common install paths
    for candidate in [
        Path(r"C:\Program Files\Image-Line\FL Studio 21"),
        Path(r"C:\Program Files\Image-Line\FL Studio 20"),
        Path(r"C:\Program Files (x86)\Image-Line\FL Studio 21"),
    ]:
        if candidate.exists():
            return candidate
    return None


def _fl_user_data_path() -> Path:
    """Return the FL Studio user data folder (Documents/Image-Line/FL Studio)."""
    docs = Path(os.path.expanduser("~")) / "Documents" / "Image-Line" / "FL Studio"
    return docs


# ── Scanner ───────────────────────────────────────────────────────────────────

SAMPLE_EXTENSIONS = {".wav", ".flac", ".mp3", ".aiff", ".ogg"}
PRESET_EXTENSIONS = {".fst", ".fxp", ".nmsv", ".vital", ".xpf"}

def _scan_samples(roots: list[Path], max_files: int = 5000) -> list[dict]:
    seen = set()
    results = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("*"):
                if path.suffix.lower() not in SAMPLE_EXTENSIONS:
                    continue
                key = path.stem.lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    results.append({
                        "name": path.stem,
                        "path": str(path),
                        "ext":  path.suffix.lower(),
                        "size_kb": round(path.stat().st_size / 1024, 1),
                        "role": _guess_role(path.stem),
                    })
                except Exception:
                    continue
                if len(results) >= max_files:
                    return results
        except Exception:
            continue
    return results


def _guess_role(name: str) -> str:
    n = name.lower()
    if any(w in n for w in ("kick", " bd ", "_bd_", "-bd-", "bassdrum", "bass drum")): return "kick"
    if any(w in n for w in ("snare", " sd ", "_sd_", "rimshot", "rim ")): return "snare"
    if any(w in n for w in ("hat", "hihat", "hi-hat", "cymbal", "hh", "open", "closed")): return "hat"
    if any(w in n for w in ("808", "sub", "bass")): return "808"
    if any(w in n for w in ("clap", "clp")): return "clap"
    if any(w in n for w in ("perc", "shaker", "tamb", "conga", "bongo", "tom")): return "perc"
    if any(w in n for w in ("vocal", "vox", "voice", "chant", "ad lib")): return "vocal"
    if any(w in n for w in ("pad", "atmo", "texture", "ambient", "drone")): return "pad"
    if any(w in n for w in ("lead", "melody", "synth", "pluck", "keys", "piano", "bell")): return "melodic"
    if any(w in n for w in ("chord", "stab", "brass", "strings")): return "chord"
    return "other"


def _scan_presets(roots: list[Path]) -> list[dict]:
    results = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("*"):
                if path.suffix.lower() not in PRESET_EXTENSIONS:
                    continue
                results.append({
                    "name":   path.stem,
                    "plugin": path.parent.name,
                    "path":   str(path),
                    "ext":    path.suffix.lower(),
                })
                if len(results) >= 2000:
                    return results
        except Exception:
            continue
    return results


# ── Main index builder ────────────────────────────────────────────────────────

def build_library_index(output_path: Path) -> dict:
    """Scan the FL Studio library and write index to output_path. Returns the index."""
    fl_install = _fl_install_path()
    fl_user    = _fl_user_data_path()

    sample_roots = []
    preset_roots = []

    if fl_install:
        sample_roots.append(fl_install / "Data" / "Patches" / "Packs")
        sample_roots.append(fl_install / "Data" / "Patches" / "Samples")
        preset_roots.append(fl_install / "Data" / "Patches" / "Presets")

    sample_roots.append(fl_user / "Samples")
    sample_roots.append(fl_user / "Presets" / "Projects")
    preset_roots.append(fl_user / "Presets")

    # Also scan common VST preset locations
    vst_presets = Path(os.path.expanduser("~")) / "Documents" / "VST3 Presets"
    if vst_presets.exists():
        preset_roots.append(vst_presets)

    samples = _scan_samples(sample_roots)
    presets = _scan_presets(preset_roots)

    # Summary by role
    role_counts = {}
    for s in samples:
        role_counts[s["role"]] = role_counts.get(s["role"], 0) + 1

    index = {
        "fl_install":  str(fl_install) if fl_install else None,
        "fl_user":     str(fl_user),
        "sample_count": len(samples),
        "preset_count": len(presets),
        "role_counts":  role_counts,
        "samples":      samples,
        "presets":      presets,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index


def load_library_index(index_path: Path) -> dict | None:
    """Load existing index from disk. Returns None if not found."""
    if not index_path.exists():
        return None
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_sample(role: str, index: dict) -> str | None:
    """Find the best sample for a given role from the index."""
    for s in index.get("samples", []):
        if s["role"] == role:
            return s["path"]
    return None


def library_context_block(index: dict) -> str:
    """Return a short context string for the system prompt."""
    if not index:
        return ""
    lines = [f"User FL Studio library: {index['sample_count']} samples, {index['preset_count']} presets."]
    rc = index.get("role_counts", {})
    if rc:
        parts = ", ".join(f"{v} {k}" for k, v in rc.items() if v and k != "other")
        if parts:
            lines.append(f"Samples by role: {parts}.")
    if index.get("fl_install"):
        lines.append(f"FL Studio install: {index['fl_install']}")
    return "\n".join(lines)


# ── Module-level active index (shared singleton) ──────────────────────────────

_CACHED_INDEX: dict = {}


def set_active_index(index: dict):
    global _CACHED_INDEX
    _CACHED_INDEX = index


def get_active_index() -> dict:
    return _CACHED_INDEX
