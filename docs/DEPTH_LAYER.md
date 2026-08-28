# Studio Depth Layer

This document describes the depth layer added on top of the 5-step
`storyboard → generate → assemble → master → ship` pipeline. Each piece
can be used independently or composed.

## Beat-aligned cuts in assemble

`backend/src/melosviz/compose/beat_cuts.py` exposes:

```python
from melosviz.compose.beat_cuts import (
    BeatCutPlan,
    build_assemble_effects_plan,
    assemble_effects_to_ffmpeg_filter,
)

plan: BeatCutPlan = build_assemble_effects_plan(
    storyboard_json,
    downbeat_times=[0.0, 0.5, 1.0, ...],   # from MIR
    cut_on_every_n_beats=2,
    transition_style="whip_pan",            # or 'crossfade', 'flash', 'cut'
    target_fps=24,
)
```

The CLI auto-uses this when `assemble` finds a `downbeat_times.json` next
to the storyboard (offline-mode just writes the `effects.json` so the
artist can review cuts in DaVinci).

## Render cache (skip re-renders)

`backend/src/melosviz/conductor/render_cache.py`:

- `scene_cache_key(scene)` -> `sha256` of `(prompt, scene_type, width,
height, fps, model, seed)`
- `RenderCache(out_root).lookup(scene)` -> cached artifact path or `None`
- `RenderCache(out_root).store(scene, artifact_path)` -> persist

The orchestrator emits a `done` event carrying the cache key so the next
`viz generate` run skips unchanged scenes.

## Per-clip provenance

`backend/src/melosviz/conductor/provenance.py`:

Every rendered scene ships a sidecar JSON describing:

- `workflow.json` used (ComfyUI / C4D / UE / AE / Blender job)
- `cache_key`
- `model_hash` + `seed`
- `source_wav_sha256` (so re-mastering picks the exact same audio)
- `license` + `content_origin` (festival delivery metadata)
- `manifest.json` indexes all clips + provenance for the full video

## Storyboard validator

`backend/src/melosviz/conductor/validate.py`:

12 validators across `ERROR` (blocks ship) / `WARNING` / `INFO`:

| Code                             | Severity | What it checks               |
| -------------------------------- | -------- | ---------------------------- |
| `palette-too-small`              | ERROR    | scene has < 3 colors         |
| `palette-too-wide`               | WARNING  | scene has > 8 colors         |
| `aspect-ratio-mismatch`          | ERROR    | scene width/height vs preset |
| `scene-overlap`                  | ERROR    | scenes overlap in time       |
| `scene-gap`                      | WARNING  | scenes have gaps             |
| `camera-not-diverse`             | WARNING  | < 3 distinct camera motions  |
| `seed-collision`                 | WARNING  | two scenes share a seed      |
| `continuity-character-missing`   | WARNING  | no subject anchor            |
| `continuity-environment-missing` | WARNING  | no world anchor              |
| `duration-out-of-range`          | WARNING  | scene duration < 2s or > 30s |
| `beat-alignment-density`         | INFO     | cuts per minute outside 4-32 |
| `lyric-coverage-low`             | WARNING  | < 60% of lyrics linked       |
| `concept-too-vague`              | INFO     | concept prompt < 8 words     |

Run via CLI: `viz validate storyboard.json --severity warning`.
Run via bridge: `POST /api/studio/validate {"storyboard_path": ...}`.

## Art-director edit loop

```bash
viz direct storyboard.json --scene-index 3 \
    --replace-prompt "NEW: silver hair dancer, dramatic chiaroscuro"
viz direct storyboard.json --scene-index 3 \
    --replace-camera whip_pan_burst \
    --re-render \
    --wav track.wav \
    --render-out ./generate_scene3
```

Bridge: `POST /api/studio/direct`. Returns edit summary; the web Studio
Console + desktop Director's Console both consume this for in-place edits.

## Docker dev stack

```bash
make dev-up        # docker-compose -f deploy/docker-compose.dev.yml up
make dev-pipeline  # synthesize 60s WAV, run 5-step pipeline end-to-end
make dev-test      # 4/4 stub server tests
make dev-down
```

`deploy/README.md` has the service diagram + env var table.

## Live render event bus

```
/api/render/events?job_id=...           # SSE (preferred)
/api/render/events/recent?job_id=...    # JSON poll fallback
```

Web StudioConsole subscribes via `EventSource`; desktop Director's Console
receives events through the bun-side SSE proxy
(`desktop/src/index.ts: subscribeRenderEvents` / `unsubscribeRenderEvents`).
