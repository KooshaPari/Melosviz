# MelosViz Architecture

MelosViz is a **spec-first music-video renderer**. All surfaces coordinate
around one canonical artifact: **RenderSpec v2**.

```
desktop/ (Electrobun)  --HTTP localhost-->  bridge (FastAPI)
                                              |
                         +--------------------+--------------------+
                         |                    |                    |
                   Rust MIR binary      Python analysis      conductor
                   (melosviz-mir)       (librosa fallback)   (adapters)
                         |                    |                    |
                         +-------- RenderSpec v2 ------------------+
                                              |
                              +---------------+---------------+
                              |               |               |
                         Blender/TD      video_exporter    wgpu render
                         adapters        (ffmpeg)         (Rust)
```

## Surfaces

| Surface | Path | Role |
|---------|------|------|
| Python backend | `backend/src/melosviz/` | DSP, MIR, conductor, CLI, bridge |
| Electrobun desktop | `desktop/` | Native shell + Python sidecar |
| React/R3F web | `web/` | Browser preview / playlist UI |
| Rust MIR | `crates/melosviz-mir/` | Fast pre-pass analyzer |
| Rust wgpu | `crates/melosviz-render-wgpu/` | GPU frame encoder |

## Key modules (backend)

| Package | Responsibility |
|---------|----------------|
| `analysis/` | WAV → RenderSpec (stdlib + optional librosa) |
| `bridge/` | FastAPI localhost API + security middleware |
| `conductor/` | Adapter registry + orchestrator |
| `compose/` | Narrative assembly / render plans |
| `render/` | Blender / AE / ME / Firefly / video exporters |
| `runtime/touchdesigner/` | Live OSC/WS bridge |
| `cli/` | `viz` / `melosviz` console scripts |
| `observability.py` | JSON logs, metrics, optional OTel |

## Contracts

- Adapter protocol: `scene_type` + `render()` (see SPEC.md)
- Bridge routes: `/health`, `/ready`, `/metrics`, `/analyze`, `/build`, `/render`
- No silent missing-adapter fallbacks (MV-NFR-003)

## Further reading

- [`SPEC.md`](../SPEC.md)
- [`docs/adr/0003-spec-first-conductor.md`](adr/0003-spec-first-conductor.md)
- [`docs/TRACEABILITY.md`](TRACEABILITY.md)
- [`docs/WORK_DAG.md`](WORK_DAG.md)
