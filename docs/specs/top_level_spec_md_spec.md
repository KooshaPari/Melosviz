# MV-SPEC-MV-FR-54 — Spec for the Top-Level `SPEC.md`

> **This file is the spec (the "what") for MV-FR-54.**
> The implementation that satisfies this spec is `/Users/kooshapari/CodeProjects/Phenotype/repos/MelosViz/SPEC.md`
> (top-level, repo root).
>
> **Do not confuse with `docs/specs/SPEC.md`** — that is the existing inner FR-N
> spec (preset library + video exporter). It is referenced, not replaced.

---

## 1. Purpose

The inner `docs/specs/SPEC.md` documents only **two subsystems** (preset library
and FFmpeg video exporter) at the FR-N level. It is necessary but not sufficient
as a top-level product specification.

This spec mandates a separate, top-level **`SPEC.md` at the repository root**
that:

1. Captures the **whole multi-surface product** (backend Python lib, Electrobun
   desktop shell, React/R3F web surface, Rust crates, SDKs).
2. Documents the **adapter contract** that all renderers and runtimes must
   implement.
3. Enumerates the **RenderSpec v2 schema**, **render pipeline stages**, and
   **cross-surface boundaries**.
4. Lists **failure modes** that any consumer of MelosViz must handle.
5. Locks the **per-surface test strategy** grounded in what is actually shipped.
6. Locks the **distribution channels** that the release workflow actually builds.
7. Carries a **revision history** so future readers can audit spec drift.

The top-level `SPEC.md` is the single page a new contributor reads to understand
the product. It is referenced by `README.md`, `CONTRIBUTING.md`,
`docs/adr/0003-spec-first-conductor.md`, and the trace-gate workflow.

---

## 2. File Location (Hard Requirement)

The implementation MUST live at:

```
/Users/kooshapari/CodeProjects/Phenotype/repos/MelosViz/SPEC.md
```

That is **`<repo-root>/SPEC.md`** — the same directory as `README.md`,
`CLAUDE.md`, `Cargo.toml`, `pyproject.toml`. It is **not** `docs/specs/SPEC.md`
(which already exists and is preserved as the inner FR-N spec).

The validator test (see § 6) explicitly distinguishes between the two files by
absolute path.

---

## 3. Section Mandate

The top-level `SPEC.md` MUST contain the following **10 sections**, in this order,
each as a level-2 `##` heading. The validator test (see § 6) asserts presence
of every heading listed here.

| # | Heading | Required content |
|---|---|---|
| 1 | `## 1. Architecture` | Multi-surface layout: backend lib, Electrobun desktop, React/R3F web, Rust crates, SDKs. Boundary diagram. |
| 2 | `## 2. Domain Model` | `RenderSpec v2`, `SceneSegment`, adapter contract overview. Reference the canonical Pydantic classes. |
| 3 | `## 3. Adapter Contract` | Trait/interface contract every renderer adapter must satisfy. Error contract. Config schema (env vars). |
| 4 | `## 4. Spec Format v2 (RenderSpec JSON Schema)` | JSON Schema reference (types, required fields, defaults) for the on-disk spec format. |
| 5 | `## 5. Render Pipeline` | Five-stage pipeline: `analyze → compose → route → render → export`. Per-stage I/O contract. |
| 6 | `## 6. Failure Modes` | **At least 8 failure modes**, each with the columns: name · trigger · response · recover. |
| 7 | `## 7. Cross-Surface Boundaries` | How web ↔ desktop ↔ backend ↔ rust interact (HTTP bridge, Rust subprocess, FastAPI sidecar). |
| 8 | `## 8. Test Strategy` | Per-surface test plan grounded in actual shipped tests: backend pytest, desktop e2e, web gap, Rust inline. |
| 9 | `## 9. Distribution` | **Only channels actually shipped by `.github/workflows/release.yml`** (no aspirational channels). |
| 10 | `## 10. Revision History` | At minimum Rev 1 (2026-07-03 baseline) entry. |

Additional level-3 subheadings (e.g. `### 1.1 ...`) are encouraged; level-1
`#` is the document title. No additional level-2 headings may displace any of
the 10 required ones.

---

## 4. Length Floor

**Minimum 300 lines** (LOC, measured by `wc -l`). This excludes the inner
`docs/specs/SPEC.md` and any future spec files.

The 300-line floor is intentional: the inner spec is 315 LOC for two subsystems;
the top-level spec must cover the full product across ≥ 4 surfaces and ≥ 9
subsystems, so 300+ LOC is a conservative lower bound, not an upper one.

The validator test asserts `line_count >= 300`.

---

## 5. Grounding Mandate (Anti-Fabrication)

Every claim in the top-level `SPEC.md` MUST be verifiable against the
repository. Specifically:

1. **Architecture claims** must match actual filesystem layout
   (`backend/src/melosviz/`, `desktop/`, `web/`, `crates/melosviz-mir/`,
   `crates/melosviz-render-wgpu/`, `sdk/python/`, `sdk/rust/`).
2. **Domain Model claims** must cite real Python classes by file:line
   (e.g. `backend/src/melosviz/analysis/models.py:287`).
3. **Distribution claims** must match what `.github/workflows/release.yml`
   actually builds. Channels NOT built by the workflow (OCI, MSI, AppImage,
   deb, rpm, brew, winget, scoop) MUST NOT appear as "shipped". They may
   appear under a "Not yet shipped / aspirational" subsection with explicit
   non-shipment language, but only if they are clearly labelled.
4. **Test Strategy claims** must match actual test counts
   (e.g. `grep -rE "^\s*(def|async def) test_" backend/tests/ | wc -l`).
5. **Failure Mode count** must be ≥ 8.

If a fact cannot be verified by `grep`, `find`, `wc`, `cat`, or a file read,
it does not exist in the product and MUST NOT be documented.

---

## 6. Validator Test

A pytest module at `backend/tests/test_top_level_spec_md_spec.py` enforces
this spec. It MUST assert:

1. `Path(repo_root, "SPEC.md").exists()` is `True`.
2. `Path("docs/specs/SPEC.md").exists()` is `True` (the inner spec is preserved;
   this is a sanity check, not a check on top-level).
3. The two paths are not the same file (different `Path.resolve()` results).
4. `line_count(Path(repo_root, "SPEC.md")) >= 300`.
5. Every required heading (table in § 3) appears as a line in the file.

The test runs against the current working directory or the resolved repo root
(`parents[3]` of `backend/tests/...`).

---

## 7. Traceability

| ID | This spec contributes | Implementation contributes |
|---|---|---|
| MV-FR-54 | Defines the structure of the top-level SPEC.md | Authors the SPEC.md at the repo root |
| MV-SPEC-MV-FR-54 | (this file) | — |

This spec (`docs/specs/top_level_spec_md_spec.md`) is the spec for MV-FR-54;
the top-level `SPEC.md` is the deliverable. Both are recorded in
`docs/TRACEABILITY.md` and `docs/COMPLETENESS.md`.

---

## 8. Out of Scope

This spec does **not** mandate:

- Rewrite of the inner `docs/specs/SPEC.md` (preserved verbatim).
- New requirements on the inner spec's FR-N numbers (FR-1…FR-22).
- Changes to `docs/adr/0003-spec-first-conductor.md` (still the architecture
  authority).
- Changes to `docs/TRACEABILITY.md` content beyond adding the MV-FR-54 row.
- Changes to `docs/COMPLETENESS.md` content beyond adding the MV-FR-54 row.