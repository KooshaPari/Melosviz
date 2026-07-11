# MelosViz Work DAG

Atomic, FR-linked tasks agents can claim independently.

```mermaid
flowchart TD
  A[CI green on main] --> B[Rust Python parity]
  A --> C[Harbor live runner]
  A --> D[Release SHA256SUMS]
  B --> E[Re-score C08]
  C --> E
  D --> F[Re-score C06]
  E --> G[SCORECARD + audits mirror]
  F --> G
```

## Ready / in-flight (this wave)

| ID | Task | FR / pillar | Effort | Status |
|----|------|-------------|--------|--------|
| W-226 | Live Harbor runner in CI | C08 L76 | M | THIS PR |
| W-227 | Rust↔Python parity harness | C08 L75 | M | THIS PR |
| W-229 | Release SHA256SUMS artifact | C06 L59 | S | THIS PR |
| W-230 | Re-score + SCORECARD | audit | S | THIS PR |

## Completed

| ID | Task | Status |
|----|------|--------|
| W-101…W-110 | Windows/OTLP/DX | #127 |
| W-201…W-217 | Eval + auto-update | #128 |
| W-204…W-222 | a11y/CodeQL/GHCR/deny | #129 |

## Backlog (hard / org)

| ID | Task | Effort |
|----|------|--------|
| W-223 | Native mobile (iOS/Android) | L |
| W-224 | Apple notarization / Authenticode | L |
| W-225 | Offline air-gap install bundle | L |
| W-228 | Org signed-commit enforcement | org |
| W-231 | Real multi-genre golden corpus | M |
| W-232 | cargo-fuzz nightly CI | L |

## Claim protocol

1. `claim W-2xx` on PR/issue.
2. Branch `feat/w2xx-<slug>`.
3. Reference FR ID in PR body.
