# audit-v38 Scorecard - MelosViz

**Repo:** KooshaPari/Melosviz
**Date:** 2026-07-10
**Repo-type profile:** desktop + CLI + library + web-app
**Auditor:** v38-eval-autoupdate lane
**Commit audited:** (feat/v38-eval-autoupdate tip)

> Scoring: each sub-pillar 0=? / 1=? / 2=~ / 3=+, evidence-mandatory (`file:line`).
> Cluster score = sum / (sub-pillars x 3). Grade: A≥90% · B≥75% · C≥60% · D≥40% · F<40%.

## Category Scores

| Cluster | Category | Pillars | Score (sum/max) | Pct | Grade | Top-3 gaps |
|---------|----------|---------|:---------------:|:---:|:-----:|------------|
| C00 | Architecture + Module | L0-L9 | 26/30 | 87% | B | External SDK; continuous profiler endpoint; Windows desktop soft-fail |
| C01 | CI, DX, Observability | L10-L19 | 22/30 | 73% | C | i18n; automated a11y CI; runner pin consistency |
| C02 | Error handling, API, Governance | L20-L29 | 22/30 | 73% | C | IdP; crypto key lifecycle; PrometheusRule manifests |
| C03 | Agent Readiness | L30 | 26/36 | 72% | C | USER_JOURNEYS; screenshot goldens; friction-log CI |
| C04 | Security | L31-L40 | 23/30 | 77% | B | signed commits (org); cosign; CodeQL in-repo |
| C05 | Observability (deep) | L41-L50 | 25/30 | 83% | B | always-on profiler; PrometheusRule manifests |
| C06 | Supply Chain | L51-L60 | 20/30 | 67% | C | hermetic builds; license CI; frozen lock verify |
| C07 | DX, QEng, Portability | L61-L70 | 22/30 | 73% | C | cargo-fuzz/atheris; Makefile depth; host-gated desktop e2e |
| C08 | Eval Coverage | L71-L80 | 26/30 | 87% | B | live Harbor runner; Rust/Python parity; real-track corpus |
| C09 | Accessibility + UX | L81-L95 | 25/30 | 83% | B | automated a11y CI; focus choreography |
| C10 | Visual Identity | L96-L107 | 24/36 | 67% | C | Playwright screenshots; light theme; PROVENANCE table |
| C11 | Packaging + Distribution | L108-L122 | 29/45 | 64% | C | mobile; GHCR; Authenticode/notarization |

## Overall

**Weighted overall score:** 76% · **Overall grade:** B

(Equal-weight mean of cluster percentages:
(87+73+73+72+77+83+67+73+87+83+67+64) / 12 = **75.5%** → **B**.)

## Headline Findings

- **Strongest:** C00 Architecture (87% B); C08 Eval (87% B); C05/C09 (83% B).
- **Weakest:** C11 Packaging C (64%); C06 Supply Chain C (67%); C10 Visual C (67%).
- **Highest-leverage next:** axe/pa11y CI (C09) + CodeQL/cargo-deny (C04/C06) + GHCR image (C11 L118).
- **Agent-readiness verdict (C03):** FR catalog + WORK_DAG + Harbor adapter emit path for agent evals.
- **Time-2 verdict (C11):** Windows/macOS/Linux release channels + Electrobun stable-channel auto-update wired.

## Delta vs prior wave (2026-07-09 ~72% C)

| Cluster | Before | After | Lift |
|---------|--------|-------|------|
| C02 | 70% C | 73% C | +3 |
| C05 | 80% B | 83% B | +3 |
| C07 | 70% C | 73% C | +3 |
| C08 | 57% D | 87% B | +30 |
| C10 | 64% C | 67% C | +3 |
| C11 | 60% C | 64% C | +4 |
| Overall | 72% C | 76% B | +4 |

## Cluster file map

| Cluster | Path |
|---------|------|
| C00 | `audit/.lane-c00/C00.md` |
| C01 | `audit/.lane-c01/C01.md` |
| C02 | `audit/.lane-c02/C02.md` |
| C03 | `audit/.lane-c03/C03.md` |
| C04 | `audit/.lane-c04/C04.md` |
| C05 | `audit/.lane-c05/C05.md` |
| C06 | `audit/.lane-c06/C06.md` |
| C07 | `audit/.lane-c07/C07.md` |
| C08 | `audit/.lane-c08/C08.md` |
| C09 | `audit/.lane-c09/C09.md` |
| C10 | `audit/.lane-c10/C10.md` |
| C11 | `audit/.lane-c11/C11.md` |

## Spine links

- Rubric: [phenotype-org-audits/audit-v38](https://github.com/KooshaPari/phenotype-org-audits/tree/main/audit-v38)
- Registry: [phenotype-registry catalog](https://github.com/KooshaPari/phenotype-registry/blob/main/catalog/registry.yaml) (`melosviz`)
- Governance index: [GOVERNANCE_INDEX.md](https://github.com/KooshaPari/phenotype-org-governance/blob/main/GOVERNANCE_INDEX.md)

## How to run

1. Read `phenotype-org-audits/audit-v38/catalog/WORKER-SPEC.md`.
2. Re-score a cluster into `audit/.lane-cXX/CXX.md`.
3. Update this rollup table and recompute the equal-weight mean.
