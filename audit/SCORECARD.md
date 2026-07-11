# audit-v38 Scorecard - MelosViz

**Repo:** KooshaPari/Melosviz
**Date:** 2026-07-11
**Repo-type profile:** desktop + CLI + library + web-app
**Auditor:** v38-corpus-cosign-fuzz lane
**Commit audited:** (feat/v38-corpus-cosign-fuzz tip)

> Scoring: each sub-pillar 0=? / 1=? / 2=~ / 3=+, evidence-mandatory (`file:line`).
> Cluster score = sum / (sub-pillars x 3). Grade: A≥90% · B≥75% · C≥60% · D≥40% · F<40%.

## Category Scores

| Cluster | Category | Pillars | Score (sum/max) | Pct | Grade | Top-3 gaps |
|---------|----------|---------|:---------------:|:---:|:-----:|------------|
| C00 | Architecture + Module | L0-L9 | 26/30 | 87% | B | External SDK; Windows desktop soft-fail |
| C01 | CI, DX, Observability | L10-L19 | 23/30 | 77% | B | i18n; runner pin consistency; deeper a11y beyond fixture |
| C02 | Error handling, API, Governance | L20-L29 | 22/30 | 73% | C | IdP; crypto key lifecycle; multi-tenant |
| C03 | Agent Readiness | L30 | 27/36 | 75% | B | VISUAL polish tooling; journey depth |
| C04 | Security | L31-L40 | 25/30 | 83% | B | signed commits (org); notarization |
| C05 | Observability (deep) | L41-L50 | 28/30 | 93% | A | always-on continuous profiler agent |
| C06 | Supply Chain | L51-L60 | 26/30 | 87% | B | hermetic builds; reserved-name CI scanner |
| C07 | DX, QEng, Portability | L61-L70 | 26/30 | 87% | B | host-gated desktop e2e; longer fuzz farm |
| C08 | Eval Coverage | L71-L80 | 29/30 | 97% | A | licensed real-track corpus (legal) |
| C09 | Accessibility + UX | L81-L95 | 27/30 | 90% | A | focus choreography; canvas SR depth |
| C10 | Visual Identity | L96-L107 | 27/36 | 75% | B | palette drift; desktop/R3F screenshot corpus |
| C11 | Packaging + Distribution | L108-L122 | 33/45 | 73% | C | mobile; Authenticode/notarization; air-gap |

## Overall

**Weighted overall score:** 83% · **Overall grade:** B

(Equal-weight mean of cluster percentages:
(87+77+73+75+83+93+87+87+97+90+75+73) / 12 = **83.1%** → **B**.)

## Headline Findings

- **Strongest:** C08 Eval (97% A); C05 (93% A); C09 (90% A).
- **Weakest:** C02 (73% C); C11 Packaging (73% C).
- **Highest-leverage next:** org signed-commits · notarization/Authenticode · mobile (product) · air-gap bundle.
- **Agent-readiness:** multi-genre goldens + cargo-fuzz + Criterion smoke + Harbor/parity.
- **Time-2:** GHCR + multi-OS releases + SHA256SUMS + cosign + Electrobun auto-update.

## Delta vs prior closeout (~82% B)

| Cluster | Before | After | Lift |
|---------|--------|-------|------|
| C04 | 80% B | 83% B | +3 |
| C05 | 90% A | 93% A | +3 |
| C07 | 80% B | 87% B | +7 |
| C08 | 93% A | 97% A | +4 |
| Overall | 82% B | 83% B | +1 |

## Spine links

- Rubric: [phenotype-org-audits/audit-v38](https://github.com/KooshaPari/phenotype-org-audits/tree/main/audit-v38)
- Registry: [phenotype-registry](https://github.com/KooshaPari/phenotype-registry/blob/main/catalog/registry.yaml) (`melosviz`)
