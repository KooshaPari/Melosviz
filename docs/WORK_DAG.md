# MelosViz Work DAG

Atomic, FR-linked tasks agents can claim independently.

```mermaid
flowchart TD
  A[CI green] --> B[Hermetic Python wheelhouse smoke]
  A --> C[Portability smoke without FFmpeg/Blender]
  B --> D[C06 L54 3/3 -> C06 100%]
  C --> E[C07 L70 3/3 -> C07 100%]
  D --> F[Re-score 97.5% A]
  E --> F
```

## Ready / in-flight (this wave)

| ID | Task | FR / pillar | Effort | Status |
|----|------|-------------|--------|--------|
| W-316 | Hermetic Python wheelhouse offline CI (`check_hermetic_python_smoke.sh` + supply-chain) | C06 L54 · G-C06-03 · WBS-P1.14 | M | THIS PR |
| W-317 | Portability smoke without FFmpeg/Blender (`check_portability_smoke.py`) | C07 L70 · G-C07-03 · WBS-P1.14 | S | THIS PR |
| W-318 | Re-score SCORECARD (p1n → 97.5% A) | audit | S | THIS PR |

## Completed

| ID | Task | Status |
|----|------|--------|
| W-313 | Flaky quarantine machine gate (`check_flaky_quarantine.py` + docs-trace CI) | #153 |
| W-314 | External profiler sidecar (`profile_bridge_sidecar.sh`/`.ps1`) | #153 |
| W-315 | Re-score SCORECARD (p1m → 97.0% A) | #153 |
| W-309 | SDK pack smoke CI (`npm pack` + tarball install + import) | #152 |
| W-310 | Document publishable-shape gate + future publish steps | #152 |
| W-311 | Re-score SCORECARD (p1l → 96.8% A) | #152 |
| W-312 | Desktop-spawned bridge bearer auth by default (`INSECURE_LOOPBACK` opt-out) | #152 |
| W-304 | Global memory-cap enforcement (`security.MemoryCapGuard`; soft 429 / hard 503 problem+json; audited; fails open) | #151 |
| W-305 | Wire memory-cap check into `/analyze` `/build` `/render`; RSS/cap gauges on `/metrics` | #151 |
| W-306 | Forward `HTTPException.headers` (e.g. `Retry-After`) through `http_exception_problem` | #151 |
| W-307 | Electrobun tray/menubar quick-actions (Show/Open Bridge Health/Quit) | #151 |
| W-308 | Re-score SCORECARD (p1k → 96.3% A) | #151 |
| W-301 | `@melosviz/ui` shared component package (`Button`/`EmptyState`/`Skeleton`) | #150 |
| W-302 | Wire `PlaylistPanel` + `Skeleton` re-export to `@melosviz/ui` (real consumer, not stub) | #150 |
| W-303 | Re-score SCORECARD (p1j → 95.8% A) | #150 |
| W-297 | R3F canvas fixture + CI pixelmatch golden | #149 |
| W-298 | C00 L6 continuous-profiler audit resync | #149 |
| W-299 | AGENT_QUICKSTART + C03 100% | #149 |
| W-300 | Re-score SCORECARD (p1i → 95.6% A) | #149 |
| W-294 | In-process continuous profiler (`MELOSVIZ_PROFILE=continuous`/`2`) | #148 |
| W-295 | Mitigate G-C07-01 (Linux desktop-e2e; GUI host-gated note) | #148 |
| W-296 | Re-score SCORECARD (p1h → 94.8% A) | #148 |
| W-291 | SceneView canvas SR (role=img + aria-live) | #147 |
| W-292 | Bridge RateLimiter/RenderQuota race stress | #147 |
| W-293 | Re-score SCORECARD (p1g → 94.5% A) | #147 |
| W-288 | Web playlist empty/zero state | #146 |
| W-289 | `@melosviz/bridge-client` SDK stub | #146 |
| W-290 | Re-score SCORECARD (p1f → 94.3% A) | #146 |
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
