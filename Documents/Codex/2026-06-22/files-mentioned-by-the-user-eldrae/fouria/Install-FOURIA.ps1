$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Hardware = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings\Hardware\FOURIA"
$OldLauncher = Join-Path ([Environment]::GetFolderPath("Startup")) "FOURIA.cmd"
New-Item -ItemType Directory -Force -Path $Hardware | Out-Null
Copy-Item (Join-Path $Root "fl_bridge\device_fouria.py") (Join-Path $Hardware "device_fouria.py") -Force
Remove-Item $OldLauncher -Force -ErrorAction SilentlyContinue
$Shell = New-Object -ComObject WScript.Shell
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "FL Studio + FOURIA.lnk"
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\Launch-FL-With-FOURIA.ps1`""
$Shortcut.WorkingDirectory = $Root
$Shortcut.IconLocation = "C:\Program Files\Image-Line\FL Studio 21\FL64.exe,0"
$Shortcut.Save()

$WatcherShortcutPath = Join-Path ([Environment]::GetFolderPath("Startup")) "FOURIA FL Watcher.lnk"
Remove-Item $WatcherShortcutPath -Force -ErrorAction SilentlyContinue

Write-Host "Launch FL with the new 'FL Studio + FOURIA' desktop shortcut." -ForegroundColor Magenta
Write-Host "FOURIA starts only from the FL Studio + FOURIA launcher." -ForegroundColor Magenta
Write-Host "In FL click Update MIDI scripts; FOURIA appears under Scripts."
