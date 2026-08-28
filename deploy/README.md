# MelosViz Dev Stack

A one-command docker-compose stack that brings up a **real ComfyUI worker** + a **C4D stub listener** + the **MelosViz bridge** so the offline-mode storyboard/generate/assemble/master/ship pipeline produces actual renders (image / video / 3D) instead of just job-spec JSON.

## Quick start

```bash
# 1) Build + bring up the stack
make dev:stack

# 2) Run the end-to-end pipeline against it
make dev:pipeline TRACK=./path/to/track.wav LYRICS=./path/to/song.lrc

# 3) Watch the per-scene render queue live in the browser
open http://localhost:5173   # web Director's Console (vite dev server)

# 4) Tear down when you're done
make dev:stack-down
```

`make dev:pipeline` writes its artifacts into `out/<timestamp>/` next to the repo root.

## Services

| Service    | Port | URL                     | What it does                                                                                                                                                                                                                                            |
| ---------- | ---- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `comfyui`  | 8188 | `http://localhost:8188` | Real ComfyUI worker (SDXL + Wan 2.1 nodes) — auto-loads the SDXL + Wan workflows from `backend/workflows/`. GPU required; runs in CPU mode on host machines without an NVIDIA GPU.                                                                      |
| `c4d-stub` | 8787 | `http://localhost:8787` | A FastAPI stub that pretends to drive Cinema 4D headless. Accepts the same `c4d_render_plan.json` the real C4D adapter emits and writes a stub `.exr` + `.json` manifest. Replace with the real `c4dpy` listener when you have a C4D licence + machine. |
| `bridge`   | 8788 | `http://localhost:8788` | The MelosViz Python orchestrator + FastAPI bridge (`melosviz.cli.main bridge` or `uvicorn melosviz.bridge.server:app`). Front-door for the web + desktop Director's Console.                                                                            |
| `web`      | 5173 | `http://localhost:5173` | The Vite dev server hosting `web/`. The Director's Console is the default view (mode toggle switches to the in-browser preview).                                                                                                                        |

## Architecture

```
┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  web (5173)  │───▶│ bridge (8788) │───▶│ comfyui (8188)│  image / video renders
│   Director's │    │  orchestrator │    │              │
│   Console    │    │   + event bus │    └──────────────┘
└──────┬───────┘    │   + SSE       │
       │            │   + HTTP API  │    ┌──────────────┐
       │ SSE        └──────┬────────┘───▶│ c4d-stub (8787)│  3D scene renders
       │                   │             │              │
       │                   ▼             └──────────────┘
       │            ┌──────────────┐
       └───────────▶│desktop (8788)│  Director's Console with native renderer
                    └──────────────┘
```

The bridge streams `queued / rendering / done / error` events per scene over `/api/render/events` (SSE) and `/api/render/events/recent` (JSON polling). Both the web and desktop Director's Console subscribe and light up the render queue row-by-row as each scene completes.

## Running individual services

```bash
# Just the C4D stub (no Docker required — useful for tests)
python3 -m uvicorn deploy.scripts.c4d_stub_server:app \
    --host 127.0.0.1 --port 8787

# Just the bridge
cd backend && PYTHONPATH=src python3 -m melosviz.bridge.server
# or with uvicorn directly:
cd backend && PYTHONPATH=src python3 -m uvicorn melosviz.bridge.server:app \
    --host 0.0.0.0 --port 8788

# Just the web Director's Console
cd web && bun install && bun dev
```

## Environment variables

The pipeline reads these at every step:

| Variable                          | Used by        | What it does                                                                                       |
| --------------------------------- | -------------- | -------------------------------------------------------------------------------------------------- |
| `MELOSVIZ_COMFYUI_URL`            | generate       | ComfyUI HTTP endpoint. Defaults to `http://localhost:8188`.                                        |
| `MELOSVIZ_C4D_URL`                | generate       | C4D adapter endpoint (stub or real). Defaults to `http://localhost:8787`.                          |
| `MELOSVIZ_BRIDGE_URL`             | web, desktop   | Bridge HTTP endpoint. Defaults to `http://localhost:8788`.                                         |
| `MELOSVIZ_C4D_OUTPUT_DIR`         | c4d-stub       | Where the stub writes `.exr` / `.json` per render.                                                 |
| `MELOSVIZ_COMFYUI_OFFLINE`        | generate       | `1` = don't hit ComfyUI, just emit `workflow.json` per scene.                                      |
| `MELOSVIZ_UE_BIN` / `_UE_PROJECT` | unreal adapter | UnrealEditor binary + project path.                                                                |
| `MELOSVIZ_BRIDGE_TOKEN`           | bridge         | Required bearer token on `/api/*` calls (when set).                                                |
| `MELOSVIZ_DIRECTOR_*`             | llm director   | Optional LLM credentials (provider, model, key). Falls back to deterministic templates when unset. |

## Tests

```bash
# C4D stub server
python3 deploy/scripts/test_c4d_stub_server.py

# Pipeline end-to-end (offline mode, no GPU required)
cd backend && PYTHONPATH=src python3 -m pytest tests/test_e2e_3min_pipeline.py -m "not slow" -v
```

## Troubleshooting

- **ComfyUI worker not responding**: `docker compose -f deploy/docker-compose.dev.yml logs comfyui`. First startup pulls ~12 GB of model weights (SDXL base + Wan 2.1). Set `COMFYUI_PULL_MODELS=0` in the env to skip the model download.
- **C4D stub not accepting renders**: check the stub logs at `out/dev/c4d_stub.log`. The stub writes a `.json` manifest next to every `.exr` it emits — read that to see the dispatch shape.
- **Bridge `401 Unauthorized`**: set `MELOSVIZ_BRIDGE_TOKEN=anything` on both the bridge and the desktop/web client.
- **Web Director's Console stuck on "queued"**: the bridge is probably offline. `curl http://localhost:8788/healthz` should return `{"ok": true}`.
