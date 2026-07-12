# MelosViz Work DAG

Atomic, FR-linked tasks agents can claim independently.

```mermaid
flowchart TD
  A[CI green] --> B[Machine-trace gates]
  A --> C[RenderQuota + CircuitBreaker]
  A --> D[Audit retention]
  A --> E[Reserved-name CI]
  A --> F[Token perms + hermetics docs]
  B --> G[fr-status.yaml]
  C --> H[Re-score C02]
  D --> I[Re-score C05]
  E --> J[Re-score C06]
  F --> K[Re-score C04/C07]
  G --> L[SCORECARD + audits]
  H --> L
  I --> L
  J --> L
  K --> L
```

## Ready / in-flight (this wave)

| ID | Task | FR / pillar | Effort | Status |
|----|------|-------------|--------|--------|
| W-262 | Machine-trace gates (WBS/GAP/docs-trace CI) | C03 L30.1 | M | THIS PR |
| W-263 | RenderQuota (CPU/concurrency caps) | C02 L25 · MV-NFR-005 | M | THIS PR |
| W-264 | CircuitBreaker for bridge/render failures | C02 L26 · MV-NFR-006 | M | THIS PR |
| W-265 | Audit JSONL retention prune | C05 L49 · MV-NFR-007 | M | THIS PR |
| W-266 | Reserved-name / dep-confusion CI scanner | C06 L55 | M | THIS PR |
| W-267 | OSSF TokenPermissions sweep | C04 L39 | S | THIS PR |
| W-268 | Hermetics docs (LOCAL_RUN / CLAUDE / AIRGAP) | C07 L69 | S | THIS PR |
| W-269 | fr-status.yaml + check_fr_status.py | C03 L30.1 | S | THIS PR |
| W-270 | Re-score SCORECARD (p1-trace-c02-c06) | audit | S | THIS PR |

## Completed

| ID | Task | Status |
|----|------|--------|
| W-255 | OpenAPI export + drift CI | #135 |
| W-256 | Journey friction gate CI | #135 |
| W-257 | PARALLEL_AGENTS.md concurrency policy | #135 |
| W-258 | ThemeProvider + light theme | #135 |
| W-259 | Splash + desktop screenshot baseline | #135 |
| W-260 | Skeleton loading blocks | #135 |
| W-261 | Re-score + SCORECARD (openapi-theme-journeys) | #135 |
| W-101…W-254 | prior closeouts | #127–#134 |

## Backlog (hard / org)

| ID | Task | Effort |
|----|------|--------|
| W-223 | Native mobile (iOS/Android) | L |
| W-224 | Apple notarization / Authenticode | L |
| W-228 | Org GPG/signed-commit branch protection | org |

## Claim protocol

1. `claim W-2xx` on PR/issue.
2. Branch `feat/w2xx-<slug>`.
3. Reference FR ID in PR body.
