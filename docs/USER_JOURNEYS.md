# MelosViz user journeys (outside-in)

Agent-facing friction map for the primary studio loops. Pair with
`docs/TRACEABILITY.md` FR IDs and `docs/EVAL.md` goldens.

## J1 — Analyze a WAV (desktop)

1. Launch MelosViz (Electrobun) or `python -m melosviz.bridge.server`.
2. Drop / pick a `.wav`.
3. Expect RenderSpec JSON (duration, envelope, onsets) without silent failure.
4. Friction: missing ffmpeg/librosa → diagnose via `scripts/diagnose.py`.

**FR:** MV-FR analyze path · **Eval:** Harbor `melosviz-analyze-sine`

## J2 — Apply preset + export

1. From a RenderSpec, apply a preset (`cinematic` / `minimal` / …).
2. Export MP4/WebM via video exporter or wgpu preview.
3. Friction: missing ffmpeg binary → loud CLI/bridge error.

## J3 — Web preview

1. `cd web && bun install && bun run dev`
2. Load analysis / playlist UI; keyboard shortcuts work.
3. Friction: WebGL/canvas a11y — use `web/a11y/fixture.html` for axe CI.

## J4 — Release install

1. Download macOS DMG / Linux CLI / Windows CLI from GitHub Releases.
2. Desktop stable builds check for updates via Electrobun Updater.
3. Friction: unsigned Windows desktop (best-effort job).

## J5 — Operator bridge

1. Scrape `/metrics`, probe `/ready`, import Grafana JSON.
2. Optional: apply `deploy/prometheus/melosviz-bridge-rules.yaml`.
3. Friction: OTLP exporter needs `melosviz[otel]` + endpoint.

## Gap log

| Journey | Known gap | Tracking |
|---------|-----------|----------|
| J3 | Canvas/WebGL SR support thin | W-204 axe fixture covers chrome only |
| J4 | No mobile native | C11 L117 |
| J1 | Real multi-genre corpus optional | C08 L71 |
