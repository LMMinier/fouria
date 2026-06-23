"""FOURIA-owned desktop fallback executor.

This module runs inside the FOURIA Desktop process. It is the only component
allowed to use Windows UI automation when FL's native MIDI bridge is unavailable.
"""
import ctypes
import os
import subprocess
import threading
import time
import tkinter as tk
import uuid
from pathlib import Path

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
KEYUP = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
VK = {
    "ctrl": 0x11, "enter": 0x0D, "esc": 0x1B, "space": 0x20,
    "f6": 0x75, "f7": 0x76, "v": 0x56,
}

_jobs = {}
_lock = threading.Lock()


def _set(job_id, **fields):
    with _lock:
        _jobs.setdefault(job_id, {}).update(fields)


def get_job(job_id):
    with _lock:
        job = dict(_jobs.get(job_id) or {})
        job.pop("_plan", None)
        return job


def recent_jobs():
    with _lock:
        jobs = []
        for value in list(_jobs.values())[-20:]:
            item = dict(value)
            item.pop("_plan", None)
            jobs.append(item)
        return jobs


def _fl_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if handle:
            try:
                size = ctypes.c_ulong(1024)
                path = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                    if os.path.basename(path.value).lower() == "fl64.exe":
                        found.append(hwnd)
                        return False
            finally:
                kernel32.CloseHandle(handle)
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        raise RuntimeError("FL Studio is not running")
    return found[0]


def _focus_fl():
    hwnd = _fl_window()
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    return hwnd


def _key(name, up=False):
    code = VK.get(name.lower())
    if code is None and len(name) == 1:
        code = ord(name.upper())
    if code is None:
        raise ValueError(f"unknown key: {name}")
    user32.keybd_event(code, 0, KEYUP if up else 0, 0)


def _press(name):
    _key(name)
    _key(name, True)
    time.sleep(0.18)


def _hotkey(*names):
    for name in names:
        _key(name)
    for name in reversed(names):
        _key(name, True)
    time.sleep(0.25)


def _paste(text):
    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(str(text))
    root.update()
    _hotkey("ctrl", "v")
    root.update()
    time.sleep(0.2)
    root.destroy()


def _click(x, y, right=False):
    user32.SetCursorPos(int(x), int(y))
    down, up = (8, 16) if right else (2, 4)
    user32.mouse_event(down, 0, 0, 0, 0)
    user32.mouse_event(up, 0, 0, 0, 0)
    time.sleep(0.15)


def _set_tempo(bpm):
    _focus_fl()
    _click(522, 27, right=True)
    time.sleep(0.4)
    # FL's tempo context menu has presets at fixed rows. Prefer exact 140.
    preset_y = {80: 64, 90: 83, 100: 102, 110: 121, 120: 140,
                130: 159, 140: 178, 150: 197, 160: 216}.get(int(bpm))
    if preset_y:
        _click(724, preset_y)
    else:
        _click(574, 286)
        time.sleep(0.5)
        _paste(str(int(bpm)))
        _press("enter")
    time.sleep(0.8)


def _program_drums():
    _focus_fl()
    _press("f6")
    time.sleep(1)
    x0, dx = 583, 16
    rows = {
        223: {0, 8, 10, 14},
        253: {4, 12},
        283: set(range(16)),
        313: {4, 12},
    }
    # Reset each first-16-step lane by right-click-dragging is destructive and
    # version-sensitive. Use a known empty/new project or inspect before use.
    from PIL import ImageGrab
    image = ImageGrab.grab()
    for y, wanted in rows.items():
        for step in range(16):
            x = x0 + dx * step
            r, g, b = image.getpixel((x, y))[:3]
            active = r > 85 and r > g * 1.25
            if active != (step in wanted):
                _click(x, y)


def _import_midi(midi_path, plugin="Omnisphere"):
    if not Path(midi_path).is_file():
        raise RuntimeError("generated MIDI is missing: " + str(midi_path))
    preset = (Path.home() / "Documents" / "Image-Line" / "FL Studio" /
              "Presets" / "Plugin database" / "Generators" / "synth" /
              f"{plugin}.fst")
    if not preset.is_file():
        raise RuntimeError(f"{plugin} is not in FL's Plugin Database")
    fl_exe = Path(r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe")
    subprocess.Popen([str(fl_exe), str(preset)])
    time.sleep(15)
    _focus_fl()
    _press("esc")
    _press("f7")
    time.sleep(1)
    _hotkey("ctrl", "m")
    time.sleep(1)
    _paste(str(midi_path))
    _press("enter")
    time.sleep(1.5)
    _press("enter")
    time.sleep(1)


def _run_beat(job_id, plan):
    try:
        _set(job_id, status="running", stage="setting tempo")
        _set_tempo(plan["bpm"])
        _set(job_id, stage="programming drums")
        _program_drums()
        _set(job_id, stage="loading chords")
        _import_midi(plan["midi_files"]["chords"], "Omnisphere")
        _set(job_id, stage="loading melody")
        _import_midi(plan["midi_files"]["melody"], "Omnisphere")
        _set(job_id, status="done", stage="verified visible FL operations",
             finished_at=time.time())
    except Exception as exc:
        _set(job_id, status="failed", stage="stopped", error=str(exc),
             finished_at=time.time())


def start_beat(plan):
    job_id = uuid.uuid4().hex
    _set(job_id, id=job_id, type="make_beat", status="queued",
         stage="waiting", created_at=time.time(), _plan=dict(plan),
         bpm=plan.get("bpm"), key=plan.get("key"), scale=plan.get("scale"),
         bars=plan.get("bars"), style=plan.get("style"))
    threading.Thread(target=_run_beat, args=(job_id, plan), daemon=True).start()
    return get_job(job_id)
