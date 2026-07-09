# MelosViz Functional Requirements Catalog

Machine-oriented FR index. Canonical definitions and test links live in
[`TRACEABILITY.md`](TRACEABILITY.md). This file is the **section-per-FR**
catalog agents should claim from.

## How to use

1. Pick an FR ID below.
2. Open the linked TRACEABILITY / SPEC section.
3. Claim a matching task in [`WORK_DAG.md`](WORK_DAG.md).
4. Land code + test that names the FR ID.

## Catalog

### Architecture (MV-FR-A*)

| ID | Title | Status | Primary evidence |
|----|-------|--------|------------------|
| MV-FR-A01 | Spec-first conductor | DONE | `docs/adr/0003-spec-first-conductor.md` |
| MV-FR-A02 | Adapter registry (no silent fallback) | DONE | `backend/src/melosviz/conductor/` |
| MV-FR-A03 | RenderSpec v2 canonical artifact | DONE | `backend/src/melosviz/analysis/models.py` |
| MV-FR-A04 | Polyglot surfaces around one spec | DONE | `SPEC.md` §1 |

### Analysis pipeline (MV-FR-P*)

| ID | Title | Status | Primary evidence |
|----|-------|--------|------------------|
| MV-FR-P01 | Stdlib WAV → thin RenderSpec | DONE | `spec_from_wav` |
| MV-FR-P02 | Rich MIR (librosa) path | DONE | `analyze_wav_rich` / `spec_from_wav_rich` |
| MV-FR-P03 | Beat / BPM / onset fields | DONE | `analysis/audio.py` |
| MV-FR-P04 | Scene segmentation | DONE | `scene_segments` in RenderSpec |

### Scene / composition (MV-FR-S* / MV-FR-C*)

| ID | Title | Status | Primary evidence |
|----|-------|--------|------------------|
| MV-FR-S01 | Multi-domain scene model | DONE | `scene/models.py` |
| MV-FR-C01 | Narrative assembly | DONE | `compose/assemble.py` |
| MV-FR-C02 | Seeded reproducibility | DONE | `narrator.py` / composer seed |

### Rendering (MV-FR-R*)

| ID | Title | Status | Primary evidence |
|----|-------|--------|------------------|
| MV-FR-R01 | Blender offline adapter | DONE | `render/blender_exporter.py` |
| MV-FR-R02 | TouchDesigner live adapter | DONE | `runtime/touchdesigner/` |
| MV-FR-R03 | FFmpeg video exporter | DONE | `render/video_exporter.py` |
| MV-FR-R04 | Flash-safety limiter | DONE | `FLASH_SAFETY_MAX_HZ` |

### CLI / bridge / DX (MV-FR-L* / MV-FR-D*)

| ID | Title | Status | Primary evidence |
|----|-------|--------|------------------|
| MV-FR-L01 | `viz` / `melosviz` CLI | DONE | `cli/main.py` |
| MV-FR-L02 | Localhost HTTP bridge | DONE | `bridge/server.py` |
| MV-FR-50 | Self-diagnose script | DONE | `scripts/diagnose.py` |
| MV-FR-52 | Intent artifact | DONE | `docs/intent/MelosViz.md` |
| MV-FR-54 | Top-level SPEC.md | DONE | `SPEC.md` + `test_top_level_spec_md_spec.py` |

### Non-functional (MV-NFR*)

| ID | Title | Status | Primary evidence |
|----|-------|--------|------------------|
| MV-NFR-001 | Deterministic / seeded output | DONE | composer seed + docs |
| MV-NFR-002 | Perf budgets (<15s init / <5s edit) | PARTIAL | `docs/PERF_BENCHMARK.md`, perf-smoke CI |
| MV-NFR-003 | No silent failure | DONE | ConductorError / HTTP 400 mapping |
| MV-NFR-004 | Observability (logs/metrics/traces) | PARTIAL | `observability.py`, `/metrics`, OTel optional |

## Gaps (claimable)

| Gap | Suggested FR | Effort |
|-----|--------------|--------|
| Windows CI installer (desktop) | MV-FR-L10 | M |
| Auto-update channel | MV-FR-L11 | M |
| Harbor / portage eval adapter | MV-FR-E01 | L |
| Automated a11y CI | MV-NFR-005 | M |
| Light theme | MV-FR-D10 | M |

See also: [`COMPLETENESS.md`](COMPLETENESS.md), [`WORK_DAG.md`](WORK_DAG.md).
