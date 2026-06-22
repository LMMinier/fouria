$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Port = if ($env:FOURIA_PORT) { $env:FOURIA_PORT } else { "11700" }
$Model = if ($env:FOURIA_MODEL) { $env:FOURIA_MODEL } else { "fouria:studio" }
$OllamaUrl = if ($env:OLLAMA_URL) { $env:OLLAMA_URL } else { "http://127.0.0.1:11434" }

$env:FOURIA_ROOT = $Root
$env:FOURIA_MODEL = $Model
$env:FOURIA_PORT = $Port
$env:OLLAMA_URL = $OllamaUrl

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = (Get-Command python -ErrorAction Stop).Source
$psi.Arguments = "server\fouria_api.py"
$psi.WorkingDirectory = $Root
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $false
$psi.RedirectStandardError = $false

try { Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2 | Out-Null; Write-Host "FOURIA is already running"; exit } catch {}

$process = [System.Diagnostics.Process]::Start($psi)
$process.Id | Out-File -FilePath (Join-Path $LogDir "fouria.pid") -Encoding ascii

Start-Sleep -Seconds 2
$health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5
Write-Host "FOURIA background server started: http://127.0.0.1:$Port"
Write-Host "PID: $($process.Id)"
Write-Host "Model: $($health.model)"

