@echo off
title FOURIA Server
cd /d "%~dp0"
echo.
echo  ███████╗ ██████╗ ██╗   ██╗██████╗ ██╗ █████╗
echo  ██╔════╝██╔═══██╗██║   ██║██╔══██╗██║██╔══██╗
echo  █████╗  ██║   ██║██║   ██║██████╔╝██║███████║
echo  ██╔══╝  ██║   ██║██║   ██║██╔══██╗██║██╔══██║
echo  ██║     ╚██████╔╝╚██████╔╝██║  ██║██║██║  ██║
echo  ╚═╝      ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
echo.
echo  FL Studio AI Production Assistant v0.2
echo  ─────────────────────────────────────
echo.

:: Deploy latest bridge to FL Studio
echo [1/3] Deploying bridge to FL Studio...
set BRIDGE_SRC=%~dp0fl_bridge\device_fouria.py
set BRIDGE_DST=%USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Hardware\FOURIA\device_fouria.py
if not exist "%USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Hardware\FOURIA\" (
    mkdir "%USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Hardware\FOURIA\"
)
copy /Y "%BRIDGE_SRC%" "%BRIDGE_DST%" >nul
echo     Bridge deployed to FL Studio MIDI scripts.

:: Start server
echo [2/3] Starting FOURIA server at http://127.0.0.1:11700
echo [3/3] Open http://127.0.0.1:11700 in your browser
echo.
echo  In FL Studio: Options ^> MIDI Settings ^> Controller type = FOURIA AI Studio Assistant
echo  Then press F5 or restart the script to connect.
echo.
echo  Press Ctrl+C to stop FOURIA.
echo ─────────────────────────────────────────────────
echo.

cd server
python fouria_api.py
pause
