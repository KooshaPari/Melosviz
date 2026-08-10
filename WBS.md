# WBS — Melosviz (2026-08-09)

**Repo:** Melosviz / MelosViz
**Status:** initial skeleton; expand as scope grows. Currently on
`recovery/melosviz-local-20260726` recovery branch — recovery actions
must precede new feature work.
**Owner:** forge (agent CLI). **Driver:** `proc` / `proc <id>`.

## Phase overview

Melosviz is a **music-analysis visualization tool**. The current
working tree is on a recovery branch (`recovery/melosviz-local-20260726`)
following a recovery event; new work must start by completing the
recovery tasks before proceeding to feature work.

| Phase | Tasks | Theme | Outcome |
|-------|-------|-------|---------|
| 0 | 1–5 | audit close-out + inventory | reproducible baseline |
| 1 | 6–15 | recovery-state close-out | clean main, recovery branch archived |
| 2 | 16–25 | core analyzer hardening | audio analysis pipeline verified |
| 3 | 26–35 | visualization layer (web/canvas) | UI verified |
| 4 | 36–50 | test coverage expansion | ≥70% line coverage |
| 5 | 51–60 | CI hardening (lint + type + security) | 0 findings |
| 6 | 61–70 | release hygiene (CHANGELOG, tags) | tagged releases |
| 7 | 71–80 | integrate & ship | `melosviz-v0.x` tag |

---

## Phase 0 — Audit (tasks 1–5)

| ID | Title | depends_on | ac |
|----|-------|------------|----|
| 1 | inventory modules + identify recovery artifacts | — | ac_v1 |
| 2 | scan remaining lint/type findings | 1 | ac_v1 |
| 3 | scan bandit MEDIUM findings | 1 | ac_v1 |
| 4 | audit recovery branch for uncommitted artifacts | 1 | ac_v1 |
| 5 | tag current HEAD as `melosviz-v0.x` baseline | 1–4 | ac_v1 |

---

## Phase 1 — Recovery-state close-out (tasks 6–15)

| ID | Title | depends_on | ac |
|----|-------|------------|----|
| 6 | diff `main` vs `recovery/melosviz-local-20260726` | 5 | ac_v1 |
| 7 | cherry-pick any unique recovery commits to main | 6 | ac_v1 |
| 8 | archive `recovery/melosviz-local-20260726` (don't delete) | 7 | ac_v1 |
| 9 | verify clean working tree on main | 8 | ac_v1 |
| 10–15 | recovery-state validation tests | 9 | ac_test |

---

## Ac conventions

- `ac_v1`: commit on `main` with conventional subject + DAG id in footer.
- `ac_test`: `pytest -q tests/` exits 0.
- `ac_clippy`: `cargo clippy -- -D warnings` exits 0 (if Rust crates).

---

## Notes

- Part of the **Phenotype Fleet** (cross-repo audit at
  `pheno-harness/_cockpit/XREPO_BACKLOG.json`).
- **Recovery branch policy:** archive, never delete (per
  `pheno-harness/AGENTS.md §10.5`).
- AMC / Agentora remains paused per `pheno-harness/AGENTS.md §3.2`.
- Branch taxonomy: 8-prefix (feat/, fix/, chore/, docs/, test/, refactor/,
  perf/, build/).
