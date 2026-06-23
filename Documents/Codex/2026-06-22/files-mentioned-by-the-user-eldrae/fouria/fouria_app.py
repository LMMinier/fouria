"""FOURIA Desktop App — single entry point.

Double-click this (or the built EXE) to:
  1. Start the FOURIA server in a background thread
  2. Deploy the bridge to FL Studio MIDI scripts
  3. Open the FOURIA native window (no browser needed)
"""
import os
import sys
import shutil
import threading
import time
from pathlib import Path

# ── Root resolution (works both as .py and as PyInstaller EXE) ───────────────
if getattr(sys, "frozen", False):
    # Running as compiled EXE — PyInstaller unpacks to _MEIPASS
    BUNDLE_DIR = Path(sys._MEIPASS)
    APP_DIR    = Path(sys.executable).parent
else:
    BUNDLE_DIR = Path(__file__).resolve().parent
    APP_DIR    = BUNDLE_DIR

os.environ["FOURIA_ROOT"] = str(BUNDLE_DIR)
sys.path.insert(0, str(BUNDLE_DIR / "server"))

PORT  = int(os.environ.get("FOURIA_PORT", "11700"))
URL   = f"http://127.0.0.1:{PORT}"

# ── Bridge auto-deploy ────────────────────────────────────────────────────────

def _deploy_bridge():
    src = BUNDLE_DIR / "fl_bridge" / "device_fouria.py"
    dst_dir = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings" / "Hardware" / "FOURIA"
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst_dir / "device_fouria.py")
        print(f"FOURIA: bridge deployed → {dst_dir}", flush=True)
    except Exception as exc:
        print(f"FOURIA: bridge deploy skipped ({exc})", flush=True)


# ── Server launcher ───────────────────────────────────────────────────────────

def _start_server():
    import fouria_api
    fouria_api.main()


def _wait_for_server(timeout: int = 20) -> bool:
    from urllib.request import urlopen
    from urllib.error import URLError
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urlopen(f"{URL}/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


# ── Splash (shown while server starts) ───────────────────────────────────────

def _splash_html() -> str:
    return """<!doctype html><html><head>
<meta charset="utf-8">
<style>
  body { margin:0; background:#10100f; display:flex; flex-direction:column;
         align-items:center; justify-content:center; height:100vh;
         font-family:"Segoe UI",system-ui,sans-serif; color:#f4f0e8; }
  .logo { font-size:48px; font-weight:900; letter-spacing:.18em;
          background:linear-gradient(135deg,#e7618d,#d6a94a);
          -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
  .sub  { margin-top:8px; font-size:13px; color:#aaa39a; letter-spacing:.12em; }
  .bar  { margin-top:32px; width:220px; height:3px; background:#1e1e1c;
          border-radius:99px; overflow:hidden; }
  .fill { height:100%; width:30%; background:linear-gradient(90deg,#e7618d,#d6a94a);
          border-radius:99px; animation:slide 1.2s ease-in-out infinite; }
  @keyframes slide { 0%{transform:translateX(-100%)} 100%{transform:translateX(433%)} }
</style></head><body>
<div class="logo">FOURIA</div>
<div class="sub">FL Studio AI · starting up…</div>
<div class="bar"><div class="fill"></div></div>
</body></html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Deploy bridge immediately
    _deploy_bridge()

    # 2. Start server thread
    server_thread = threading.Thread(target=_start_server, daemon=True)
    server_thread.start()

    # 3. Launch native window
    try:
        import webview
    except ImportError:
        print("pywebview not installed. Run: pip install pywebview", flush=True)
        # Fallback: open browser
        import webbrowser
        if _wait_for_server():
            webbrowser.open(URL)
        else:
            print("Server failed to start.", flush=True)
        server_thread.join()
        return

    # Show splash while server starts
    window = webview.create_window(
        title      = "FOURIA  ·  FL Studio AI",
        html       = _splash_html(),
        width      = 1280,
        height     = 860,
        resizable  = True,
        min_size   = (860, 600),
        background_color = "#10100f",
    )

    def _on_ready():
        # Wait for server, then navigate to the real UI
        if _wait_for_server(timeout=25):
            window.load_url(URL)
        else:
            window.load_html("""<!doctype html><html><body style="background:#10100f;color:#e7618d;
                font-family:sans-serif;display:flex;align-items:center;justify-content:center;
                height:100vh;font-size:18px">Server failed to start. Check the console.</body></html>""")

    threading.Thread(target=_on_ready, daemon=True).start()

    webview.start(
        debug           = False,
        private_mode    = False,
        storage_path    = str(APP_DIR / "data" / "webview_cache"),
    )


if __name__ == "__main__":
    main()
