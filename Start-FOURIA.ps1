$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Server = Join-Path $Root "server\fouria_api.py"
$Port = if ($env:FOURIA_PORT) { $env:FOURIA_PORT } else { "11700" }

if (-not $env:FOURIA_MODEL) { $env:FOURIA_MODEL = "fouria:studio" }
if (-not $env:OLLAMA_URL) { $env:OLLAMA_URL = "http://127.0.0.1:11434" }
if (-not $env:FOURIA_ROOT) { $env:FOURIA_ROOT = $Root }
if (-not $env:FOURIA_PORT) { $env:FOURIA_PORT = $Port }

function Test-Port($port) {
    $c = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -WarningAction SilentlyContinue
    return $c.TcpTestSucceeded
}

Write-Host ""
Write-Host "  FOURIA - FL Studio producer brain" -ForegroundColor Magenta
Write-Host "  ---------------------------------" -ForegroundColor DarkGray

if (-not (Test-Port 11434)) {
    Write-Host "  Starting Ollama..." -ForegroundColor Cyan
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
}

$models = (& ollama list 2>$null | Out-String)
if ($models -notmatch "fouria:studio") {
    Write-Host "  Creating Ollama model fouria:studio from qwen2.5-coder:3b..." -ForegroundColor Cyan
    & ollama create fouria:studio -f (Join-Path $Root "Modelfile")
}

Write-Host "  Starting server on http://127.0.0.1:$Port" -ForegroundColor Green
python $Server

