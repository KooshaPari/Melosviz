# MelosViz — Agent Quickstart

One-page entry for coding agents (C03 L30.11). Prefer this over skimming the whole tree.

## Orient (≤2 min)

| Doc | Why |
|-----|-----|
| [`CLAUDE.md`](../CLAUDE.md) | Commands, layout, non-negotiables |
| [`README.md`](../README.md) | Product + local run |
| [`docs/LOCAL_RUN.md`](LOCAL_RUN.md) | Bridge + desktop + web ports |
| [`docs/USER_JOURNEYS.md`](USER_JOURNEYS.md) | J1–J5 acceptance stories |
| [`audit/SCORECARD.md`](../audit/SCORECARD.md) | audit-v38 status |

## Traceability SoT

| Artifact | Checker |
|----------|---------|
| [`docs/WBS_PHASED.md`](WBS_PHASED.md) | `python scripts/check_wbs.py` |
| [`docs/GAP_AUDIT_QA_MATRIX.md`](GAP_AUDIT_QA_MATRIX.md) | `python scripts/check_gap_matrix.py` |
| [`docs/fr-status.yaml`](fr-status.yaml) | `python scripts/check_fr_status.py` |
| [`docs/WORK_DAG.md`](WORK_DAG.md) | claim W-xxx before editing |

## Tight feedback loop

```bash
# Backend (from repo root)
cd backend && uv run pytest -q
# Web unit / type
cd web && npm test --silent
# Trace docs
python scripts/check_wbs.py && python scripts/check_gap_matrix.py
```

Bridge: `MELOSVIZ_PROFILE=continuous` for in-process sampling; see [`OBSERVABILITY.md`](OBSERVABILITY.md).

## Do not

- Commit `target/` or regenerate lockfiles without cause
- Invent GAP/WBS statuses outside the closed enums
- Request interactive Plan-mode approval gates for routine work
