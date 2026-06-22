param([string]$FLPath = "C:\Program Files\Image-Line\FL Studio 21\FL64.exe")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not (Test-Path $FLPath)) { $FLPath = "C:\Program Files\Image-Line\FL Studio 20\FL64.exe" }
if (-not (Test-Path $FLPath)) { throw "FL Studio was not found." }
try { Invoke-RestMethod "http://127.0.0.1:11700/health" -TimeoutSec 1 | Out-Null }
catch { Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$Root\Start-FOURIA-Background.ps1`"" }
$fl = Start-Process $FLPath -PassThru
for ($i=0; $i -lt 30; $i++) {
    try { Invoke-RestMethod "http://127.0.0.1:11700/health" -TimeoutSec 1 | Out-Null; break }
    catch { Start-Sleep -Milliseconds 500 }
}
Start-Process python -WindowStyle Hidden -ArgumentList "`"$Root\fouria_chat.py`""
$fl.WaitForExit()
