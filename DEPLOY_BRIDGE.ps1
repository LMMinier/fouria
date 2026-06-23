# FOURIA Bridge Deployer
# Run this any time you pull updates to push the latest bridge to FL Studio
$Root    = Split-Path $MyInvocation.MyCommand.Path
$BridgeSrc = Join-Path $Root "fl_bridge\device_fouria.py"
$HardwareDir = "$env:USERPROFILE\Documents\Image-Line\FL Studio\Settings\Hardware\FOURIA"

if (-not (Test-Path $HardwareDir)) {
    New-Item -ItemType Directory -Path $HardwareDir | Out-Null
    Write-Host "Created FL Studio FOURIA script folder."
}

Copy-Item $BridgeSrc "$HardwareDir\device_fouria.py" -Force
$ver = Select-String "BRIDGE_VERSION" "$HardwareDir\device_fouria.py" | Select-Object -First 1
Write-Host "Bridge deployed: $($ver.Line.Trim())"
Write-Host "Restart the FOURIA script in FL Studio: Options > MIDI Settings > FOURIA > press F5 or reload."
