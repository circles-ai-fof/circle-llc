# start-local.ps1 — Arranca backend + dashboard en local (PowerShell)
#
# Uso:
#   .\start-local.ps1                 # arranca todo
#   .\start-local.ps1 -CleanDashboard # también borra .next antes
#   .\start-local.ps1 -Stop           # detiene los servicios
#
# Prerequisitos: Python 3.12+ con uvicorn, Node 20+, .env en circle-llc/

param(
    [switch]$CleanDashboard,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$DashboardDir = Join-Path $Root "dashboard"
$BackendPort = 8002
$DashboardPort = 3001

function Stop-Port($port) {
    $pids = (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess
    foreach ($pid in $pids) {
        if ($pid) {
            Write-Host "  Killing PID $pid (listening on $port)" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
}

if ($Stop) {
    Write-Host "Stopping services..." -ForegroundColor Cyan
    Stop-Port $BackendPort
    Stop-Port $DashboardPort
    Write-Host "Done." -ForegroundColor Green
    exit 0
}

# Stop any existing services on those ports (avoid EADDRINUSE)
Write-Host "Killing any previous processes on :$BackendPort and :$DashboardPort..." -ForegroundColor Cyan
Stop-Port $BackendPort
Stop-Port $DashboardPort
Start-Sleep -Seconds 1

# Backend: load .env so ALLOWED_EMAILS + ANTHROPIC_API_KEY are exported
$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "ERROR: .env not found at $EnvFile" -ForegroundColor Red
    Write-Host "       Copy .env.example to .env and fill in the keys first." -ForegroundColor Red
    exit 1
}

# Export env vars so the EvidenceGateWorkflow init sees ANTHROPIC_API_KEY
Get-Content $EnvFile | Where-Object { $_ -match "^[A-Z_]+=." } | ForEach-Object {
    $kv = $_ -split "=", 2
    [Environment]::SetEnvironmentVariable($kv[0], $kv[1], "Process")
}

if ([Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY")) {
    Write-Host "ANTHROPIC_API_KEY: set (live mode)" -ForegroundColor Green
} else {
    Write-Host "ANTHROPIC_API_KEY: not set (mock mode)" -ForegroundColor Yellow
}

# Start backend in a new PowerShell window so the user can see logs
Write-Host "Starting backend on :$BackendPort ..." -ForegroundColor Cyan
$BackendCmd = "cd '$Root'; python -m uvicorn orchestrator.api:app --reload --port $BackendPort --host 127.0.0.1"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCmd

# Wait for backend to be reachable (max 30s)
$tries = 0
while ($tries -lt 30) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$BackendPort/api/v1/health" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) {
            $body = $r.Content | ConvertFrom-Json
            Write-Host "Backend ready (mode=$($body.mode), persistent_storage=$($body.persistent_storage))" -ForegroundColor Green
            break
        }
    } catch {
        # not ready yet
    }
    Start-Sleep -Seconds 1
    $tries++
}
if ($tries -ge 30) {
    Write-Host "Backend did not come up in 30s. Check the backend window for errors." -ForegroundColor Red
}

# Dashboard
if ($CleanDashboard -and (Test-Path (Join-Path $DashboardDir ".next"))) {
    Write-Host "Cleaning dashboard .next ..." -ForegroundColor Cyan
    Push-Location $DashboardDir
    & npm run clean
    Pop-Location
}

Write-Host "Starting dashboard on :$DashboardPort ..." -ForegroundColor Cyan
$DashCmd = "cd '$DashboardDir'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $DashCmd

Write-Host ""
Write-Host "Services starting." -ForegroundColor Green
Write-Host "  Backend:   http://localhost:$BackendPort/api/v1/health" -ForegroundColor White
Write-Host "  Dashboard: http://localhost:$DashboardPort/login" -ForegroundColor White
Write-Host ""
Write-Host "Allowed emails (from .env):" -ForegroundColor White
$allowed = [Environment]::GetEnvironmentVariable("ALLOWED_EMAILS")
if ($allowed) {
    $allowed -split "," | ForEach-Object { Write-Host "  - $_" -ForegroundColor White }
} else {
    Write-Host "  (none — set ALLOWED_EMAILS in .env)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "To stop: .\start-local.ps1 -Stop" -ForegroundColor Gray
