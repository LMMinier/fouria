import ctypes
import os
import subprocess
import time
import tkinter as tk

user32 = ctypes.windll.user32
SW_RESTORE = 9
KEYUP = 2
VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "enter": 0x0D, "esc": 0x1B, "space": 0x20,
      "f7": 0x76, "f8": 0x77, "f10": 0x79, "v": 0x56}

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

def focus_fl():
    found = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if handle:
            try:
                size = ctypes.c_ulong(1024)
                path = ctypes.create_unicode_buffer(size.value)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                    if os.path.basename(path.value).lower() == "fl64.exe":
                        found.append(hwnd)
                        return False
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        return True
    user32.EnumWindows(callback, 0)
    if not found:
        raise RuntimeError("FL Studio window not found")
    user32.ShowWindow(found[0], SW_RESTORE)
    user32.SetForegroundWindow(found[0])
    time.sleep(.5)

def key(name, up=False):
    code = VK.get(name.lower())
    if code is None and len(name) == 1:
        code = ord(name.upper())
    if code is None:
        raise ValueError(f"unknown key: {name}")
    user32.keybd_event(code, 0, KEYUP if up else 0, 0)

def press(name):
    key(name); key(name, True); time.sleep(.15)

def hotkey(*names):
    for name in names: key(name)
    for name in reversed(names): key(name, True)
    time.sleep(.2)

def paste(text):
    root = tk.Tk(); root.withdraw()
    root.clipboard_clear(); root.clipboard_append(text); root.update()
    hotkey("ctrl", "v")
    root.update(); time.sleep(.2); root.destroy()

def build_in_fl(midi_path, plugin="Omnisphere"):
    steps = []
    if not os.path.isfile(midi_path):
        raise RuntimeError(f"generated MIDI is missing: {midi_path}")
    focus_fl()
    steps.append("focused FL64.exe")
    user = os.environ.get("USERPROFILE", "")
    preset = os.path.join(user, "Documents", "Image-Line", "FL Studio", "Presets",
                          "Plugin database", "Generators", "synth", plugin + ".fst")
    fl_exe = r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe"
    if not os.path.isfile(preset):
        raise RuntimeError(f"{plugin} preset is not in FL's Plugin Database")
    subprocess.Popen([fl_exe, preset])
    steps.append(f"loaded {plugin} preset into FL")
    # Omnisphere can take several seconds to finish creating its channel.
    time.sleep(15)
    focus_fl()
    press("esc")
    time.sleep(.5)
    press("f7")
    steps.append("opened Piano Roll")
    time.sleep(1)
    hotkey("ctrl", "m")
    steps.append("opened Import MIDI")
    time.sleep(1)
    paste(midi_path)
    steps.append("entered generated MIDI path")
    press("enter")
    time.sleep(1.5)
    press("enter")
    steps.append("confirmed MIDI import")
    time.sleep(1)
    return steps
