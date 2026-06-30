# ADR 0003 — Spec-First Conductor over Pro Toolchain

**Status:** Accepted  
**Date:** 2026-06-29  
**Deciders:** kooshapari  
**Supersedes:** —  
**Traceability IDs:** MV-NFR-001, MV-FR-A01 through MV-FR-A10

---

## Context

MelosViz generates music videos from audio files. The core problem: most existing
visualizers (Spotify Canvas, GFX-only loops) are hand-authored animations loosely
aligned to vibe — not to the actual audio signal. A system that wants 100% beat-
deterministic sync must drive visuals directly from structured audio analysis.

Two competing approaches were considered:

1. **GUI-first tooling** — author in TouchDesigner/After Effects/Blender natively;
   sync manually or via MIDI cues. Fast for one-off content, brittle for automation.

2. **Spec-first conductor** — define a canonical `RenderSpec` (YAML/JSON) as the
   source of truth; all GUI tools are orchestrated from it; no logic lives in GUI
   project files.

The operator's original exploration (ChatGPT-Programmable Music Visualizers.md,
§ "Offline 'perfect sync' pipeline") identified the spec-first path as the correct
one: preprocess the WAV → extract structure → generate visuals from data timeline →
render frames offline → encode video. This guarantees exact beat alignment, zero
drift, reproducibility, and the ability to "compose" visuals like music.

---

## Decision

MelosViz adopts a **spec-first conductor** pattern over a **pro toolchain**:

### Principle 1 — Source of truth outside any GUI

`RenderSpec v2` (Pydantic model, YAML/JSON-exportable) is the canonical definition of
every render. No logic lives inside `.toe` / `.aep` / `.blend` project files. GUI
tools are downstream consumers of the spec, not the authoring environment.

- **Implementation:** `backend/src/melosviz/analysis/models.py::RenderSpec`
- **Traceability:** MV-FR-A01

### Principle 2 — Conductor routes each scene/segment to the best tool

A Python `conductor` layer inspects `scene_type` and routes to the best-fit adapter:
Blender for offline 3D/Cycles, After Effects for motion-graphics + roto, Media
Encoder for assembly/transcode, Firefly for generative assets, TouchDesigner for live
IO, FFmpeg for lightweight fallback. No tool is used outside its strength.

- **Implementation:** `backend/src/melosviz/conductor/orchestrator.py::route_scene()` + `registry.py::ADAPTER_REGISTRY`
- **Traceability:** MV-FR-A02

### Principle 3 — Hybrid scene representation (5 domains)

The scene is modelled as a union of 5 independent representation domains: `photo`
(equirect / projected video), `mesh` (polygon geometry), `splat` (Gaussian splat
3DGS), `performer` (roto-extracted talent), `fx` (shader-based generative effects).
Each domain has its own material preset family. A `ScannerSpec` acts as a volumetric
mask generator that writes into named channels, which `TransitionSpec` rules consume
to compute per-domain opacities in real time.

- **Implementation:** `backend/src/melosviz/scene/models.py` + `scene/scanner.py`
- **Traceability:** MV-FR-A03

### Principle 4 — Disco-ball scanner = volumetric mask generator

The scanner is not a light; it is a spatial write-head. Its cone/sphere/spline
footprint, beat-locked rotation, Perlin noise, and occlusion mode compute a
`ChannelMaskFrame` per audio frame. TransitionSpec opacity rules consume these channel
values to drive cross-domain fades — this is how "DJ stays photoreal while room flips
to splat on the drop" works.

- **Implementation:** `backend/src/melosviz/scene/scanner.py::evaluate_scanner()`
- **Traceability:** MV-FR-A04

### Principle 5 — Round-trip: GUI edits serialize to overrides.yaml

Operators can adjust parameters in TouchDesigner's live preview. Those adjustments
are serialized to `overrides.yaml`, diffed against the canonical RenderSpec, and
re-applied non-destructively. This eliminates GUI lock-in: the spec is always the
authority; the GUI edit is a named deviation.

- **Implementation:** `backend/src/melosviz/runtime/touchdesigner/overrides.py` + `cli/main.py diff/apply`
- **Traceability:** MV-FR-A05

### Principle 6 — Blender + Cycles as first-class offline 3D renderer

Blender Cycles headless (bpy driver) is the primary renderer for offline 3D scenes.
All MIR fields are wired into Blender geometry nodes / shader drivers. Output is
100% deterministic given the same RenderSpec (seeded randomness only).

- **Implementation:** `backend/src/melosviz/render/blender_exporter.py` (720 LOC)
- **Traceability:** MV-FR-A06

### Principle 7 — After Effects for motion-graphics + Roto Brush 3

After Effects + nexrender is the motion-graphics path: MOGRT templates receive
beat-derived data, and Roto Brush 3 extracts performer mattes. This path is used
only for `motion_graphics_beat_sync` scene types. It is explicitly not used for
offline 3D animation.

- **Implementation:** `backend/src/melosviz/render/aftereffects_adapter.py`
- **Traceability:** MV-FR-A07

### Principle 8 — TouchDesigner as live IO glue, not core logic

TouchDesigner owns live preview, OSC/WS bridge, and NDI/Spout output to hardware.
Its `.toe` network is auto-generated from the RenderSpec by a Python generator; no
node-spaghetti is authored manually. TD is not used for offline render.

- **Implementation:** `backend/src/melosviz/runtime/touchdesigner/` (generator + bridge + adapter + scheduler)
- **Traceability:** MV-FR-A08

### Principle 9 — Flash-safety limiter before any render

A luminance flash-rate check (`FLASH_SAFETY_MAX_HZ = 3.0 Hz`) is applied to the
composed keyframe sequence before export. This is not an advisory warning — renders
that exceed the photosensitivity threshold are rejected. Applies to both per-adapter
export and cross-segment assembly.

- **Implementation:** `backend/src/melosviz/render/blender_exporter.py::apply_flash_safety()` + `compose/assemble.py::cross_segment_flash_safety()`
- **Traceability:** MV-NFR-001

### Principle 10 — Unreal/nDisplay is stage-only, not primary

Unreal Engine is explicitly not a primary renderer. Its adapter slot is reserved
(raises `NotImplementedError`) for live-stage/LED-wall use by the operator when
hardware is present. All offline and preview render passes use other adapters.

- **Implementation:** `backend/src/melosviz/conductor/registry.py` stub
- **Traceability:** MV-FR-A10

---

## Consequences

**Positive:**
- Full reproducibility: same RenderSpec → byte-identical output across runs.
- Agent-operable: RenderSpec is YAML/JSON, editable by LLM agents without GUI.
- Best-tool fidelity: Blender Cycles for 3D quality; AE for motion-gfx; TD for live latency.
- No GUI lock-in: all project logic lives in Python + spec files, committed to VCS.
- Festival-ready: OSC lookahead scheduler + TD live adapter support zero-drift live shows.

**Negative / Trade-offs:**
- External tools (AE, ME, Firefly) require system-level access; stub adapters need live-test on a system with those tools installed.
- Blender headless bpy adds ~3 s cold-start per render job; mitigated by persistent worker process.
- Performers still require manual Roto Brush 3 upstream pass until AE UXP scripting matures.
- 3DGS training pipeline is external (graphdeco-inria); users supply pre-trained `.ply`/`.splat` assets.

---

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| GUI-first (native TD/Blender authoring) | GUI project files are opaque; agent-unreadable; no deterministic export |
| Single renderer (Blender only) | Motion-gfx and live-preview quality loss; AE Roto Brush 3 is irreplaceable for performer extraction |
| Real-time only (no offline render) | Beat drift accumulates; no determinism guarantee; festival-quality requires offline Cycles |
| Bevy/Rust as primary renderer | Immature 3D ecosystem for this use case; Blender Cycles quality gap too large |

---

## References

- Vision source: `~/Downloads/ChatGPT-Programmable Music Visualizers.md` §§ "Offline perfect sync pipeline", "Split system (core brain + renderer bridge)"
- Audit initiative: `.audit-run-v37/initiatives/MELOSVIZ.md` § "ADR 0003 — ARCHITECTURE LOCKED"
- RenderSpec v2: `backend/src/melosviz/analysis/models.py`
- Conductor: `backend/src/melosviz/conductor/orchestrator.py`
- Traceability matrix: `docs/TRACEABILITY.md`
