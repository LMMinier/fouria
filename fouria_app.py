"""FOURIA Desktop App: one owner for FL, bridge, server, and UI."""
import csv
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).parent
else:
    BUNDLE_DIR = Path(__file__).resolve().parent
    APP_DIR = BUNDLE_DIR

os.environ["FOURIA_ROOT"] = str(BUNDLE_DIR)
os.environ["FOURIA_DESKTOP_EXECUTOR"] = "1"
sys.path.insert(0, str(BUNDLE_DIR / "server"))

PORT = int(os.environ.get("FOURIA_PORT", "11700"))
URL = f"http://127.0.0.1:{PORT}"
LOG_FILE = APP_DIR / "FOURIA-startup.log"


def _log(message):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def _listener_pids():
    pids = set()
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{PORT}") and parts[3] == "LISTENING":
                pids.add(int(parts[4]))
    except Exception:
        pass
    return pids


def _process_name(pid):
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        rows = list(csv.reader([result.stdout.strip()]))
        return rows[0][0].lower() if rows and rows[0] else ""
    except Exception:
        return ""


def _claim_server_port():
    pids = _listener_pids() - {os.getpid()}
    if not pids:
        return
    for pid in pids:
        name = _process_name(pid)
        if name not in {"python.exe", "pythonw.exe", "fouria.exe"}:
            raise RuntimeError(f"Port {PORT} is occupied by {name or 'another app'} (PID {pid})")
    for pid in pids:
        name = _process_name(pid)
        _log(f"stopping stale FOURIA server: {name} PID {pid}")
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    deadline = time.time() + 8
    while (_listener_pids() - {os.getpid()}) and time.time() < deadline:
        time.sleep(0.2)
    remaining = _listener_pids() - {os.getpid()}
    if remaining:
        raise RuntimeError(f"Could not claim port {PORT}; remaining PIDs: {sorted(remaining)}")


def _prepare_token():
    data_dir = APP_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    token_file = data_dir / "fouria.token"
    token = token_file.read_text(encoding="utf-8").strip() if token_file.exists() else ""
    if not token:
        token = secrets.token_hex(16)
        token_file.write_text(token, encoding="utf-8")
    os.environ["FOURIA_TOKEN"] = token
    return token


def _deploy_bridge(token):
    src = BUNDLE_DIR / "fl_bridge" / "device_fouria.py"
    dst = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings" / "Hardware" / "FOURIA"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst / "device_fouria.py")
    (dst / "fouria.token").write_text(token, encoding="utf-8")
    _log(f"bridge and matching token deployed to {dst}")


def _fl_running():
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq FL64.exe"], capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return "FL64.exe" in result.stdout


def _launch_fl():
    if _fl_running():
        _log("FL Studio already running")
        return
    configured = os.environ.get("FOURIA_FL_PATH", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe"),
        Path(r"C:\Program Files\Image-Line\FL Studio 20\FL64.exe"),
    ]
    executable = next((path for path in candidates if path and path.exists()), None)
    if not executable:
        raise RuntimeError("FL Studio was not found")
    subprocess.Popen([str(executable)])
    _log(f"launched FL Studio: {executable}")


def _start_server():
    try:
        import fouria_api
        fouria_api.main()
    except Exception as exc:
        _log(f"bundled server failed: {exc!r}")


def _wait_for_own_server(timeout=25):
    from urllib.request import urlopen
    deadline = time.time() + timeout
    expected = str(BUNDLE_DIR).lower()
    while time.time() < deadline:
        try:
            data = json.loads(urlopen(f"{URL}/health", timeout=1).read())
            if str(data.get("root", "")).lower() == expected:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _splash():
    return """<!doctype html><html><body style="margin:0;background:#10100f;color:#f4f0e8;
    display:flex;align-items:center;justify-content:center;height:100vh;font-family:Segoe UI">
    <div style="text-align:center"><div style="font-size:48px;font-weight:900;color:#e7618d">
    FOURIA</div><div style="margin-top:12px;color:#aaa39a">starting FL Studio and claiming control...</div>
    </div></body></html>"""


def main():
    LOG_FILE.write_text("", encoding="utf-8")
    _log(f"starting Desktop FOURIA from {APP_DIR}")
    try:
        _claim_server_port()
        token = _prepare_token()
        _deploy_bridge(token)
        _launch_fl()
        threading.Thread(target=_start_server, daemon=True).start()
    except Exception as exc:
        _log(f"startup aborted: {exc!r}")
        raise

    import webview
    window = webview.create_window(
        "FOURIA  ·  FL Studio AI", html=_splash(), width=1280, height=860,
        min_size=(860, 600), background_color="#10100f",
    )

    def ready():
        if _wait_for_own_server():
            _log("bundled server verified; loading UI")
            window.load_url(URL)
        else:
            _log("bundled server verification timed out")
            window.load_html(
                "<body style='background:#10100f;color:#e7618d;font:18px Segoe UI'>"
                "FOURIA server failed. See Desktop/FOURIA-startup.log.</body>"
            )

    threading.Thread(target=ready, daemon=True).start()
    webview.start(debug=False, private_mode=False, storage_path=str(APP_DIR / "data" / "webview_cache"))


if __name__ == "__main__":
    main()
