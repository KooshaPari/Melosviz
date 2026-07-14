# External py-spy sidecar profiler for the MelosViz bridge (WBS-P3.4).
# Operator-owned host dependency: pip install py-spy
# Opt-in via MELOSVIZ_PROFILE_SIDECAR=1 (see docs/ENV.md).

param(
    [string]$BridgeUrl = $(if ($env:MELOSVIZ_BRIDGE_URL) { $env:MELOSVIZ_BRIDGE_URL } else {
        $p = if ($env:MELOSVIZ_BRIDGE_PORT) { $env:MELOSVIZ_BRIDGE_PORT } else { "8765" }
        "http://127.0.0.1:$p"
    }),
    [string]$Mode = $(if ($env:MELOSVIZ_PROFILE_SIDECAR_MODE) { $env:MELOSVIZ_PROFILE_SIDECAR_MODE } else { "top" }),
    [int]$Duration = $(if ($env:MELOSVIZ_PROFILE_SIDECAR_DURATION) { [int]$env:MELOSVIZ_PROFILE_SIDECAR_DURATION } else { 60 }),
    [string]$Out = $(if ($env:MELOSVIZ_PROFILE_SIDECAR_OUT) { $env:MELOSVIZ_PROFILE_SIDECAR_OUT } else { "bridge-profile.svg" })
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($env:MELOSVIZ_PROFILE_SIDECAR -ne "1") {
    Write-Host "profile_bridge_sidecar: set MELOSVIZ_PROFILE_SIDECAR=1 to run (opt-in sidecar)"
    exit 0
}

if (-not (Get-Command py-spy -ErrorAction SilentlyContinue)) {
    Write-Error "profile_bridge_sidecar: py-spy not found — pip install py-spy"
}

function Resolve-BridgePid {
    if ($env:MELOSVIZ_BRIDGE_PID) {
        return [int]$env:MELOSVIZ_BRIDGE_PID
    }

  try {
        Invoke-WebRequest -Uri "$BridgeUrl/health" -UseBasicParsing -TimeoutSec 5 | Out-Null
    } catch {
        throw "profile_bridge_sidecar: bridge not healthy at $BridgeUrl/health"
    }

    $uri = [Uri]$BridgeUrl
    $port = if ($uri.Port -gt 0) { $uri.Port } else { 8765 }
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($conn) {
        return [int]$conn.OwningProcess
    }

    throw "profile_bridge_sidecar: cannot resolve PID (set MELOSVIZ_BRIDGE_PID)"
}

$bridgePid = Resolve-BridgePid
Write-Host "profile_bridge_sidecar: attaching py-spy to bridge pid=$bridgePid mode=$Mode"

switch ($Mode) {
    "top" {
        & py-spy top --pid $bridgePid
    }
    "record" {
        & py-spy record --pid $bridgePid --output $Out --duration $Duration
    }
    default {
        throw "profile_bridge_sidecar: unknown MELOSVIZ_PROFILE_SIDECAR_MODE=$Mode (top|record)"
    }
}
