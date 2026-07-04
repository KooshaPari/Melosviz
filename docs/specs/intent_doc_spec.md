# Intent Document Spec — MV-FR-52

**ID:** MV-FR-52
**Type:** Functional — Documentation Specification
**Date:** 2026-07-03
**Status:** Accepted
**Deciders:** kooshapari
**Traceability:** Traces into `docs/TRACEABILITY.md` Rev 3, `docs/COMPLETENESS.md` Part 5.

---

## Context

The MelosViz repo has a tightly wired technical chain (vision → spec → code → test → doc → deploy)
covering **49 `MV-FR-*` / `MV-NFR-*` requirement IDs** at 100% documented completeness
(`docs/TRACEABILITY.md:9`). What it does **not** have, as of Rev 2 of that matrix, is a
single stakeholder-facing document that answers four questions at a glance:

1. *What is this thing, in plain language, for someone who is not reading an ADR?*
2. *Who is it for?*
3. *What is it explicitly **not** trying to do?*
4. *How do we know it is working?*

The technical docs (`COMPLETENESS.md`, `TRACEABILITY.md`, ADR 0003) answer these in code-level
detail, but they are written *by* and *for* engineers. The intent document fills the gap: it
sits one layer above the traceability matrix, summarises the operator's vision in
human-readable prose, and exposes the non-goals and KPIs so contributors can self-route
proposals ("is this in scope?" → "read §3").

The spec for that document is captured here so that:

- The doc's section list is reviewable before authoring (no surprise document shape).
- A pytest gate (see `backend/tests/test_intent_doc_spec.py`, MV-FR-52 test) can mechanically
  validate that the doc exists, hits the LOC minimum, and contains every required section —
  preventing silent drift if anyone edits it down.
- A new `MV-FR-52` ID ties the artifact back into the traceability chain that already
  covers the engineering surface.

---

## Decision

`docs/intent/MelosViz.md` **MUST** be a single Markdown file with the following five
mandatory sections, in this order, each starting with a level-2 (`##`) heading whose
heading text begins with the section number and name:

| # | Section heading (must begin with)        | Minimum content                                                                 |
|---|------------------------------------------|---------------------------------------------------------------------------------|
| 1 | `## 1. Project Intent`                   | 3–5 sentences naming the problem, the user, and the chosen approach.            |
| 2 | `## 2. Stakeholders`                     | A table or bullet list of stakeholder roles (minimum 5 named below).            |
| 3 | `## 3. Non-Goals`                        | An enumerated list of **at least 5** explicit non-goals.                        |
| 4 | `## 4. Failure Modes`                    | At least **3** realistic failure scenarios, each with the system's response.   |
| 5 | `## 5. Success Metrics`                  | At least **3** measurable KPIs (render success rate, time-to-first-render, NPS, etc.). |

### Stakeholder roles (section 2 must include all of)

- **Producer** — the operator who runs a render job end-to-end (audio in, MP4 out).
- **Audio Creator** — supplies the source WAV; cares about beat-locked fidelity, no audible
  artefacts, no content drift in the rendered clip.
- **Visual Artist** — authors or selects scene palettes, scanner masks, material presets;
  cares about visual fidelity and round-trip override ergonomics.
- **Developer** — extends the adapter registry, adds a new renderer, edits the
  `RenderSpec` schema; cares about spec-first guarantees and test coverage.
- **Operator** — runs MelosViz in a live / festival setting; cares about zero-drift sync,
  flash-safety, and graceful adapter fallback.

### Non-goals (section 3 must enumerate at least 5)

These are *explicitly out of scope* by design (drawn from `docs/COMPLETENESS.md:135-141`
and ADR 0003 Principle 10). The intent doc MUST list at least five; recommended list:

1. Replacing Adobe After Effects as a general motion-graphics editor.
2. Realtime adaptive rendering off a live audio stream (we are offline-first).
3. Training 3D Gaussian Splatting assets in-house.
4. Acting as a primary Unreal Engine renderer (Unreal is stage-only).
5. Locking project state inside any single GUI's native file format.
6. Auto-rotoscoping performers without an upstream AE Roto Brush 3 pass.
7. Providing a music-recommendation, audio-MIR-as-a-service, or DAW-replacement API.

### Failure modes (section 4 must include at least 3)

Realistic failure scenarios with how the system must respond:

- **Failure A: Audio decoder rejects the input WAV** (corrupt, mono-only-in-stereo-stub,
  sample rate outside supported set) → system raises a typed exception with the path and
  codec reason; CLI exits non-zero with a single-line actionable error
  (`docs/LOCAL_RUN.md` failure-mode pattern).
- **Failure B: Adapter unknown for `scene_type`** → conductor raises `NotImplementedError`
  with the unsupported scene type, adapter name, and the registry's supported list
  (per `MV-NFR-003` no-silent-fallback; `docs/adr/0003-spec-first-conductor.md`).
- **Failure C: Flash-safety threshold exceeded during compose** → assembly is rejected
  before render; user sees the offending keyframe range and the offending `scene_type`; no
  MP4 is written (`MV-NFR-001`, `docs/COMPLETENESS.md:39`).
- **Failure D: Demucs / librosa optional dependency missing** → system falls back
  gracefully (Demucs → librosa HPSS) per `MV-FR-P08` (`COMPLETENESS.md:151`); never crashes
  the import path.
- **Failure E: TouchDesigner not installed on operator's host** → `viz render live_*`
  surfaces a clear "TouchDesigner not detected" message rather than a stack trace.

### Success metrics (section 5 must include at least 3)

Measurable KPIs the system is graded against:

- **Render success rate** ≥ 99% over the shipped P0–P5 + P7 + P8 surface (test evidence in
  `backend/tests/`; `COMPLETENESS.md:170`).
- **Time-to-first-render** ≤ 10 s for a 30 s 720p30 preset on a CI-class host (Blender
  cold-start amortisation target per ADR 0003 "Consequences: Negative" and
  `docs/PERF_BENCHMARK.md`).
- **Determinism byte-equality** — same `RenderSpec` + seed ⇒ byte-identical MP4 across runs
  (`MV-NFR-002`).
- **Flash-safety pass rate** 100% on composed keyframes before any export
  (`MV-NFR-001`).
- **Test coverage** ≥ 60% statements/lines/functions/branches per `MV-NFR-004`,
  CI-enforced (`COMPLETENESS.md:170`, `.github/workflows/ci.yml`).
- **Traceability coverage** 100% of `MV-FR-*` IDs referenced in the matrix have all 7 chain
  links present (`docs/TRACEABILITY.md:9`).

---

## Mechanical Validation (TDD contract)

A pytest module — `backend/tests/test_intent_doc_spec.py` — asserts the following so that
the artifact's presence and shape are CI-enforceable:

1. The path `docs/intent/MelosViz.md` (relative to repo root) exists.
2. The file contains **≥ 50** non-empty lines (LOC threshold).
3. The file contains all 5 level-2 headings above, in order, each prefixed by the
   corresponding section number.
4. Section 2 lists all 5 named stakeholder roles.
5. Section 3 enumerates at least 5 non-goals.
6. Section 4 describes at least 3 failure modes.
7. Section 5 names at least 3 KPIs.

The test MUST fail (RED) before `docs/intent/MelosViz.md` is created and MUST pass (GREEN)
once the doc satisfies the contract above.

---

## Consequences

**Positive:**
- Stakeholders and new contributors get one human-readable entry point instead of having
  to read 30 KB of traceability tables.
- The pytest gate prevents accidental truncation or section removal in future edits.
- `MV-FR-52` slots into the existing `MV-FR-*` namespace, closing a previously-undocumented
  gap in the traceability matrix.

**Negative / Trade-offs:**
- One more doc to keep in sync if the project pivots; mitigated by the mechanical pytest
  test forcing intent-doc shape to be preserved.
- Some content will overlap with `README.md` and `COMPLETENESS.md`; the intent doc is the
  short, stakeholder-facing distillation, not a duplicate.

---

## Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Embed intent content in `README.md` | README is install/usage-oriented; mixing intent dilutes it. |
| Skip the artifact; point to `TRACEABILITY.md` instead | Matrix is engineer-facing; not accessible to non-engineers. |
| Author a long whitepaper instead of a 50+ LOC file | Violates the "short and verifiable" principle; whitepapers drift. |

---

## References

- `docs/TRACEABILITY.md` — 49-ID matrix this spec extends.
- `docs/COMPLETENESS.md` — feature enumeration and gap analysis (ground-truth for non-goals).
- `docs/adr/0003-spec-first-conductor.md` — 10 architecture principles (intent source for
  failure modes and success metrics).
- `README.md` — operator-facing usage; the intent doc complements but does not replace it.
- `backend/tests/test_intent_doc_spec.py` — the pytest contract that enforces this spec.