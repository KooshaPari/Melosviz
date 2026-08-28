# Migration: MelosViz v1 (in-browser R3F) → v2 (studio pipeline)

## TL;DR

v1 rendered short looping clips in a browser using Three.js + R3F + a
TypeScript WebGPU preview. v2 produces a full 3-5 minute festival /
club / YouTube-grade music video by orchestrating industry-standard
post-production tools (ComfyUI, Cinema 4D, Unreal Engine 5, After
Effects, DaVinci Resolve) from a Python backend, with a thin web +
desktop Director's Console for review.

## What changed

| v1 | v2 |
|---|---|
| In-browser Three.js + R3F | Python orchestrator + ComfyUI / C4D / UE / AE / Resolve |
| Browser-side `visualizer.ts` | `melosviz.cli.main storyboard → generate → assemble → master → ship` |
| `viz:visualize` desktop tab | `viz storyboard` + `viz generate` + per-scene workflow JSONs |
| Loop-based shader-driven clips | Lyric-aligned, beat-synced, multi-scene timeline |
| Browser preview only | ProRes / MP4 / WAV / SRT / stems / manifest `final.zip` |
| No AI text-to-video | ComfyUI + Wan 2.1 / SDXL pipelines |
| No audio mastering | LUFS-targeted ffmpeg `loudnorm` 2-pass + dither + AI stem split |

## What kept

- `melosviz` Python package layout
- WAV analysis pipeline (MIR: tempo / beats / structure / segments)
- `RenderSpec` / `RenderPlan` data models
- Tauri / Electrobun desktop shell (Electrobun preferred)
- i18n (en + es) keys
- Per-scene R3F `web/fixtures/r3f-canvas.html` as a static reference

## API surface (what to port if you have v1 plugins)

v1's plugin points:
- `RenderPlan.visualizer_extensions` → v2's `viz storyboard --concept`
- `Bridges.subscribeRender` → v2's `/api/render/events?job_id=...` SSE
- `Bridge.preview(plan)` → v2's `viz assemble` + `viz master`
- `Bridges.exportMp4` → v2's `viz ship` (final.zip)

v1's removed APIs:
- `Bridges.r3fScene` (browser R3F preview is gone in product paths)
- `plan.captureLoop()` (no longer loop-based)

## Workflow: porting a v1 project to v2

1. Export the audio + lyrics + concept from your v1 project
2. `viz storyboard track.wav --lyrics lyrics.lrc --concept "..." --out sb.json`
3. `viz generate track.wav --storyboard sb.json --out ./out`
4. `viz assemble ./out`
5. `viz master ./out/assembly/assembly_plan.json --lufs-target youtube --export-stems`
6. `viz ship ./out/master`

Result: `final.zip` containing the festival ProRes, club MP4, YouTube
MP4, audio stems, SRT captions, and the source storyboard.json — ready
for delivery.

## Migration timeline

- **2026-Q2**: v1 deprecated, v2 branch created
- **2026-Q3**: v2 ships CI + docker dev stack + Director's Console
- **2026-Q4**: v1 plugin compatibility layer removed

See `docs/STUDIO_PIPELINE.md` for the full v2 architecture,
`docs/MUSIC_VIDEO_GUIDE.md` for the "I want a music video" end-to-end
walkthrough, and `docs/DEPTH_LAYER.md` for the per-feature depth layer.