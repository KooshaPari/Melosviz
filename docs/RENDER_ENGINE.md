# Render Engine Decision — Local Studio

**Status:** Accepted  
**Date:** 2026-07-13  
**Scope:** MelosViz local studio (Electrobun desktop + Python bridge + Rust GPU export)  
**Related:** [`ARCHITECTURE.md`](ARCHITECTURE.md), [`adr/0003-spec-first-conductor.md`](adr/0003-spec-first-conductor.md), [`PERF_BENCHMARK.md`](PERF_BENCHMARK.md)

---

## Decision

**Keep bare wgpu as the studio renderer.** Do not adopt Unreal Engine for local studio. Treat Bevy as the only plausible engine upgrade path later, not a near-term switch.

For **Time-2 local studio**: fix and ship the current `melosviz-render-wgpu` binary first. Do not start Bevy or Unreal integration now.

---

## Today — `melosviz-render-wgpu`

The studio GPU path lives in `crates/melosviz-render-wgpu/`. It consumes **RenderSpec v2** (dense keyframes, scene segments, palette) and renders frames headless for export (raw RGBA → ffmpeg) or, when wired, to a wgpu surface for preview.

### Backend selection

`WgpuRenderer::new()` requests `wgpu::Backends::PRIMARY`. wgpu maps that to the platform default:

| Platform | Default backend |
|----------|-----------------|
| Windows | **DX12** |
| macOS | **Metal** |
| Linux | **Vulkan** |

On Windows, Vulkan is also available when selected explicitly. OpenGL is supported as a fallback via operator override (see below).

### Operator override

Set **`WGPU_BACKEND`** before launching the renderer or desktop sidecar that spawns it:

| Value | Backend |
|-------|---------|
| `dx12` | DirectX 12 (Windows) |
| `vulkan` | Vulkan (Linux, Windows) |
| `metal` | Metal (macOS) |
| `gl` | OpenGL (fallback; slower, wider driver coverage) |

This is the standard wgpu instance env var — no MelosViz-specific wrapper. Use it when the default adapter fails (e.g. hybrid-GPU laptops, CI smoke on software GL) or when benchmarking a specific API.

### Role in the stack

```
RenderSpec v2  →  melosviz-render-wgpu (WGSL pipelines)  →  RGBA frames  →  ffmpeg  →  MP4
```

The Python conductor routes `scene.render.engine` to adapters (Blender, TouchDesigner, FFmpeg, wgpu). The wgpu crate is the **embeddable, deterministic, offline** path aligned with ADR 0003 — no GUI project file owns render logic.

---

## Why not Unreal Engine (local studio)

Unreal remains **out of scope** as a primary MelosViz local-studio renderer. ADR 0003 Principle 10 reserves Unreal for **live stage / nDisplay** only (`NotImplementedError` stub in the conductor registry).

| Concern | Impact |
|---------|--------|
| **Packaging size** | UE runtime + content staging is orders of magnitude larger than a Rust wgpu binary inside an Electrobun desktop bundle. Conflicts with [`PACKAGING.md`](PACKAGING.md) offline/installer goals. |
| **Licensing** | Revenue-share and redistribution rules add legal/ops overhead unrelated to RenderSpec→MP4 export. |
| **Python / Electrobun sidecar mismatch** | Local studio is Electrobun (Bun) + Python FastAPI bridge + small Rust helpers. UE expects its own editor/project lifecycle, not a localhost spec conductor spawning headless frames. |
| **Problem fit** | MelosViz needs beat-deterministic **offline** frames from structured audio analysis — not a full game/editor stack. UE is overkill for RenderSpec→MP4; Blender Cycles already covers high-fidelity 3D when quality demands it. |

Unreal may reappear only for operator-owned **festival / LED-wall** deployments, not as the default desktop export engine.

---

## Why Bevy later (optional)

Bevy is the **only credible “engine upgrade”** if bare wgpu becomes limiting:

| Factor | Bare wgpu (today) | Bevy (later) |
|--------|-------------------|--------------|
| GPU API | wgpu → DX12 / Metal / Vulkan | Same — Bevy renders through wgpu |
| Scene / animation | Custom pipelines + timeline code in `melosviz-render-wgpu` | ECS, cameras, `bevy_animation`, scene graph batteries |
| Cold start | ~low ms (minimal instance) | ~100–150 ms extra app bootstrap (see [`PERF_BENCHMARK.md` §3c](PERF_BENCHMARK.md)) |
| Migration | — | Incremental: lift WGSL/shader assets and RenderSpec field mapping into Bevy systems; keep ffmpeg export pipe |

**Do not adopt Bevy now.** The current crate is the right surface area for Time-2: prove export latency, wire preview, and stabilize adapters. Revisit Bevy when scene-graph complexity (many entities, skeletal animation, editor-style iteration) exceeds what is reasonable to maintain in hand-rolled wgpu code — not before `melosviz-render-wgpu` ships.

---

## Recommendation — Time-2 local studio

1. **Fix and build** `crates/melosviz-render-wgpu` on host GPUs (Metal / DX12 / Vulkan); gate CI with `#[ignore]` GPU tests as today.
2. **Integrate export** through the existing conductor / bridge path (RenderSpec → MP4), replacing or complementing the slow Python PNG+zlib path documented in [`PERF_BENCHMARK.md`](PERF_BENCHMARK.md).
3. **Use `WGPU_BACKEND`** only for operator diagnostics — not as a permanent fork of render logic.
4. **Defer Bevy** until bare wgpu is production-stable and complexity justifies ECS.
5. **Do not scope Unreal** for local studio; keep the stage-only stub.

---

## References

- `crates/melosviz-render-wgpu/src/renderer.rs` — `Backends::PRIMARY`, headless `Rgba8Unorm` export
- `docs/intent/MelosViz.md` §3 — Unreal explicitly not a primary renderer
- `docs/adr/0003-spec-first-conductor.md` — Principle 10 (Unreal stage-only); alternatives table (Bevy deferred)
