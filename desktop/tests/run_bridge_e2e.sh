#!/usr/bin/env bash
# Desktop bridge-layer e2e (Linux CI / headless local).
#
# Starts the Python FastAPI bridge sidecar, runs Bun e2e in BRIDGE_ONLY mode
# (no Electrobun / no display), then tears down the bridge.
#
# Host-gated GUI tests (launcher log, WKWebView invariants) require macOS +
# a display — see desktop/tests/README.md and run:
#   cd desktop && bun test tests/e2e_desktop.test.ts
#
# Usage (from repo root):
#   ./desktop/tests/run_bridge_e2e.sh
#   BRIDGE_PORT=18765 ./desktop/tests/run_bridge_e2e.sh
#
# CI: .github/workflows/ci.yml job `desktop-e2e` invokes this script.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DESKTOP="$ROOT/desktop"
BACKEND="$ROOT/backend"
PORT="${BRIDGE_PORT:-18765}"

if ! command -v python >/dev/null 2>&1; then
  echo "run_bridge_e2e: python not found" >&2
  exit 1
fi
if ! command -v bun >/dev/null 2>&1; then
  echo "run_bridge_e2e: bun not found" >&2
  exit 1
fi

cleanup() {
  if [[ -n "${BRIDGE_PID:-}" ]]; then
    kill "$BRIDGE_PID" 2>/dev/null || true
    wait "$BRIDGE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "run_bridge_e2e: starting bridge on 127.0.0.1:${PORT}"
(
  cd "$BACKEND"
  python -m melosviz.bridge.server --port "$PORT"
) &
BRIDGE_PID=$!

echo "run_bridge_e2e: waiting for /health"
ready=0
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.5
done
if [[ "$ready" -ne 1 ]]; then
  echo "run_bridge_e2e: bridge did not become ready within 15s" >&2
  exit 1
fi

echo "run_bridge_e2e: running Bun bridge e2e"
(
  cd "$DESKTOP"
  export BRIDGE_ONLY=1
  export BRIDGE_PORT="$PORT"
  export MELOSVIZ_BACKEND_DIR="$BACKEND"
  export CI=1
  bun test tests/e2e_desktop.test.ts --timeout 60000
)

echo "run_bridge_e2e: ok"
