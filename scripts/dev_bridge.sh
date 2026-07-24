#!/usr/bin/env bash
# MelosViz bridge dev helper — start/stop/health for the local sidecar (p1q).
#
# Default listen port: 8765 (override with MELOSVIZ_BRIDGE_PORT or --port).
# Dev mode sets MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1 (open loopback, no bearer).
#
# Usage (from repo root):
#   ./scripts/dev_bridge.sh health          # probe /health + operator tips
#   ./scripts/dev_bridge.sh status          # PID file + health summary
#   ./scripts/dev_bridge.sh start [--port N]  # background sidecar
#   ./scripts/dev_bridge.sh stop            # stop background sidecar
#
# Requires: python with melosviz bridge installed (`pip install -e backend/`).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
PID_FILE="$ROOT/.melosviz-dev-bridge.pid"
PORT="${MELOSVIZ_BRIDGE_PORT:-8765}"
CMD="${1:-health}"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="${2:?--port requires a value}"
      shift 2
      ;;
    *)
      echo "dev_bridge: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

BASE_URL="http://127.0.0.1:${PORT}"

require_python() {
  if ! command -v python >/dev/null 2>&1; then
    echo "dev_bridge: python not found — install backend deps: pip install -e backend/" >&2
    exit 1
  fi
}

health_probe() {
  local path="${1:-/health}"
  if command -v curl >/dev/null 2>&1; then
    curl -sf "${BASE_URL}${path}"
    return $?
  fi
  python - "$BASE_URL" "$path" <<'PY'
import sys, urllib.request
base, path = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(f"{base}{path}", timeout=3) as r:
    sys.stdout.write(r.read().decode())
PY
}

print_tips() {
  cat <<EOF
Bridge base URL: ${BASE_URL}
  GET ${BASE_URL}/health   — liveness (use this first)
  GET ${BASE_URL}/ready    — readiness (deps loaded)
  GET ${BASE_URL}/metrics  — Prometheus text exposition

Env (manual dev): MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1
Desktop tray: "Open Bridge Health" opens the /health URL in your browser.
Docs: docs/ENV.md · docs/OBSERVABILITY.md
EOF
}

cmd_health() {
  echo "dev_bridge: probing ${BASE_URL}/health"
  if health_probe "/health" >/dev/null 2>&1; then
    echo "dev_bridge: OK — bridge is healthy on port ${PORT}"
    health_probe "/health" || true
    echo
    print_tips
    return 0
  fi
  echo "dev_bridge: not reachable on ${BASE_URL}/health" >&2
  echo "dev_bridge: tip — start with: ./scripts/dev_bridge.sh start" >&2
  echo "dev_bridge: tip — ensure backend installed: pip install -e backend/" >&2
  print_tips >&2
  return 1
}

read_pid() {
  if [[ -f "$PID_FILE" ]]; then
    cat "$PID_FILE"
  fi
}

pid_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

cmd_status() {
  local pid
  pid="$(read_pid || true)"
  if pid_running "$pid"; then
    echo "dev_bridge: running (pid=${pid}, port=${PORT})"
  else
    echo "dev_bridge: no managed sidecar (pid file missing or stale)"
  fi
  if health_probe "/health" >/dev/null 2>&1; then
    echo "dev_bridge: /health OK on ${BASE_URL}"
  else
    echo "dev_bridge: /health not OK on ${BASE_URL}"
    return 1
  fi
}

cmd_start() {
  require_python
  local pid
  pid="$(read_pid || true)"
  if pid_running "$pid"; then
    echo "dev_bridge: already running (pid=${pid}) — use stop first or another port" >&2
    exit 1
  fi
  if health_probe "/health" >/dev/null 2>&1; then
    echo "dev_bridge: something already listens on port ${PORT} (/health OK)" >&2
    echo "dev_bridge: use MELOSVIZ_BRIDGE_PORT=<port> or --port to avoid collision" >&2
    exit 1
  fi

  echo "dev_bridge: starting bridge on 127.0.0.1:${PORT} (insecure loopback dev mode)"
  (
    cd "$BACKEND"
    export MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1
    exec python -m melosviz.bridge.server --port "$PORT"
  ) &
  pid=$!
  echo "$pid" >"$PID_FILE"

  local ready=0
  for _ in $(seq 1 30); do
    if health_probe "/health" >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "dev_bridge: bridge process exited early (pid=${pid})" >&2
      rm -f "$PID_FILE"
      exit 1
    fi
    sleep 0.5
  done
  if [[ "$ready" -ne 1 ]]; then
    echo "dev_bridge: bridge did not become healthy within 15s" >&2
    kill "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    exit 1
  fi
  echo "dev_bridge: started (pid=${pid})"
  print_tips
}

cmd_stop() {
  local pid
  pid="$(read_pid || true)"
  if ! pid_running "$pid"; then
    echo "dev_bridge: no managed sidecar to stop"
    rm -f "$PID_FILE"
    return 0
  fi
  echo "dev_bridge: stopping pid=${pid}"
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "dev_bridge: stopped"
}

case "$CMD" in
  health) cmd_health ;;
  status) cmd_status ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  *)
    echo "dev_bridge: unknown command '${CMD}' (health|status|start|stop)" >&2
    exit 1
    ;;
esac
