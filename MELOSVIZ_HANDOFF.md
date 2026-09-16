# MELOSVIZ HANDOFF — Agent Transfer Brief

**Date:** 2026-09-16
**Handoff from:** Daisy (portfolio coordinator)
**Handoff to:** [TBD — next agent assigned to Melosviz]
**Repo:** `/Users/kooshapari/CodeProjects/Phenotype/repos/melosviz`
**Branch:** `feat/melosviz-macos-signing-infisical-20260902T0048Z`
**Latest commit:** `961d871 fix(fuzz): repair cargo check after melosviz-mir crate deletion`
**Working tree:** Clean (except `.worktrees/` untracked — leftover from prior agent work, should clean or gitignore)

---

## 1. What Is Melosviz?

Music visualization authoring app. Hybrid Rust + Python + TypeScript stack. Three runtime surfaces:

- **`backend/`** — Python (FastAPI/Bridge server, `pyproject.toml`)
- **`web/`** — TypeScript (Vite + React Three Fiber + WaveSurfer)
- **`desktop/`** — TypeScript (Electrobun/Electron app)
- **`crates/`** — Rust crates
- **`fuzz/`** — Fuzz testing
- **`docs/`** — Documentation
- **`scripts/`**, **`deploy/`**, **`packaging/`**, **`api-spec/`**

## 2. Key Reference Documents (READ THESE FIRST)

| Document | Location | Size | Purpose |
|----------|----------|------|---------|
| **SPEC.md** | `./SPEC.md` | 52KB | Full product specification — vision, features, architecture, UI flows |
| **WBS.md** | `./WBS.md` | 23KB | Work breakdown structure — task list, phases, dependencies |
| **AGENTS.md** | `./AGENTS.md` | — | Agent operating rules for this repo |
| **CLAUDE.md** | `./CLAUDE.md` | — | Claude-specific instructions |

## 3. Audit Summary (from M.1 — completed 2026-09-16)

**Status:** Active, well-structured, recent commits show active development. Ready for Phase 1 work.

### What Exists
- Full hybrid stack (Rust + Python + TS)
- Backend with FastAPI
- Web frontend with R3F (React Three Fiber) for 3D viz
- Desktop shell (Electrobun/Electron)
- Fuzz testing infrastructure
- CI: CircleCI + GitHub Actions + pre-commit hooks
- Comprehensive SPEC and WBS docs

### What's Missing / Concerns for Phase 1
- `.worktrees/` untracked — should clean or gitignore
- No obvious root-level `tests/` directory — tests likely scattered in `backend/tests/`, `desktop/tests/`, `fuzz/`
- README Quick Start references `uvicorn` directly, not a unified CLI
- Rust crate count unclear from `crates/`
- No `target/` dir present (Rust not built, or cleaned)
- No obvious integration/e2e test runner at root level

## 4. What Was NOT Done (dropped before completion)

| Task | Status | Notes |
|------|--------|-------|
| M.1 Audit | **DONE** | Completed. Summary above. |
| M.2 Happy Path Design | **NOT DONE** | bear agent was reading SPEC.md + WBS.md when stopped. Had not produced output yet. Next agent should design the end-to-end happy path: import audio -> analyze -> sync -> render -> export video. |
| M.3 Happy Path Implementation | **NOT DONE** | Depends on M.2 |

## 5. Recommended Next Steps for Taking Agent

1. **Read SPEC.md and WBS.md** — these are the source of truth
2. **Run M.2** — Design the end-to-end happy path (import -> analyze -> sync -> render -> export)
3. **Run M.3** — Implement the happy path based on M.2 design
4. **Check CI status** — `cargo check` for Rust, `npm test` for TS if configured
5. **Clean `.worktrees/`** — gitignore or remove

## 6. Repo Access

```bash
cd /Users/kooshapari/CodeProjects/Phenotype/repos/melosviz
git status
git log --oneline -5
```

## 7. Context from Portfolio

Melosviz is one of 3 Phenotype repos managed in this session. The other two are:
- **Fabric** (`phenotype-fabric`) — Rust workspace for capability-aware compute topology (actively being developed, 2-node harness design complete)
- **Khostty** — Ghostty terminal fork with Phenotype CI overlay (needs upstream sync before feature work)

Melosviz was deprioritized to focus implementation resources on Fabric's 2-node harness.
