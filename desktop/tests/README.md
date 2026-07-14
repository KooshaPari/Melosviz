# Desktop e2e tests

`e2e_desktop.test.ts` exercises the MelosViz desktop stack in two modes.

## BRIDGE_ONLY (Linux CI, headless local)

No display server or Electrobun process. A pre-started Python bridge sidecar is
probed over HTTP — the same channel the Bun main process uses in production.

**Covered in CI** (`.github/workflows/ci.yml` → job `desktop-e2e`):

| Case | Endpoint / check |
|------|------------------|
| Liveness | `GET /health` |
| Readiness | `GET /ready` |
| Observability | `GET /metrics` (Prometheus text) |
| Profiler off | `GET /debug/profile` → 404 when `MELOSVIZ_PROFILE` unset |
| Analyze happy path | `POST /analyze` → RenderSpec JSON shape |
| Analyze validation | missing `wav_path` → 422; missing file → 400 |
| Build reachability | `POST /build` → 200 or 400 (flat fixture) |
| Render reachability | `POST /render` → 200 or 400 (flat fixture) |

**Run locally (headless):**

```bash
# From repo root — starts bridge, runs tests, stops bridge
./desktop/tests/run_bridge_e2e.sh

# Or manual sidecar:
cd backend && pip install -e ".[bridge]"
python -m melosviz.bridge.server --port 18765 &
export BRIDGE_PORT=18765 BRIDGE_ONLY=1 MELOSVIZ_BACKEND_DIR=$PWD
cd ../desktop && bun install && bun test tests/e2e_desktop.test.ts --timeout 60000
```

CI installs `backend[bridge]` only (not `[analysis]`) so `/analyze` stays within
runner time budgets on the flat `test_tone.wav` fixture.

## HOST MODE (macOS + display — host-gated)

Spawns `bunx electrobun dev`, waits for `[MelosViz] window created`, then
asserts launcher-log invariants (crypto.subtle, views:// bundle, RPC transport,
webview console errors, tray startup).

**Not runnable in Linux CI** — WKWebView / AppKit require a real macOS host with
a display. These checks are **host-gated** and documented in
`docs/GAP_AUDIT_QA_MATRIX.md` (G-C07-01 mitigated: bridge layer in CI; full GUI
still macOS-host-only).

**Run on macOS:**

```bash
cd backend && pip install -e '.[bridge,analysis]'
cd ../desktop && bun install
bun test tests/e2e_desktop.test.ts
# Or: bun run test:e2e
```

Unset `BRIDGE_ONLY` and `CI` so the suite launches Electrobun. For bridge HTTP
probes without re-spawning the sidecar, the host run still uses the app-spawned
bridge port parsed from launcher logs.

## Residual manual-only checks

These remain outside automated e2e (see `e2e_desktop.test.ts` header):

- Pixel-level webview rendering (WKWebView has no headless screenshot API in CI)
- Native file-picker (`openFileDialog`) interaction
- Drag-and-drop into the webview

Tracked under WBS-P1.9 / audit C07 L64.
