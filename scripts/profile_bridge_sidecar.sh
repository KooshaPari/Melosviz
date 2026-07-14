#!/usr/bin/env bash
# External py-spy sidecar profiler for the MelosViz bridge (WBS-P3.4).
#
# Operator-owned host dependency: pip install py-spy
# Opt-in via MELOSVIZ_PROFILE_SIDECAR=1 (see docs/ENV.md).
#
# Resolves bridge PID from:
#   1) MELOSVIZ_BRIDGE_PID
#   2) listener on MELOSVIZ_BRIDGE_PORT (default 8765) after /health succeeds
#
# Usage:
#   MELOSVIZ_PROFILE_SIDECAR=1 ./scripts/profile_bridge_sidecar.sh
#   MELOSVIZ_PROFILE_SIDECAR_MODE=record MELOSVIZ_PROFILE_SIDECAR_DURATION=60 ./scripts/profile_bridge_sidecar.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${MELOSVIZ_PROFILE_SIDECAR:-0}" != "1" ]]; then
  echo "profile_bridge_sidecar: set MELOSVIZ_PROFILE_SIDECAR=1 to run (opt-in sidecar)"
  exit 0
fi

if ! command -v py-spy >/dev/null 2>&1; then
  echo "profile_bridge_sidecar: py-spy not found — pip install py-spy" >&2
  exit 1
fi

PORT="${MELOSVIZ_BRIDGE_PORT:-8765}"
URL="${MELOSVIZ_BRIDGE_URL:-http://127.0.0.1:${PORT}}"
MODE="${MELOSVIZ_PROFILE_SIDECAR_MODE:-top}"
DURATION="${MELOSVIZ_PROFILE_SIDECAR_DURATION:-60}"
OUT="${MELOSVIZ_PROFILE_SIDECAR_OUT:-bridge-profile.svg}"

resolve_pid() {
  if [[ -n "${MELOSVIZ_BRIDGE_PID:-}" ]]; then
    echo "$MELOSVIZ_BRIDGE_PID"
    return 0
  fi

  if ! curl -sf "${URL}/health" >/dev/null; then
    echo "profile_bridge_sidecar: bridge not healthy at ${URL}/health" >&2
    return 1
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:${PORT}" -sTCP:LISTEN | head -n1
    return 0
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -lptn "sport = :${PORT}" | awk -F'pid=' 'NR>1 {gsub(/,.*/, "", $2); print $2; exit}'
    return 0
  fi

  echo "profile_bridge_sidecar: cannot resolve PID (set MELOSVIZ_BRIDGE_PID)" >&2
  return 1
}

PID="$(resolve_pid)"
if [[ -z "$PID" ]]; then
  echo "profile_bridge_sidecar: empty PID" >&2
  exit 1
fi

echo "profile_bridge_sidecar: attaching py-spy to bridge pid=${PID} mode=${MODE}"

case "$MODE" in
  top)
    exec py-spy top --pid "$PID"
    ;;
  record)
    exec py-spy record --pid "$PID" --output "$OUT" --duration "$DURATION"
    ;;
  *)
    echo "profile_bridge_sidecar: unknown MELOSVIZ_PROFILE_SIDECAR_MODE=${MODE} (top|record)" >&2
    exit 1
    ;;
esac
