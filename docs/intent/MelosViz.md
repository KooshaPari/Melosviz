# MelosViz — Project Intent

> **Traceability:** MV-FR-52
> **Spec:** [`docs/specs/intent_doc_spec.md`](../specs/intent_doc_spec.md)
> **Architecture:** [`docs/adr/0003-spec-first-conductor.md`](../adr/0003-spec-first-conductor.md)
> **Status:** Accepted · 2026-07-03

This is the stakeholder-facing intent document for MelosViz. The full engineering
traceability (49 requirement IDs across vision → spec → code → test → doc → deploy)
lives in [`docs/TRACEABILITY.md`](../TRACEABILITY.md); the feature-completeness audit
lives in [`docs/COMPLETENESS.md`](../COMPLETENESS.md). This document is the short,
human-readable entry point: what it is, who it serves, what it deliberately does **not**
do, how it fails, and how we know it works.

## 1. Project Intent

MelosViz turns a single WAV file into a beat-locked music video by treating audio
analysis as the **source of truth** and rendering as a downstream, replaceable step.
Visuals are derived from a canonical `RenderSpec` (YAML/JSON) that records beats,
sections, stems, energy arcs, and scanner masks — not from hand-authored animation
keyframes. The system serves **music creators and live-performance operators** who need
*exact* beat-to-frame alignment, *full reproducibility* (same input + same seed ⇒
byte-identical output), and *zero GUI lock-in* (every parameter is editable in a
text-friendly spec, not buried in a `.toe`/`.aep`/`.blend` file). It is a Python
package (`melosviz`) with a CLI, a FastAPI bridge, an Electrobun+wgpu desktop shell,
and an FFmpeg-backed video fallback; offline frame-perfect render is its primary
delivery, with a TouchDesigner live-preview path for stage use.

## 2. Stakeholders

| Role | Who they are | What they care about |
|---|---|---|
| **Producer** | The operator who runs an end-to-end render job (audio in → MP4 out), often under deadline for a release or a festival. | Pipeline predictability, clear failure messages, time-to-first-render, repeatability across machines. |
| **Audio Creator** | The artist or engineer supplying the source WAV; expects the visuals to honour the track's structure (drops, choruses, transitions) without audible artefacts or content drift. | Beat-locked fidelity, section-aware composition, no tampering with audio content. |
| **Visual Artist** | The designer who authors or curates palettes, scanner masks, material presets, and scene templates; works in both spec and override mode. | Visual fidelity, palette coverage (31 material presets), clean round-trip between overrides and the canonical spec. |
| **Developer** | An engineer extending the adapter registry, adding a new renderer, editing the `RenderSpec` schema, or wiring a new audio analysis pass. | Spec-first guarantees, deterministic output, test coverage (370+ cases, CI-enforced), no silent fallbacks. |
| **Operator** | The runtime user running MelosViz in a live or festival setting where audio and visuals cannot drift apart. | Zero-drift sync (10 Hz dense keyframes, beat-phase lookahead), flash-safety, graceful adapter fallback when a tool is missing. |

## 3. Non-Goals

The following are **explicitly out of scope** by design. If a proposal looks like one of
these, route it elsewhere (or close it as out-of-scope) before opening a spec.

1. **Replacing Adobe After Effects as a general motion-graphics editor.** AE is one of
   several rendering *adapters* in MelosViz; it is not the editing surface. Use AE
   directly for general Mograph work.
2. **Real-time adaptive rendering off a live audio stream.** MelosViz is offline-first:
   it analyses the full WAV, builds a deterministic `RenderSpec`, then renders. Live
   previews exist via TouchDesigner but they consume a pre-built spec, not a live
   signal. ([`docs/COMPLETENESS.md` § 2.3](../COMPLETENESS.md))
3. **Training 3D Gaussian Splatting (3DGS) assets in-house.** The loader accepts
   user-supplied `.ply` / `.splat` files; the training pipeline (`graphdeco-inria`)
   lives outside this repo. ([`COMPLETENESS.md` § 2.2](../COMPLETENESS.md))
4. **Acting as a primary Unreal Engine renderer.** Unreal is **stage-only** — its
   adapter slot is reserved and raises `NotImplementedError` by design. Offline and
   preview renders go through Blender / TouchDesigner / FFmpeg.
   ([ADR 0003 Principle 10](../adr/0003-spec-first-conductor.md))
5. **Locking project state inside any single GUI's native file format.** No logic
   lives in `.toe` / `.aep` / `.blend` project files; the canonical `RenderSpec` is
   always the source of truth. GUI edits serialize to `overrides.yaml` and apply
   non-destructively. (ADR 0003 Principles 1 and 5)
6. **Auto-rotoscoping performers without an upstream AE Roto Brush 3 pass.** Performer
   mattes require manual extraction in AE; full procedural roto via AE UXP is
   post-MVP research. ([`COMPLETENESS.md` § 2.2](../COMPLETENESS.md))
7. **Acting as a music-recommendation, audio-MIR-as-a-service, or DAW-replacement
   API.** MelosViz is a single-track renderer; there is no playlist layer, no
   multi-track orchestration, and no DAW integration.

## 4. Failure Modes

The system is designed to **fail loudly and early**, never silently. The five
realistic failure modes below are how each is wired to respond.

- **Failure A — Corrupt or unsupported input WAV.** The audio decoder raises a typed
  exception with the file path and the codec reason (sample rate, channel layout, or
  truncated RIFF chunk). The CLI exits non-zero with a single-line actionable
  message. No partial `RenderSpec` is written; no MP4 is produced. (Pattern per
  [`docs/LOCAL_RUN.md`](../LOCAL_RUN.md) failure-mode notes.)
- **Failure B — Conductor receives an unknown `scene_type`.** The orchestrator raises
  `NotImplementedError` listing the unsupported scene type, the adapter that was
  requested, and the full set of supported scene types in
  `ADAPTER_REGISTRY`. Per MV-NFR-003 ("no silent failures"), there is **never** a
  fallback that masks the missing path. ([`COMPLETENESS.md` Part 3](../COMPLETENESS.md),
  ADR 0003 § Principle 2.)
- **Failure C — Flash-safety threshold exceeded during compose.** The cross-segment
  flash-safety check (`FLASH_SAFETY_MAX_HZ = 3.0 Hz`) is applied **before** any
  export. A render that would exceed the photosensitivity limit is rejected with
  the offending keyframe range and the offending `scene_type`; no MP4 is written.
  (MV-NFR-001.)
- **Failure D — Optional dependency missing on operator's host.** If `demucs` or
  `librosa` is not installed, the analysis layer falls back gracefully
  (Demucs → librosa HPSS for stem separation; librosa beat tracker for BPM when
  madmom is absent). The system never crashes the import path. (MV-FR-P08,
  [`test_optional_dep_imports.py`](../../backend/tests/test_optional_dep_imports.py).)
- **Failure E — TouchDesigner not installed for a live render.** A `viz render live_*`
  invocation on a host without TouchDesigner surfaces a clear "TouchDesigner not
  detected" message and a pointer to `LOCAL_RUN.md` — not a Python stack trace
  leaking into the operator's terminal.

## 5. Success Metrics

The system is graded against the following measurable KPIs. Each is wired to a
specific `MV-NFR-*` or `MV-FR-*` ID and is checked in CI or in the operational
benchmark suite.

- **Render success rate ≥ 99%** over the shipped P0–P5 + P7 + P8 surface
  (audio analysis → spec build → adapter dispatch → encode). Verified by
  `backend/tests/test_e2e_pipeline_smoke.py` and the 370+ test cases listed in
  [`COMPLETENESS.md` Part 4](../COMPLETENESS.md). The 3 currently-stubbed adapters
  (AE, Media Encoder, Firefly) are explicitly out of this numerator pending
  external Adobe CC system access.
- **Time-to-first-render ≤ 10 s** for a 30 s 720p30 preset on a CI-class host
  (single-threaded, no warm cache). The Blender cold-start tax is amortised by the
  persistent worker process described in ADR 0003 "Consequences: Negative".
  Tracked in [`docs/PERF_BENCHMARK.md`](../PERF_BENCHMARK.md).
- **Determinism byte-equality** — same `RenderSpec` + seed produces a
  byte-identical MP4 across runs and machines. Enforced by seeded RNG in
  `compose/narrator.py` and zero per-frame randomness in
  `render/blender_exporter.py`. (MV-NFR-002.)
- **Flash-safety pass rate = 100%** on composed keyframes before any export.
  Cross-segment check lives in `compose/assemble.py::cross_segment_flash_safety()`;
  per-adapter check lives in `render/blender_exporter.py::apply_flash_safety()`.
  (MV-NFR-001.)
- **Test coverage ≥ 60%** statements / lines / functions / branches,
  CI-enforced via `.github/workflows/ci.yml`. (MV-NFR-004,
  [`docs/QGATE_BASELINE.md`](../QGATE_BASELINE.md).)
- **Traceability coverage = 100% documented** — all 49 `MV-FR-*` / `MV-NFR-*` IDs
  in [`docs/TRACEABILITY.md`](../TRACEABILITY.md) have all 7 chain links (intent →
  spec → plan → code → test → doc → deploy) present or explicitly explained.
  Lint-enforced by `backend/scripts/check/check_traceability.py`.

---

*This document is the contract for MV-FR-52. Its presence and shape are
mechanically enforced by
[`backend/tests/test_intent_doc_spec.py`](../../backend/tests/test_intent_doc_spec.py);
edits that remove a section, drop the LOC below 50, or omit a stakeholder will fail
CI.*