# MelosViz — Product Specification

> **Top-level product spec.** This is the page a new contributor reads to
> understand the whole product. For inner FR-N requirements (preset library,
> video exporter), see [`docs/specs/SPEC.md`](docs/specs/SPEC.md). For
> architecture rationale, see
> [`docs/adr/0003-spec-first-conductor.md`](docs/adr/0003-spec-first-conductor.md).
> For traceability, see [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md).
>
> **Spec ID:** MV-FR-54 (this document)
> **Inner FR-N spec ID:** MV-SPEC-MV-FR-54 (defined at
> `docs/specs/top_level_spec_md_spec.md`)
> **Validated by:** `backend/tests/test_top_level_spec_md_spec.py`

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Domain Model](#2-domain-model)
3. [Adapter Contract](#3-adapter-contract)
4. [Spec Format v2 (RenderSpec JSON Schema)](#4-spec-format-v2-renderspec-json-schema)
5. [Render Pipeline](#5-render-pipeline)
6. [Failure Modes](#6-failure-modes)
7. [Cross-Surface Boundaries](#7-cross-surface-boundaries)
8. [Test Strategy](#8-test-strategy)
9. [Distribution](#9-distribution)
10. [Revision History](#10-revision-history)

---

## 1. Architecture

MelosViz is a **spec-first music-video renderer**. The system ships as four
production surfaces plus two SDK stubs, all coordinated around a single
canonical artifact: the `RenderSpec v2`.

### 1.1 Surfaces (verified layout, not aspirational)

| Surface | Path | Purpose | Build status |
|---|---|---|---|
| **Python backend library** | `backend/src/melosviz/` | Core DSP, MIR, adapter orchestration, CLI | Shipped (CI: `backend` job) |
| **Electrobun desktop shell** | `desktop/` (entry `src/index.ts` + `views/main/index.html`) | Native macOS/Windows app — bundles the Python backend as a sidecar | Shipped (CI: `release.yml::macos-desktop`) |
| **React/R3F web surface** | `web/` (build artifacts only in repo; sources tracked in worktrees) | Browser preview / R3F playground | Planned — see § 8.3 (gap honestly documented) |
| **Rust MIR analyzer** | `crates/melosviz-mir/src/` (`lib.rs`, `mir.rs`, `spec.rs`, `wav.rs`, `dsp.rs`) | Fast MIR pre-pass (≈0.82s for 180s WAV) called by the bridge before the Python fallback | Shipped (compiled into `linux-cli` tarball) |
| **Rust wgpu renderer** | `crates/melosviz-render-wgpu/src/` (`renderer.rs`, `pipeline.rs`, `scene_runner.rs`, `shaders/`) | GPU-side frame encoder; ships as `melosviz-render` binary | Shipped (compiled into `linux-cli` tarball) |
| **Python SDK stub** | `sdk/python/` | Type-stub-only SDK for external Python consumers | Stub (no PyPI publish) |
| **Rust SDK stub** | `sdk/rust/` | Crate-shell SDK for external Rust consumers | Stub (no crates.io publish) |

The repo root is the workspace for the Rust crates
(`Cargo.toml:3-6` lists both members); Python is configured as a `setuptools`
package rooted at `backend/src/` (`backend/pyproject.toml:60-64`).

### 1.2 Surface interaction (one-line summary)

The desktop shell ships a Bun main process (`desktop/src/index.ts`) that calls
a Python FastAPI bridge sidecar (`backend/src/melosviz/bridge/server.py`) over
localhost HTTP. The bridge either delegates to the **Rust MIR binary** (if
present) or falls back to the **Python MIR** in `backend/src/melosviz/analysis/`.
The returned `RenderSpec` flows through the **conductor** in
`backend/src/melosviz/conductor/orchestrator.py`, which selects a renderer
adapter from `backend/src/melosviz/conductor/registry.py::ADAPTER_REGISTRY`.

### 1.3 Boundary diagram

```
        ┌─────────────────────────────────────────────────┐
        │  desktop/ (Electrobun)                          │
        │  ┌─────────────────┐    HTTP localhost          │
        │  │ Bun main (TS)   │ ◄──────────────────────┐   │
        │  │ src/index.ts    │                        │   │
        │  │ + views/main/   │                        │   │
        │  └─────────────────┘                        │   │
        └─────────────────────────────────────────────────┘
                                                         │
                                                         ▼
        ┌─────────────────────────────────────────────────┐
        │  backend/src/melosviz/bridge/server.py          │
        │  (FastAPI sidecar)                              │
        │                                                  │
        │   ┌──────────────────────┐                      │
        │   │ Rust MIR binary      │  ◄── try first        │
        │   │ crates/melosviz-mir  │      (~0.82s/180s)    │
        │   └──────────┬───────────┘                      │
        │              │ fallback on missing/fail         │
        │              ▼                                  │
        │   ┌──────────────────────┐                      │
        │   │ Python MIR fallback  │                      │
        │   │ analysis/audio.py    │                      │
        │   └──────────┬───────────┘                      │
        │              │ RenderSpec v2 (JSON)             │
        │              ▼                                  │
        │   ┌──────────────────────┐                      │
        │   │ Conductor            │                      │
        │   │ orchestrator.py      │                      │
        │   └──────────┬───────────┘                      │
        │              │ route_scene(scene_type)          │
        │              ▼                                  │
        │   ┌──────────────────────┐                      │
        │   │ Adapter registry     │                      │
        │   │ registry.py          │                      │
        │   │ (6 entries:          │                      │
        │   │  generative_asset,   │                      │
        │   │  motion_graphics..., │                      │
        │   │  assembly_encode,    │                      │
        │   │  procedural_3d,      │                      │
        │   │  live_stage,         │                      │
        │   │  video_export)       │                      │
        │   └──────────┬───────────┘                      │
        │              │                                  │
        └──────────────┼──────────────────────────────────┘
                       ▼
        ┌─────────────────────────────────────────────────┐
        │  Renderers (one per adapter)                     │
        │  ─ blender_exporter.py  (offline 3D, Cycles)    │
        │  ─ aftereffects_adapter (motion-gfx, nexrender) │
        │  ─ mediaencoder_adapter (assembly, HDR)         │
        │  ─ firefly_adapter      (generative assets)     │
        │  ─ runtime/touchdesigner (live stage, OSC/WS)   │
        │  ─ video_exporter.py    (FFmpeg fallback)       │
        │  ─ wgpu_adapter.py      (wgpu frame export)     │
        └─────────────────────────────────────────────────┘
```

### 1.4 What this spec is NOT

This is not a backend-only spec. The inner `docs/specs/SPEC.md` documents two
subsystems (presets, video exporter) at the FR-N level. This top-level spec
covers the **whole product** at the system level: every surface, every
adapter, every failure mode that crosses a surface boundary, and every
release channel.

---

## 2. Domain Model

The system has one canonical artifact: **`RenderSpec v2`** (a Pydantic v2
`BaseModel`). Everything else — scenes, scanners, materials, transitions,
timelines, presets — is either a sub-model of `RenderSpec` or an
adapter-internal detail.

### 2.1 `RenderSpec` (canonical)

Defined at `backend/src/melosviz/analysis/models.py:287`. Top-level fields
include metadata, palette, layers, keyframes, timeline, presets, and the
serialized MIR summary. It is **JSON-serializable** via Pydantic's
`model_dump()` — this is the on-disk format that flows between backend,
desktop, web, and Rust.

### 2.2 `SceneSegment` (analysis → scene routing)

Defined at `backend/src/melosviz/analysis/models.py:245`. Represents one
**structurally detected** music segment (intro/verse/chorus/drop/etc.) with
its start/end timestamps and energy trajectory. Produced by librosa
structural analysis in `backend/src/melosviz/analysis/audio.py`; consumed by
`backend/src/melosviz/compose/narrator.py` to assign scene types per segment.

### 2.3 Scene sub-models (in `backend/src/melosviz/scene/models.py`)

| Class | Line | Purpose |
|---|---|---|
| `SplatAssetSpec` | `scene/models.py:33` | Gaussian-splat asset descriptor (ply/splat, sh_degree, opacity_threshold) |
| `ScannerSpec` | `scene/models.py:206` | Geometric scanner (cone/sphere/spline, rotation, noise, occlusion) |
| `SceneSpec` | `scene/models.py:291` | Container for one scene's assets + scanners + transitions |
| `MaterialSpec` | `scene/models.py:358` | Per-domain material with 31 look presets (`DomainMaterialLook` enum) |
| `TransitionSpec` | `scene/models.py:416` | Cross-domain opacity rules driven by scanner channels |
| `Domain` enum | `scene/models.py:152` | `photo / mesh / splat / performer / fx` — the 5 representation domains |
| `SemanticScannerSpec` | `scene/models.py:119` | Audio-condition rule-based scanner (P8 feature) |

### 2.4 MIR sub-models

| Class | Line | Purpose |
|---|---|---|
| `MIRSummary` | `analysis/models.py:266` | Top-level MIR: BPM, key, mode, mood, chord_sequence, sections |
| `DenseKeyframe` | `analysis/models.py:178` | One frame at 10 Hz with stems, spectrum, easing hint |
| `TimelineEvent` | `analysis/models.py:222` | Beat/downbeat/onset events with timestamps |
| `StemFrame` | `analysis/models.py:169` | Per-frame stem energies (drums/bass/vocals/other) |
| `MoodVector` | `analysis/models.py:238` | Per-second mood trajectory |

### 2.5 Adapter contract overview

Every renderer adapter in `backend/src/melosviz/render/` implements the same
interface (see § 3). The conductor selects which adapter to invoke by
`scene_type`; unknown `scene_type` raises (no silent fallback — see
MV-NFR-003 in `docs/TRACEABILITY.md:135`).

---

## 3. Adapter Contract

### 3.1 Required interface

Every adapter in `backend/src/melosviz/render/` and
`backend/src/melosviz/runtime/touchdesigner/` must satisfy:

```python
class AdapterProtocol(Protocol):
    scene_type: str  # class attribute matching ADAPTER_REGISTRY key

    def render(
        self,
        render_spec: RenderSpec,
        *,
        output_path: Path | str | None = None,
        **kwargs: Any,
    ) -> Any: ...
```

The exact contract is enforced by `ADAPTER_REGISTRY` in
`backend/src/melosviz/conductor/registry.py:53-78`. The six registered
keys today are:

1. `generative_asset` → `FireflyAdapter` (stub; credentials TBD)
2. `motion_graphics_beat_sync` → `AEAdapter` (stub; nexrender live-test pending)
3. `assembly_encode` → `MEAdapter` (stub; ME CLI live-test pending)
4. `procedural_3d_animation` → `_BlenderAdapterShim` (wraps `export_blender`)
5. `live_stage` → `TDAdapter` (live OSC/WS/NDI)
6. `video_export` → `_VideoExportAdapter` (FFmpeg fallback; always available)

### 3.2 Constructor / import discipline

Adapters are imported **lazily** via `_lazy()` in
`backend/src/melosviz/conductor/registry.py:22-44`. This keeps startup cost
zero — adapter modules are loaded only when their `scene_type` is first
routed.

To register a new adapter:

```python
ADAPTER_REGISTRY["my_scene_type"] = _lazy("melosviz.render.my_adapter", "MyAdapter")
```

The class must be importable as `melosviz.render.my_adapter.MyAdapter` and
must expose `scene_type` and `render()` (see § 3.1).

### 3.3 Error contract

Adapters **must raise** on failure — they must not return a sentinel value,
empty path, or swallowed exception. The conductor surfaces the exception
verbatim to the caller. See `MV-NFR-003` ("No silent failures") in
`docs/TRACEABILITY.md:135`.

Recognized exception classes:

| Exception | Module | Triggered by |
|---|---|---|
| `BlenderNotFoundError` | `melosviz.render.blender_exporter` | `bpy` driver missing or not on `$PATH` |
| `RenderExportError` | `melosviz.render.video_exporter` | FFmpeg non-zero exit, missing/empty output file |
| `FFMpegNotFoundError` | `melosviz.render.video_exporter` | `_resolve_ffmpeg_binary` could not locate ffmpeg |
| `NotImplementedError` | `melosviz.conductor.registry` | Unknown `scene_type` (e.g. `unreal_ndisplay`) |

### 3.4 Configuration schema (environment variables)

Adapters and bridge endpoints read configuration from these environment
variables (verified by reading `backend/src/melosviz/bridge/server.py`,
`backend/src/melosviz/render/video_exporter.py`, `backend/src/melosviz/bridge/security.py`):

| Env var | Default | Used by | Effect |
|---|---|---|---|
| `MELOSVIZ_BRIDGE_ALLOW_PUBLIC` | `0` | bridge | Allow binding non-loopback interfaces |
| `MELOSVIZ_BRIDGE_REQUIRE_AUTH` | `0` | bridge | Require bearer token |
| `MELOSVIZ_BRIDGE_TOKEN` | (none) | bridge | Expected bearer token |
| `MELOSVIZ_BRIDGE_ALLOWED_DIR` | (none) | bridge | Restrict `wav_path`/`out_dir` to this dir |
| `MELOSVIZ_FFMPEG_BIN` | (none) | video exporter | Override ffmpeg binary path |
| `FLASH_SAFETY_MAX_HZ` | `3.0` | render | Reject renders exceeding flash rate |
| `MELOSVIZ_DATA_DIR` | `~/.melosviz` | bridge | Audit log directory |
| `BRIDGE_PORT` | (none) | CI only | Fixed port for the bridge sidecar |

Adapters that fail to read a required env var must raise at construction
time, not silently substitute a default.

---

## 4. Spec Format v2 (RenderSpec JSON Schema)

`RenderSpec v2` is the on-disk format that flows between surfaces. It is
JSON-serializable via Pydantic `model_dump()`.

### 4.1 Top-level shape (informal)

```jsonc
{
  "version": "v2",
  "metadata": { "preset": "cinematic", "title": "...", "artist": "..." },
  "palette": ["#0d0d10", "#7c6af7", "#f472b6", "#22d3ee", "#c084fc", "#f0f0f8"],
  "layers": [ /* Layer dicts (palette → domain → keyframes → mask) */ ],
  "keyframes": [ /* DenseKeyframe dicts at 10 Hz */ ],
  "timeline": [ /* TimelineEvent dicts (beat/downbeat/onset) */ ],
  "mir": {
    "tempo_bpm": 124.0,
    "duration_s": 180.5,
    "key": "F# minor",
    "mode": "minor",
    "chord_sequence": [...],
    "sections": [ /* SceneSegment list */ ]
  },
  "presets": { /* preset metadata */ }
}
```

### 4.2 Required vs optional fields

| Field | Required | Default |
|---|---|---|
| `version` | yes | `"v2"` |
| `metadata` | no | `{}` |
| `palette` | no | `[]` |
| `layers` | no | `[]` |
| `keyframes` | no | `[]` |
| `timeline` | no | `[]` |
| `mir` | no | `None` (filled by analyzer) |
| `presets` | no | `{}` |

### 4.3 Round-trip stability

`RenderSpec.model_validate(json.loads(model_dump_json(spec))) == spec` must
hold for all spec instances. This is verified by
`backend/tests/test_render_spec_v2.py`.

### 4.4 Versioning rule

The `version` field is bumped on any breaking change to the schema. v1 → v2
was the introduction of Pydantic v2 and the removal of deprecated alias
fields. Future breaking changes will increment to `v3`, etc.

---

## 5. Render Pipeline

The end-to-end pipeline is **five stages**, each with a defined I/O contract.
The desktop UI exposes the first three as buttons ("Analyze", "Build Plan",
"Render Video"); the CLI exposes them as subcommands (`viz analyze`,
`viz build`, `viz render`).

### 5.1 Stage 1 — Analyze

- **Input:** WAV path (string or `Path`)
- **Output:** `RenderSpec v2` (JSON dict or Pydantic model)
- **Code:** `backend/src/melosviz/analysis/audio.py::analyze_wav()` /
  `spec_from_wav()`
- **Bridge route:** `POST /analyze` with `{"wav_path": "..."}`
- **Time bound:** ~0.82s for 180s audio (Rust MIR), or ~10–15s (Python
  librosa fallback)

### 5.2 Stage 2 — Compose

- **Input:** `RenderSpec v2` from Stage 1
- **Output:** `RenderSpec v2` extended with `layers`, `palette`, `timeline`
  assignments per `SceneSegment`
- **Code:** `backend/src/melosviz/compose/narrator.py::NarrativeComposer.compose()`
  + `backend/src/melosviz/compose/assemble.py::assemble_renderspec()`
- **Invariants:** no adjacent scene-type repeat (EMA novelty constraint);
  seedable RNG for reproducibility (see MV-NFR-002 in
  `docs/TRACEABILITY.md:134`)

### 5.3 Stage 3 — Route

- **Input:** Composed `RenderSpec`
- **Output:** Chosen adapter instance + render plan
- **Code:** `backend/src/melosviz/conductor/orchestrator.py::route_scene()`
- **Behavior:** Looks up `scene_type` in `ADAPTER_REGISTRY`; unknown types
  raise `NotImplementedError` (no silent fallback — MV-NFR-003)
- **Bridge route:** `POST /build` with `{"wav_path": "..."}`

### 5.4 Stage 4 — Render

- **Input:** Render plan from Stage 3 + output path
- **Output:** Frames (PNG sequence) or directly encoded video, depending on
  the adapter
- **Code:** Adapter's `.render()` (see § 3)
- **Flash-safety check:** `apply_flash_safety()` runs **before** any
  expensive render; rejects specs whose luminance flash rate exceeds
  `FLASH_SAFETY_MAX_HZ` (default 3.0 Hz). See MV-NFR-001 in
  `docs/TRACEABILITY.md:133`.

### 5.5 Stage 5 — Export

- **Input:** Frames from Stage 4 (or already-muxed video)
- **Output:** Final MP4/WebM file at `output_dir/<name>.mp4`
- **Code:** `backend/src/melosviz/render/video_exporter.py::export_video()`
- **Codec:** libx264 + yuv420p (MP4 default) or libvpx-vp9 (WebM)
- **Bridge route:** `POST /render` with `{"wav_path": "...", "out_dir": "..."}`
- **Subprocess timeout:** 120 seconds (`backend/src/melosviz/render/video_exporter.py`,
  per `MV-NFR-3` test)

### 5.6 Cross-segment assembly

For multi-segment compositions, `backend/src/melosviz/compose/assemble.py`
runs **cross-segment flash-safety** (`cross_segment_flash_safety()`) on the
full-duration assembly before encoding. This catches transitions that look
safe per segment but flash across the boundary.

---

## 6. Failure Modes

Each failure mode is documented as **name · trigger · response · recover**.
Eight or more modes must be listed (the validator test enforces this
minimum).

### 6.1 FM-01: Missing WAV file

- **Name:** Missing WAV file
- **Trigger:** Caller passes a path that does not resolve to a file.
- **Response:** Adapter raises `FileNotFoundError`; bridge returns HTTP 404.
- **Recover:** Caller verifies the path before submission. Bridge logs the
  resolved path at WARNING level before subprocess invocation.

### 6.2 FM-02: Unsupported audio codec

- **Name:** Unsupported audio codec
- **Trigger:** Input file is not a 16-bit/24-bit PCM WAV (e.g. MP3, FLAC,
  Opus).
- **Response:** MIR analyzer raises `audioop` / `wave` decode error;
  bridge returns HTTP 415.
- **Recover:** Convert to WAV upstream via `ffmpeg -i input.<ext> output.wav`.

### 6.3 FM-03: Blender (bpy) not installed

- **Name:** Blender (bpy) not installed
- **Trigger:** Renderer is `procedural_3d_animation` but `bpy` driver is not
  importable.
- **Response:** Adapter raises `BlenderNotFoundError`; bridge returns
  HTTP 503 with an `install_hint`.
- **Recover:** Install Blender (≥ 3.6 LTS) or switch the scene to
  `video_export` (FFmpeg fallback).

### 6.4 FM-04: FFmpeg not installed

- **Name:** FFmpeg not installed
- **Trigger:** Stage 5 export runs but `_resolve_ffmpeg_binary()` returns
  `None`.
- **Response:** Adapter raises `FFMpegNotFoundError`; bridge returns
  HTTP 503.
- **Recover:** Install ffmpeg ≥ 4.4 (libx264 + libvpx-vp9 recommended) or set
  `MELOSVIZ_FFMPEG_BIN` to an explicit path.

### 6.5 FM-05: Flash-safety rejection

- **Name:** Flash-safety rejection
- **Trigger:** Composed keyframes contain luminance flashes at > 3.0 Hz.
- **Response:** `apply_flash_safety()` raises `FlashSafetyError`; render
  aborts before any expensive work.
- **Recover:** Operator adjusts palette/easing in the spec or lowers
  `FLASH_SAFETY_MAX_HZ`. Cross-segment check
  (`cross_segment_flash_safety()`) handles inter-segment flashes.

### 6.6 FM-06: Bridge auth failure

- **Name:** Bridge auth failure
- **Trigger:** `MELOSVIZ_BRIDGE_REQUIRE_AUTH=1` and request lacks the
  matching bearer token.
- **Response:** Bridge returns HTTP 401; audit log records the failed
  attempt at WARNING.
- **Recover:** Caller must supply `Authorization: Bearer
  $MELOSVIZ_BRIDGE_TOKEN`. Desktop shell reads the token from the user-set
  keychain entry.

### 6.7 FM-07: Out-of-tree output path

- **Name:** Out-of-tree output path
- **Trigger:** Caller requests `out_dir` outside `MELOSVIZ_BRIDGE_ALLOWED_DIR`.
- **Response:** Bridge returns HTTP 403 with `path_containment_violation`.
- **Recover:** Caller either configures a wider `ALLOWED_DIR` or writes into
  the allowed directory. Legacy desktop mode (no auth, no override) skips
  this check for backward compatibility with pre-hardening clients.

### 6.8 FM-08: Adapter raises on unknown scene_type

- **Name:** Adapter raises on unknown scene_type
- **Trigger:** Conductor receives a `scene_type` not in `ADAPTER_REGISTRY`
  (e.g. `unreal_ndisplay` is intentionally reserved).
- **Response:** Conductor raises `NotImplementedError`; bridge returns
  HTTP 501.
- **Recover:** Caller maps the requested scene type to a registered one.
  Reserved types (e.g. Unreal) require implementing the adapter; see
  `MV-FR-A10` in `docs/TRACEABILITY.md:51`.

### 6.9 FM-09: Bridge sidecar down

- **Name:** Bridge sidecar down
- **Trigger:** Desktop shell's Bun main process cannot reach
  `http://127.0.0.1:$BRIDGE_PORT/health`.
- **Response:** Desktop shell falls back to spawning `python -m
  melosviz.cli.main` as a subprocess per request (slower, but functional).
- **Recover:** Restart the bridge (`python -m melosviz.bridge.server`) or
  reinstall `melosviz[bridge]` so the FastAPI/uvicorn deps are present.

### 6.10 FM-10: Bridge body > 1 MiB

- **Name:** Bridge body > 1 MiB
- **Trigger:** `POST /analyze` body exceeds 1 MiB.
- **Response:** Bridge returns HTTP 413; audit log records the rejected
  attempt.
- **Recover:** Caller streams large audio files via direct CLI invocation
  instead of the HTTP bridge.

### 6.11 FM-11: Rust MIR binary missing

- **Name:** Rust MIR binary missing
- **Trigger:** `target/release/melosviz-mir` (or `debug/`) does not exist
  when the bridge tries to invoke it.
- **Response:** Bridge logs a WARNING and falls back to the Python MIR
  analyzer (`melosviz.analysis.audio.spec_from_wav`).
- **Recover:** Build the Rust workspace (`cargo build --release`). The
  `release.yml::linux-cli` job does this automatically on every tag.

---

## 7. Cross-Surface Boundaries

Each surface boundary is a defined contract. Cross-surface failures are
listed in § 6.

### 7.1 Desktop → Backend (HTTP bridge)

- **Transport:** HTTP/1.1, loopback only by default
- **Port:** Configurable (`--port` flag; CI uses 18765)
- **Auth:** Bearer token (env-gated; default off for loopback)
- **Endpoints:** `GET /health`, `POST /analyze`, `POST /build`,
  `POST /render`
- **Failure fallback:** If the bridge is down, the desktop shell spawns
  `python -m melosviz.cli.main` as a subprocess (per-bridge/server.py:6-13)

### 7.2 Backend → Rust MIR (subprocess)

- **Transport:** `subprocess.run()` with `timeout=120`
- **Binary path resolution:** `target/release/melosviz-mir` then
  `target/debug/melosviz-mir` (relative to repo root)
- **I/O contract:** CLI args `--wav <path> --out <tmpfile.json>`; stdout
  unused; tmpfile contains the JSON spec
- **Failure fallback:** Python MIR (`analysis/audio.py`)

### 7.3 Backend → Rust wgpu renderer (binary)

- **Transport:** `crates/melosviz-render-wgpu/src/main.rs` is a CLI binary
  (`melosviz-render`) packaged in the Linux CLI tarball
- **I/O contract:** Reads `RenderSpec` JSON from stdin or `--spec` flag;
  writes PNG frames to `--out-dir`
- **Failure fallback:** Python `_VideoExportAdapter` (FFmpeg) — always
  available

### 7.4 Backend → After Effects / Media Encoder / Firefly (external)

- **Transport:** CLI subprocess per adapter (e.g. `aerender`, `ffmpeg` for
  Media Encoder, `curl` for Firefly `/v3`)
- **Status:** Stubs wired (see `MV-FR-R03/R04/R05` in
  `docs/TRACEABILITY.md:109-111`); live-test pending external system access

### 7.5 Backend → TouchDesigner (OSC/WS)

- **Transport:** OSC over UDP + WebSocket
- **Direction:** Bidirectional — TD sends back override patches; backend
  sends scene changes
- **Code:** `backend/src/melosviz/runtime/touchdesigner/bridge.py` +
  `live_scheduler.py`

### 7.6 Web → Backend (planned, not shipped)

- **Transport:** TBD — likely REST against the same bridge endpoints
- **Status:** Source files for the web surface are not in the main repo;
  `web/` contains only `dist/`, `node_modules/`, `package-lock.json`,
  `package.json`. See § 8.3.

---

## 8. Test Strategy

The test strategy is **per-surface**, grounded in what is actually shipped
as of the repo scan on 2026-07-03.

### 8.1 Backend (Python)

- **Framework:** `pytest` ≥ 7.0 (declared in `backend/pyproject.toml:31`)
- **CI matrix:** Python 3.12 only (`.github/workflows/ci.yml:27-28`)
- **File count:** 25 test files in `backend/tests/*.py`
  (verified via `ls backend/tests/*.py | wc -l`)
- **Test function count:** 914 functions/methods named `test_*`
  (verified via `grep -rE "^\s*(def\|async def) test_" backend/tests/ | wc -l`)
- **Test class count:** 200 test classes
- **Coverage gate:** LCOV report (`backend/coverage/lcov.info`) consumed by
  the `quality-gate` job at threshold 100 (per `ci.yml:170`); the more
  realistic branch coverage target is documented in
  `docs/QGATE_BASELINE.md`
- **Lint:** `ruff check src/ tests/` + `ruff format --check src/ tests/`
  (per `ci.yml:46-52`)
- **SAST:** `bandit -lll -iii` (high/critical severity gate) per
  `ci.yml:75-81`

### 8.2 Desktop (Electrobun)

- **Framework:** `bun test` (per `desktop/package.json:10`)
- **File count:** 1 e2e file: `desktop/tests/e2e_desktop.test.ts`
- **CI coverage (Linux):** The bridge HTTP-layer subset runs in CI
  (`ci.yml:83-149`); the launcher-log invariants (window created, blank-view,
  RPC-transport) require macOS + AppKit and are validated on host only
  (`ci.yml:84-91`)
- **Manual gates:** macOS launcher log validation, window appearance,
  RPC transport roundtrip (see `docs/QGATE_BASELINE.md`)

### 8.3 Web (React/R3F) — **GAP**

- **Status:** Sources are not present in the main repo. `web/` contains
  only `dist/`, `node_modules/`, `package-lock.json`, `package.json`. The
  `web/package.json` declares `@react-three/fiber`, `three`, React 18,
  Vitest, and Tailwind, but no `src/` directory or test files exist yet.
- **Worktree reality:** Web sources live in feature worktrees that are not
  merged to `main`. Once they land, the contract is:
  - **Framework:** `vitest` (`web/package.json:11`)
  - **Coverage target:** TBD when sources land
- **Honest disclosure:** This is a known gap, not a documentation error.

### 8.4 Rust crates (inline tests only)

- **Framework:** Cargo's built-in `#[test]` / `#[cfg(test)]` — no
  separate `tests/` directory exists for either crate
  (verified: `ls -d crates/*/tests` returns no matches)
- **Inline test count:** 115 `#[test]` / `#[cfg(test)]` annotations
  across `crates/*/src/`
  (verified via `grep -rE "#\[(test|cfg\(test\))\]" crates/*/src/ | wc -l`)
- **Benchmarks:** `crates/*/benches/` exist (criterion-style) but are not
  part of the default `cargo test` run
- **CI:** `cargo build --release` is the only CI step for the crates
  (no `cargo test` invocation in `ci.yml`)

### 8.5 Cross-cutting

- **Traceability gate:** `trace-gate.yml` (reusable workflow from
  `KooshaPari/phenotype-pm-core`) checks that every `MV-FR-*` /
  `MV-NFR-*` ID in `docs/TRACEABILITY.md` resolves to code + test
- **Secret scan:** `gitleaks.yml` runs on every push and PR
- **Security posture:** `scorecard.yml` evaluates OpenSSF Scorecard
- **Mutation testing:** `mutmut 3.x` config in `backend/mutmut.toml`; target
  ≥ 75% kill-score; not auto-run in CI (slow)
- **Acceptance BDD:** `docs/specs/acceptance/*.feature` (presets,
  video exporter) — pytest-bdd plugin

### 8.6 What is NOT tested automatically

- After Effects nexrender templates (live-test pending external system)
- Media Encoder CLI (live-test pending external system)
- Firefly API (credentials TBD)
- macOS launcher-log invariants (host-only validation)
- Web R3F components (sources not in main repo)

---

## 9. Distribution

This section enumerates **only the channels that
`.github/workflows/release.yml` actually builds and publishes**. Aspirational
channels are listed at the end with explicit non-shipment language.

### 9.1 Channels shipped today (verified against `release.yml`)

| Channel | Artifact | Build job | Trigger |
|---|---|---|---|
| **macOS desktop DMG** | `MelosViz-<tag>-macos.dmg` | `release.yml::macos-desktop` | Push of `v*` tag |
| **Linux CLI tarball** | `MelosViz-<tag>-linux-x86_64.tar.gz` containing `melosviz-render` and `melosviz-mir` binaries + `LICENSE` | `release.yml::linux-cli` | Push of `v*` tag |
| **Windows CLI zip** | `MelosViz-<tag>-windows-x86_64.zip` containing `melosviz-render.exe` and `melosviz-mir.exe` + `LICENSE` | `release.yml::windows-cli` | Push of `v*` tag |
| **Windows desktop** (best-effort) | Electrobun package under `win-desktop-out/` | `release.yml::windows-desktop` (`continue-on-error`) | Push of `v*` tag |

Artifacts are uploaded as GitHub Actions artifacts and collated into a single
GitHub Release by the `release` job (with CycloneDX SBOM + attestations).

### 9.2 Per-channel build steps

#### 9.2.1 macOS desktop DMG

1. `cargo build --release` (workspace: `melosviz-render-wgpu`,
   `melosviz-mir`)
2. `bun install` in `desktop/`
3. `bunx electrobun build` with `ELECTROBUN_OS=macos`
4. `bunx electrobun package` with `ELECTROBUN_OS=macos`
5. Locate `.app` bundle under `desktop/build/`, copy to `MelosViz.app`
6. `hdiutil create` → UDZO-compressed DMG

#### 9.2.2 Linux CLI tarball

1. `cargo build --release`
2. Copy `target/release/melosviz-render` and `target/release/melosviz-mir`
   into `dist/`
3. Copy `LICENSE` into `dist/`
4. `tar czf` the directory tree

#### 9.2.3 Windows CLI zip

1. `cargo build --release` on `windows-latest`
2. Copy `melosviz-render.exe` and `melosviz-mir.exe` into `dist/`
3. Copy `LICENSE` into `dist/`
4. `Compress-Archive` → `MelosViz-<tag>-windows-x86_64.zip`

#### 9.2.4 Windows desktop (best-effort)

1. `cargo build --release` + Electrobun `build`/`package` with `ELECTROBUN_OS=windows`
2. Collect `.exe`/`.msi`/`.zip` under `desktop/build/` into `win-desktop-out/`
3. Job uses `continue-on-error: true` so a CLI-only Windows release still ships

### 9.3 Channels NOT shipped (explicit non-shipment)

The following distribution channels are **not currently built** by
`release.yml` and **must not** be documented as shipped elsewhere in the
repo:

- **PyPI** — the Python package is `pip install -e .`-able (CI does this)
  but no `publish` step exists in any workflow. There is no
  `twine upload` invocation.
- **crates.io** — the Rust crates build on tag but are never published
  (no `cargo publish` invocation in `release.yml`).
- **npm** — the `web/` and `desktop/` packages are `private: true`
  (`desktop/package.json:5`, `web/package.json:4`) and have no publish
  step.
- **AppImage / deb / rpm** — no Linux installer builds exist. The
  Linux artifact is a plain tarball.
- **winget / scoop** — no Windows package manager manifests exist
  (Windows CLI zip + best-effort desktop package do ship via GitHub Releases).
- **brew / Homebrew formula** — no Homebrew tap is configured.
- **OCI image** — no `docker push` or container publish step exists. A
  `Dockerfile` is present at the repo root, but CI does not build or push
  it.
- **Electrobun auto-update** — wired via `release.baseUrl` + stable-channel
  builds; manifests upload from `desktop/artifacts/` (see `docs/PACKAGING.md`).
  Canary/prerelease auto-update on GitHub Releases remains limited by
  `/releases/latest` semantics.

These channels are candidates for **future work**; see § 9.5 for the
tracking rubric.

### 9.4 Source / dev installs (not "distribution" but worth noting)

- **Backend (Python):** `pip install -e ".[test,lint,analysis]"` (per
  `ci.yml:44`)
- **Backend (bridge extras):** `pip install -e ".[bridge,analysis]"` (per
  `ci.yml:107`)
- **Desktop (Electrobun):** `bun install` inside `desktop/`
- **Rust crates:** `cargo build --release` at the workspace root

### 9.5 Future channels (aspirational — explicitly NOT shipped)

| Channel | Effort | Blocker |
|---|---|---|
| PyPI publish | Low | Requires `twine` setup + maintainer PyPI token |
| crates.io publish | Low | Requires maintainer crates.io token |
| Homebrew tap | Medium | Requires a tap repo and formula review |
| OCI image | Medium | Requires `docker buildx` + GHCR token |
| Linux installers (deb/rpm/AppImage) | High | Requires per-distro packaging logic |

These are tracked in `docs/COMPLETENESS.md` (Docker present but not
primary; Quality-of-Life 90%) and are out of scope for MV-FR-54.

---

## 10. Revision History

| Rev | Date | Author | Change |
|---|---|---|---|
| 1 | 2026-07-03 | kooshapari (via MV-FR-54 xDD chain) | Baseline top-level product spec. Authored from `docs/COMPLETENESS.md`, ADR 0003, `docs/TRACEABILITY.md`, and `docs/specs/SPEC.md`. Distribution grounded in `release.yml`; test strategy grounded in `ci.yml` + actual filesystem scan. |

Future revisions will be appended below this row, never replacing prior
entries. Each revision MUST update the `version` field at the top of this
document and add a new row here.

---

## Appendix A — Cross-References

- Inner FR-N spec: [`docs/specs/SPEC.md`](docs/specs/SPEC.md) (presets +
  video exporter, FR-1 … FR-22)
- Architecture ADR: [`docs/adr/0003-spec-first-conductor.md`](docs/adr/0003-spec-first-conductor.md)
- Traceability matrix: [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md)
- Completeness audit: [`docs/COMPLETENESS.md`](docs/COMPLETENESS.md)
- Local-run guide: [`docs/LOCAL_RUN.md`](docs/LOCAL_RUN.md)
- Quality-gate baseline: [`docs/QGATE_BASELINE.md`](docs/QGATE_BASELINE.md)
- Performance benchmark: [`docs/PERF_BENCHMARK.md`](docs/PERF_BENCHMARK.md)
- Validator test: [`backend/tests/test_top_level_spec_md_spec.py`](backend/tests/test_top_level_spec_md_spec.py)
- Spec for this spec: [`docs/specs/top_level_spec_md_spec.md`](docs/specs/top_level_spec_md_spec.md)

## Appendix B — Surface Quick Reference

| Surface | Where to start | Primary language |
|---|---|---|
| Backend | `backend/src/melosviz/analysis/models.py` | Python 3.10+ |
| Desktop | `desktop/src/index.ts` + `desktop/views/main/index.html` | TypeScript / Bun |
| Web | (planned; sources in worktrees) | TypeScript / Vite / React 18 / R3F |
| Rust MIR | `crates/melosviz-mir/src/lib.rs` | Rust (stable) |
| Rust wgpu | `crates/melosviz-render-wgpu/src/lib.rs` | Rust (stable) |
| Bridge | `backend/src/melosviz/bridge/server.py` | Python (FastAPI/uvicorn) |

End of spec.