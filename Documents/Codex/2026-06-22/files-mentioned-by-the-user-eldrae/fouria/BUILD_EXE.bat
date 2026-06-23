@echo off
title FOURIA — Build EXE
cd /d "%~dp0"

echo.
echo  FOURIA Desktop App Builder
echo  ──────────────────────────
echo.

:: Check Python
python --version >nul 2>&1 || (echo Python not found. && pause && exit /b 1)

:: Install deps
echo [1/4] Installing dependencies...
pip install pywebview pyinstaller --quiet

:: Verify pywebview
python -c "import webview" 2>nul || (echo pywebview install failed. && pause && exit /b 1)

echo [2/4] Building FOURIA.exe ...

pyinstaller ^
  --onefile ^
  --windowed ^
  --name FOURIA ^
  --add-data "server;server" ^
  --add-data "fl_bridge;fl_bridge" ^
  --add-data "ui;ui" ^
  --add-data "data;data" ^
  --hidden-import "webview" ^
  --hidden-import "webview.platforms.winforms" ^
  --hidden-import "clr" ^
  --hidden-import "fouria_api" ^
  --hidden-import "action_store" ^
  --hidden-import "model_client" ^
  --hidden-import "rag" ^
  --hidden-import "audio_tools" ^
  --hidden-import "capabilities" ^
  --hidden-import "context_injector" ^
  --hidden-import "midi_tools" ^
  --hidden-import "persona" ^
  --hidden-import "production_agent" ^
  --hidden-import "orchestrator" ^
  --hidden-import "library_index" ^
  --hidden-import "midi_output" ^
  --paths "server" ^
  fouria_app.py

if not exist "dist\FOURIA.exe" (
    echo.
    echo Build failed. Check output above.
    pause
    exit /b 1
)

echo [3/4] Copying EXE to Desktop...
copy /Y "dist\FOURIA.exe" "%USERPROFILE%\Desktop\FOURIA.exe" >nul
echo     FOURIA.exe is on your Desktop.

echo [4/4] Done.
echo.
echo  Double-click FOURIA.exe on your Desktop to launch.
echo  FL Studio bridge deploys automatically on startup.
echo.
pause
