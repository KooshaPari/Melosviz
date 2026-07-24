# MelosViz bridge dev helper — start/stop/health for the local sidecar (p1q).
#
# Default listen port: 8765 (override with $env:MELOSVIZ_BRIDGE_PORT or -Port).
# Dev mode sets MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1 (open loopback, no bearer).
#
# Usage (from repo root):
#   .\scripts\dev_bridge.ps1 health
#   .\scripts\dev_bridge.ps1 status
#   .\scripts\dev_bridge.ps1 start [-Port 8765]
#   .\scripts\dev_bridge.ps1 stop
#
# Requires: python with melosviz bridge installed (`pip install -e backend/`).

param(
    [Parameter(Position = 0)]
    [ValidateSet("health", "status", "start", "stop")]
    [string]$Command = "health",

    [int]$Port = $(if ($env:MELOSVIZ_BRIDGE_PORT) { [int]$env:MELOSVIZ_BRIDGE_PORT } else { 8765 })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backend = Join-Path $Root "backend"
$PidFile = Join-Path $Root ".melosviz-dev-bridge.pid"
$BaseUrl = "http://127.0.0.1:$Port"

function Require-Python {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "dev_bridge: python not found — install backend deps: pip install -e backend/"
    }
}

function Invoke-BridgeProbe {
    param([string]$Path = "/health")
    $uri = "$BaseUrl$Path"
    try {
        return Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 3
    } catch {
        return $null
    }
}

function Write-BridgeTips {
    @"
Bridge base URL: $BaseUrl
  GET $BaseUrl/health   — liveness (use this first)
  GET $BaseUrl/ready    — readiness (deps loaded)
  GET $BaseUrl/metrics  — Prometheus text exposition

Env (manual dev): MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1
Desktop tray: Open Bridge Health opens the /health URL in your browser.
Docs: docs/ENV.md · docs/OBSERVABILITY.md
"@
}

function Get-ManagedPid {
    if (Test-Path $PidFile) {
        $raw = (Get-Content $PidFile -Raw).Trim()
        if ($raw -match '^\d+$') { return [int]$raw }
    }
    return $null
}

function Test-PidRunning {
    param([int]$Pid)
    if (-not $Pid) { return $false }
    try {
        $p = Get-Process -Id $Pid -ErrorAction Stop
        return $null -ne $p
    } catch {
        return $false
    }
}

function Invoke-Health {
    Write-Host "dev_bridge: probing $BaseUrl/health"
    $resp = Invoke-BridgeProbe "/health"
    if ($resp) {
        Write-Host "dev_bridge: OK — bridge is healthy on port $Port"
        Write-Host $resp.Content
        Write-Host ""
        Write-BridgeTips
        return
    }
    Write-Error "dev_bridge: not reachable on $BaseUrl/health`nTip — start with: .\scripts\dev_bridge.ps1 start`nTip — ensure backend installed: pip install -e backend/`n$(Write-BridgeTips)"
}

function Invoke-Status {
    $pid = Get-ManagedPid
    if (Test-PidRunning $pid) {
        Write-Host "dev_bridge: running (pid=$pid, port=$Port)"
    } else {
        Write-Host "dev_bridge: no managed sidecar (pid file missing or stale)"
    }
    $resp = Invoke-BridgeProbe "/health"
    if ($resp) {
        Write-Host "dev_bridge: /health OK on $BaseUrl"
    } else {
        throw "dev_bridge: /health not OK on $BaseUrl"
    }
}

function Start-Bridge {
    Require-Python
    $pid = Get-ManagedPid
    if (Test-PidRunning $pid) {
        throw "dev_bridge: already running (pid=$pid) — use stop first or another -Port"
    }
    if (Invoke-BridgeProbe "/health") {
        throw "dev_bridge: something already listens on port $Port (/health OK). Use -Port or MELOSVIZ_BRIDGE_PORT."
    }

    Write-Host "dev_bridge: starting bridge on 127.0.0.1:$Port (insecure loopback dev mode)"
    $env:MELOSVIZ_BRIDGE_INSECURE_LOOPBACK = "1"
    $proc = Start-Process -FilePath "python" `
        -ArgumentList @("-m", "melosviz.bridge.server", "--port", "$Port") `
        -WorkingDirectory $Backend `
        -PassThru -WindowStyle Hidden
    Set-Content -Path $PidFile -Value $proc.Id -NoNewline

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Invoke-BridgeProbe "/health") {
            $ready = $true
            break
        }
        if ($proc.HasExited) {
            Remove-Item $PidFile -ErrorAction SilentlyContinue
            throw "dev_bridge: bridge process exited early (pid=$($proc.Id))"
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        throw "dev_bridge: bridge did not become healthy within 15s"
    }
    Write-Host "dev_bridge: started (pid=$($proc.Id))"
    Write-BridgeTips
}

function Stop-Bridge {
    $pid = Get-ManagedPid
    if (-not (Test-PidRunning $pid)) {
        Write-Host "dev_bridge: no managed sidecar to stop"
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        return
    }
    Write-Host "dev_bridge: stopping pid=$pid"
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Write-Host "dev_bridge: stopped"
}

switch ($Command) {
    "health" { Invoke-Health }
    "status" { Invoke-Status }
    "start"  { Start-Bridge }
    "stop"   { Stop-Bridge }
}
