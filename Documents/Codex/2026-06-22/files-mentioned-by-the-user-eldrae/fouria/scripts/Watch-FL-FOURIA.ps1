$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$Start = Join-Path $Root "Start-FOURIA-Background.ps1"
$Ui = "http://127.0.0.1:11700/"
$FlNames = @("FL64", "FL", "FL Studio")
$WasOpen = $false

function Test-Port($port) {
    $c = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -WarningAction SilentlyContinue
    return $c.TcpTestSucceeded
}

Write-Host "FOURIA FL watcher armed. Open FL Studio and she'll wake up." -ForegroundColor Magenta

while ($true) {
    $fl = Get-Process -ErrorAction SilentlyContinue | Where-Object { $FlNames -contains $_.ProcessName }
    if ($fl -and -not $WasOpen) {
        Write-Host "FL Studio detected. Launching FOURIA..." -ForegroundColor Green
        if (-not (Test-Port 11700)) {
            Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$Start`"" -WindowStyle Hidden
            Start-Sleep -Seconds 5
        }
        Start-Process $Ui
        $WasOpen = $true
    }
    if (-not $fl) { $WasOpen = $false }
    Start-Sleep -Seconds 3
}
