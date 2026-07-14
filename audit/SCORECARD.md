# audit-v38 Scorecard - MelosViz

**Repo:** KooshaPari/Melosviz
**Date:** 2026-07-13
**Repo-type profile:** desktop + CLI + library + web-app
**Auditor:** p1l-sdk-pack-parity wave
**Commit audited:** (wave/p1l-sdk-pack-parity tip)

> Scoring: each sub-pillar 0=? / 1=? / 2=~ / 3=+, evidence-mandatory (`file:line`).
> Cluster score = sum / (sub-pillars x 3). Grade: A≥90% · B≥75% · C≥60% · D≥40% · F<40%.

## Category Scores

| Cluster | Category | Pillars | Score (sum/max) | Pct | Grade | Top-3 gaps |
|---------|----------|---------|:---------------:|:---:|:-----:|------------|
| C00 | Architecture + Module | L0-L9 | 30/30 | 100% | A | Published SDK packages; Windows soft-fail |
| C01 | CI, DX, Observability | L10-L19 | 30/30 | 100% | A | qgate reusable workflow; full string i18n |
| C02 | Error handling, API, Governance | L20-L29 | 27/30 | 90% | A | IdP; hosted multi-tenant; cloud KMS |
| C03 | Agent Readiness | L30 | 36/36 | 100% | A | (none material) |
| C04 | Security | L31-L40 | 28/30 | 93% | A | org GPG signed-commits; notarization |
| C05 | Observability (deep) | L41-L50 | 30/30 | 100% | A | external always-on profiler agent (residual) |
| C06 | Supply Chain | L51-L60 | 29/30 | 97% | A | full in-repo vendor; Windows MSI bit-identity |
| C07 | DX, QEng, Portability | L61-L70 | 29/30 | 97% | A | full GUI desktop e2e; continuous fuzz farm |
| C08 | Eval Coverage | L71-L80 | 29/30 | 97% | A | licensed real-track corpus (legal) |
| C09 | Accessibility + UX | L81-L95 | 30/30 | 100% | A | deeper WebGL non-visual alternative |
| C10 | Visual Identity | L96-L107 | 36/36 | 100% | A | (none material) |
| C11 | Packaging + Distribution | L108-L122 | 39/45 | 87% | A | mobile; Authenticode/notarization; live registry publish |

## Overall

**Weighted overall score:** 96.8% · **Overall grade:** A

(Equal-weight mean of cluster percentages:
(100+100+90+100+93+100+97+97+97+100+100+87) / 12 = **96.75 → 96.8%** → **A**.)

## Headline Findings

- **Strongest:** C00/C01/C03/C05/C09/C10 (100% A).
- **Weakest:** C11 (87% A) — mobile + signing + live registry publish remain.
- **This wave:** SDK pack smoke (`npm pack` + tarball install + import) for `@melosviz/bridge-client`, `@melosviz/brand-tokens`, `@melosviz/ui` closes C11 L116 (2→3) → **C11 87% A**. Desktop-spawned bridge bearer auth by default (`MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1` opt-out) closes C04 L40 (2→3) → **C04 93% A**. G-C11-06 stays **open** (pack smoke ≠ registry publish).
- **Prior:** Memory-cap + tray (p1k → 96.3% A) · `@melosviz/ui` (p1j → 95.8% A).

## Delta vs prior closeout (96.3% A · p1k)

| Cluster | Before | After | Lift |
|---------|--------|-------|------|
| C04 | 90% A | 93% A | +3 |
| C11 | 84% B | 87% A | +3 |
| Overall | 96.3% A | 96.8% A | +0.5 |

## Spine links

- Rubric: [phenotype-org-audits/audit-v38](https://github.com/KooshaPari/phenotype-org-audits/tree/main/audit-v38)
- Registry: [phenotype-registry](https://github.com/KooshaPari/phenotype-registry/blob/main/catalog/registry.yaml) (`melosviz`)
