# audit-v38 Scorecard - MelosViz

**Repo:** KooshaPari/Melosviz
**Date:** 2026-07-08
**Repo-type profile:** desktop + CLI + library + web-app
**Auditor:** v38-scorecard-completion lane
**Commit audited:** (feat/v38-scorecard-completion tip)

> Scoring: each sub-pillar 0=? / 1=? / 2=~ / 3=+, evidence-mandatory (`file:line`).
> Cluster score = sum / (sub-pillars x 3). Grade: A≥90% · B≥75% · C≥60% · D≥40% · F<40%.

## Category Scores

| Cluster | Category | Pillars | Score (sum/max) | Pct | Grade | Top-3 gaps |
|---------|----------|---------|:---------------:|:---:|:-----:|------------|
| C00 | Architecture + Module | L0-L9 | 23/30 | 77% | B | OTel depth; hermetic release; ARCHITECTURE.md |
| C01 | CI, DX, Observability | L10-L19 | 17/30 | 57% | D | i18n; cov-fail-under; CONTRIBUTING.md |
| C02 | Error handling, API, Governance | L20-L29 | 17/30 | 57% | D | product-wide threat model; IdP; SLO machinery |
| C03 | Agent Readiness | L30 | 22/36 | 61% | C | FR catalog; WORK_DAG; machine-readable tasks |
| C04 | Security | L31-L40 | 23/30 | 77% | B | signed commits (org); cosign; CodeQL in-repo |
| C05 | Observability (deep) | L41-L50 | 20/30 | 67% | C | trace propagation; profiling; Grafana JSON |
| C06 | Supply Chain | L51-L60 | 20/30 | 67% | C | hermetic builds; license CI; frozen lock verify |
| C07 | DX, QEng, Portability | L61-L70 | 19/30 | 63% | C | fuzzing; Windows CI; mutmut weekly job |
| C08 | Eval Coverage | L71-L80 | 17/30 | 57% | D | load tests; Harbor adapter; golden corpus |
| C09 | Accessibility + UX | L81-L95 | 25/30 | 83% | B | automated a11y CI; focus choreography |
| C10 | Visual Identity | L96-L107 | 23/36 | 64% | C | VISUAL_SPEC; golden screenshots; light theme |
| C11 | Packaging + Distribution | L108-L122 | 25/45 | 56% | D | Windows CI installer; auto-update; mobile |

## Overall

**Weighted overall score:** 66% · **Overall grade:** C

(Equal-weight mean of cluster percentages:
(77+57+57+61+77+67+67+63+57+83+64+56) / 12 = **65.5%** → **C**.)

## Headline Findings

- **Strongest:** C09 Accessibility/UX (83% B); C00 Architecture (77% B); C04 Security after supply-chain lifts (77% B).
- **Weakest:** C11 Packaging D (56%) without Windows CI/auto-update; C01/C02/C08 still D on DX/gov/eval depth.
- **Highest-leverage fix:** Add a Windows release job + OTLP exporter defaults — moves C11 and deepens C05.
- **Agent-readiness verdict (C03):** Agents can work from SPEC/TRACEABILITY/tests, but lack a formal FR catalog + WORK_DAG.
- **Time-2 verdict (C11):** macOS DMG + Linux CLI + source install work today; Windows is documented but not CI-packaged.

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
