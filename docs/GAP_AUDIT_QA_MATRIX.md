# Gap Audit + QA Matrix (audit-v38)

Baseline: [`audit/SCORECARD.md`](../audit/SCORECARD.md) — **~94.5% · A** (2026-07-13, p1g-canvas-sr-race).
Sources: `audit/.lane-c00`…`c11`. Linked WBS → [`WBS_PHASED.md`](WBS_PHASED.md).

Status enum: `open` | `mitigated` | `closed` | `accepted` | `blocked`

## Closed / shipped (prior + Time-2 waves)

| GapID | Cluster | Pillar | Gap description | Severity | QA method | Test/evidence path | Status | Linked WBS | Trace FR |
|-------|---------|--------|-----------------|----------|-----------|--------------------|--------|------------|----------|
| G-CL-01 | C00 | L2 | OpenAPI unpublished / no drift gate | H | ci | `docs/api/openapi.json`; `.github/workflows/openapi.yml` | closed | WBS-P0.1 | C00 L2 |
| G-CL-02 | C03 | L30.12 | Journey suite not CI-gated | H | ci | `scripts/check_journeys.py`; `.github/workflows/journeys.yml` | closed | WBS-P0.2 | C03 L30.12 |
| G-CL-03 | C03 | L30.9 | No agent concurrency policy | M | doc | `docs/PARALLEL_AGENTS.md` | closed | WBS-P0.3 | C03 L30.9 |
| G-CL-04 | C10 | L104 | No ThemeProvider / light theme | M | integ | ThemeProvider (wave W-258); `audit/.lane-c10/C10.md` | closed | WBS-P0.4 | C10 L104 |
| G-CL-05 | C10 | L99/L103 | Missing skeletons / splash baseline | M | e2e | `web/src/components/Skeleton.tsx`; splash + PROVENANCE | closed | WBS-P0.5/P0.6 | C10 L99 |
| G-CL-06 | C11 | L121 | No air-gap procedure | H | doc | `docs/AIRGAP.md`; `scripts/airgap_bundle.sh` | closed | WBS-P0.8 | C11 L121 |
| G-CL-07 | C04 | L35 | No cosign / SLSA on releases | H | ci | `.github/workflows/release.yml` cosign + attest | closed | WBS-P0.9 | C04 L35 |
| G-CL-08 | C04 | L34 | No DCO Signed-off-by gate | M | ci | `.github/workflows/dco.yml` | closed | WBS-P0.10 | C04 L34 |
| G-CL-09 | C09 | L81 | No axe a11y CI / FOCUS docs | H | ci | `.github/workflows/a11y.yml`; `docs/a11y/` | closed | WBS-P0.11 | C09 L81 |
| G-CL-10 | C06 | L60 | No dedicated supply-chain policy | M | doc | `docs/SUPPLY_CHAIN.md` | closed | WBS-P0.12 | C06 L60 |

## Remaining gaps (by cluster)

| GapID | Cluster | Pillar | Gap description | Severity | QA method | Test/evidence path | Status | Linked WBS | Trace FR |
|-------|---------|--------|-----------------|----------|-----------|--------------------|--------|------------|----------|
| G-C00-01 | C00 | L2 | Public npm/crates SDK still unpublished | M | manual | `docs/sdk/README.md`; `sdk/ts` (`@melosviz/bridge-client` private publishable-shape stub); `docs/SUPPLY_CHAIN.md` reserved names | mitigated | WBS-P3.1 | C00 L2 |
| G-C00-02 | C00 | L9 | Windows desktop package/upload still step-level continue-on-error (job soft-fail narrowed) | L | ci | `audit/.lane-c00/C00.md` L9; `release.yml`; `docs/PACKAGING.md` | mitigated | WBS-P1.10 | C00 L9 |
| G-C00-03 | C00 | L7 | No loom/race stress suite | L | unit | `backend/tests/test_bridge_concurrency_race.py`; `audit/.lane-c00/C00.md` L7 | closed | — | C00 L7 |
| G-C01-01 | C01 | L11 | Full qgate reusable workflow still optional | M | ci | `audit/.lane-c01/C01.md` L11; `.qgate.toml` | open | WBS-P2.4 | C01 L11 |
| G-C01-02 | C01 | L16 | Desktop/CLI locale coverage incomplete (en-first) | M | e2e | `docs/I18N.md`; `backend/src/melosviz/i18n/`; `desktop/locales/`; `audit/.lane-c01/C01.md` | mitigated | WBS-P3.5 | C01 L16 |
| G-C02-01 | C02 | L25 | No CPU/memory quotas for render workers | H | integ | `backend/src/melosviz/bridge/security.py` (`RenderQuota`); `backend/tests/test_bridge_security.py` | closed | WBS-P1.2 | C02 L25 |
| G-C02-02 | C02 | L26 | No circuit breaker library | H | integ | `backend/src/melosviz/bridge/security.py` (`CircuitBreaker`); `backend/tests/test_bridge_security.py` | closed | WBS-P1.3 | C02 L26 |
| G-C02-03 | C02 | L21 | No OAuth/SAML IdP | L | manual | localhost Bearer sufficient today | accepted | WBS-P2.3 | C02 L21 |
| G-C02-04 | C02 | L20 | Desktop/web threat deep-dive lighter than bridge | M | doc | `docs/security/DESKTOP_WEB_THREAT_MODEL.md`; `docs/security/THREAT_MODEL.md` link | closed | — | C02 L20 |
| G-C02-05 | C02 | L28 | cargo-audit soft-fail | L | ci | `.github/workflows/supply-chain.yml` (`rust-audit` / `cargo audit` hard-fail, no continue-on-error) | closed | — | C02 L28 |
| G-C03-01 | C03 | L30.10 | No feedback-loop timing budget gate (diagnose/pytest/cargo/golden) | M | ci | `docs/TIMING_BUDGETS.md`; `scripts/check_timing_budgets.py`; `.github/workflows/timing-budgets.yml` | closed | WBS-P1.11 | C03 L30.10 |
| G-C03-02 | C03 | L30.1 | FR catalog not machine-exported (JSON/YAML) | M | ci | `docs/fr-status.yaml`; `scripts/check_fr_status.py`; `.github/workflows/docs-trace.yml` | closed | WBS-P1.1 | C03 L30.1 |
| G-C04-01 | C04 | L34 | Org GPG / verified-commit branch protection | H | manual | `CONTRIBUTING.md`; lane soft_goal W-228 | open | WBS-P2.1 | C04 L34 · W-228 |
| G-C04-02 | C04 | L39 | OSSF TokenPermissions findings on older workflows | M | ci | `.github/workflows/ci.yml`; `.github/workflows/supply-chain.yml`; `.github/workflows/release.yml`; `.github/workflows/docs-trace.yml` | mitigated | WBS-P1.8 | C04 L39 |
| G-C04-03 | C04 | L35 | Per-binary cosign still optional (manifest-level) | L | ci | `release.yml` SHA256SUMS.cosign.bundle | mitigated | WBS-P0.9 | C04 L35 |
| G-C05-01 | C05 | L49 | Audit JSONL retention not enforced in code | M | unit | `backend/src/melosviz/bridge/security.py` (`_maybe_prune_audit`); `docs/PRIVACY.md`; `backend/tests/test_bridge_security.py` | closed | WBS-P1.7 | C05 L49 |
| G-C05-02 | C05 | L45 | No always-on continuous profiler agent | M | manual | `/debug/profile` opt-in only | open | WBS-P3.4 | C05 L45 |
| G-C05-03 | C05 | L44 | Desktop Bun client does not inject traceparent | L | integ | `desktop/src/index.ts` bridgeFetch + health; `docs/OBSERVABILITY.md` | closed | — | C05 L44 |
| G-C06-01 | C06 | L55 | No automated reserved-name scanner in CI | H | ci | `scripts/check_reserved_names.py`; `docs/SUPPLY_CHAIN.md`; `.github/workflows/supply-chain.yml` | closed | WBS-P1.4 | C06 L55 |
| G-C06-02 | C06 | L52 | No SOURCE_DATE_EPOCH / bit-identical release check | H | ci | `scripts/check_repro_smoke.sh`; `.github/workflows/supply-chain.yml` (`repro-smoke`); `.github/workflows/release.yml`; `docs/SUPPLY_CHAIN.md` | closed | WBS-P1.5 | C06 L52 |
| G-C06-03 | C06 | L54 | Builds not hermetic (CI still fetches crates/pypi) | H | ci | `scripts/check_hermetic_smoke.sh`; `.github/workflows/supply-chain.yml` (`hermetic-smoke`); `docs/AIRGAP.md` (full in-repo vendor still open) | mitigated | WBS-P1.6 | C06 L54 |
| G-C07-01 | C07 | L64 | Full desktop e2e still macOS-host-only | M | e2e | `desktop/tests/e2e_desktop.test.ts` | open | WBS-P1.9 | C07 L64 |
| G-C07-02 | C07 | L67 | Nightly fuzz window short (not continuous farm) | M | ci | `.github/workflows/cargo-fuzz.yml` (PR 60s / schedule+dispatch 300s per target; continuous farm still open) | mitigated | WBS-P1.9 | C07 L67 |
| G-C07-03 | C07 | L54/L70 | Hermetic/offline + external FFmpeg/Blender deps | M | doc | `docs/AIRGAP.md`; `scripts/check_hermetic_smoke.sh`; lane C07 L70 (FFmpeg/Blender still external) | mitigated | WBS-P1.6 | C07 L70 |
| G-C08-01 | C08 | L71 | Licensed real-track corpus (legal) | L | manual | `docs/EVAL.md`; `audit/.lane-c08/C08.md` | open | WBS-P4.6 | C08 L71 |
| G-C08-02 | C08 | L72 | Full 180s Criterion not on every PR | L | ci | `criterion-smoke.yml` (1s filter) | accepted | — | C08 L72 |
| G-C09-01 | C09 | L83 | Canvas/R3F screen-reader depth limited | M | e2e | `web/src/r3fRenderer.tsx` SceneView role=img + aria-live; `docs/a11y/FOCUS.md`; `audit/.lane-c09/C09.md` L83; `USER_JOURNEYS.md` J3 | closed | — | C09 L83 |
| G-C09-02 | C09 | L82 | SPA focus trap / modal choreography thin | M | e2e | `docs/a11y/FOCUS.md`; KeyboardHelp/PresetEditor focus restore | closed | — | C09 L82 |
| G-C10-01 | C10 | L96 | Token SoT not shared (desktop inline vs web subset) | M | unit | `desktop/assets/brand/tokens.css`; `desktop/views/main/index.html`; `web/src/styles/brand.css`; `web/vite.config.ts`; `docs/VISUAL_SPEC.md` | closed | WBS-P1.12 | C10 L96 |
| G-C10-02 | C10 | L105 | No shared design-system package | M | doc | `packages/brand-tokens` stub; SoT `desktop/assets/brand/tokens.css`; full UI lib still open | mitigated | WBS-P3.2 | C10 L105 |
| G-C10-03 | C10 | L107 | R3F canvas screenshot still optional | M | e2e | `audit/.lane-c10/C10.md` L107 | open | WBS-P3.3 | C10 L107 |
| G-C11-01 | C11 | L112 | No Apple notarization / Authenticode | H | manual | `docs/SIGNING.md` (org certs) | blocked | WBS-P2.2 · W-224 | C11 L112 |
| G-C11-02 | C11 | L117 | No native iOS/Android package | H | manual | `audit/.lane-c11/C11.md` L117 | open | WBS-P4.1 · W-223 | C11 L117 |
| G-C11-03 | C11 | L110 | No tray/menubar quick-actions | L | manual | `audit/.lane-c11/C11.md` L110 | open | WBS-P4.2 | C11 L110 |
| G-C11-04 | C11 | L121 | Full vendored Electrobun offline installer | M | manual | `docs/AIRGAP.md` | open | WBS-P4.3 | C11 L121 |
| G-C11-05 | C11 | L120 | No MSI uninstaller until Authenticode | M | doc | `docs/UNINSTALL.md` | open | WBS-P4.4 | C11 L120 |
| G-C11-06 | C11 | L109 | No PyPI / crates.io publish | M | manual | `docs/PACKAGING.md` | open | WBS-P3.1 | C11 L109 |

## Notes

- **Severity:** H = blocks A+/92% path or security/supply-chain; M = cluster B→A lift; L = polish / accepted local-studio tradeoff.
- **Honest CI:** closed rows cite committed workflows/docs only — no fabricated “green run” URLs.
- C09 scores 100% A at cluster level; remaining rows are residual UX depth, not scorecard blockers.
- G-C08-01 uses Status `open` with WBS deferred (legal/product gate); not marked `accepted` until counsel signs off.

`last_updated`: 2026-07-13
