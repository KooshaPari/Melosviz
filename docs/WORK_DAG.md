# MelosViz Work DAG

Atomic, FR-linked tasks agents can claim independently.

```mermaid
flowchart TD
  A[CI green] --> B[Web empty playlist state]
  A --> C[SDK bridge-client stub]
  B --> D[Re-score C10 94%]
  C --> D
```

## Ready / in-flight (this wave)

| ID | Task | FR / pillar | Effort | Status |
|----|------|-------------|--------|--------|
| W-288 | Web playlist empty/zero state | C10 L100 | M | THIS PR |
| W-289 | `@melosviz/bridge-client` SDK stub | C00 L2 · WBS-P3.1 | S | THIS PR |
| W-290 | Re-score SCORECARD (p1f → 94.3% A) | audit | S | THIS PR |

## Completed

| ID | Task | Status |
|----|------|--------|
| W-284 | Desktop Bun inject traceparent | #144 |
| W-285 | SPA focus-trap / modal restore polish | #144 |
| W-286 | CLI + desktop i18n scaffold (en/es) | #144 |
| W-287 | Re-score SCORECARD (p1e → 94.1% A) | #144 |
| W-279 | Desktop/web STRIDE threat model | #141 |
| W-280 | Hypothesis RenderSpec property expansion | #141 |
| W-281 | `@melosviz/brand-tokens` package stub | #141 |
| W-282 | Windows release soft-fail narrow | #141 |
| W-283 | Re-score SCORECARD (p1d wave → 93.8% A) | #141 |
| W-275 | Hermetic CI smoke (fetch once + offline check) | #140 |
| W-272 | Feedback-loop timing budgets gate | #139 |
| W-273 | Shared brand token SoT (web/desktop) | #139 |
| W-274 | Re-score SCORECARD (p1b-sde-timing-tokens) | #139 |
| W-262 | Machine-trace gates (WBS/GAP/docs-trace CI) | #136 |
| W-263 | RenderQuota (CPU/concurrency caps) | #136 |
| W-264 | CircuitBreaker for bridge/render failures | #136 |
| W-265 | Audit JSONL retention prune | #136 |
| W-266 | Reserved-name / dep-confusion CI scanner | #136 |
| W-267 | OSSF TokenPermissions sweep | #136 |
| W-268 | Hermetics docs (LOCAL_RUN / CLAUDE / AIRGAP) | #136 |
| W-269 | fr-status.yaml + check_fr_status.py | #136 |
| W-270 | Re-score SCORECARD (p1-trace-c02-c06) | #136 |
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
