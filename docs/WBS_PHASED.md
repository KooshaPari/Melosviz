# MelosViz Phased WBS (project + org)

Target: **audit-v38 A+ / 92%+** overall, plus org governance closure.
Baseline: [`audit/SCORECARD.md`](../audit/SCORECARD.md) — **~93.5% · A** (2026-07-13, p1c-hermetic-fuzz).

Status enum (closed): `planned` | `in_progress` | `done` | `blocked` | `deferred`

| ID | Phase | Scope | Work item | Linked W-xxx / FR / C0x Lyy | Status | Evidence path | Owner |
|----|-------|-------|-----------|----------------------------|--------|---------------|-------|
| WBS-P0.1 | P0 | project | OpenAPI export + drift CI | W-255 · C00 L2 | done | `docs/api/openapi.json`; `scripts/export_openapi.py`; `.github/workflows/openapi.yml` | machine |
| WBS-P0.2 | P0 | project | Journey friction gate CI | W-256 · C03 L30.12 | done | `docs/USER_JOURNEYS.md`; `scripts/check_journeys.py` | machine |
| WBS-P0.3 | P0 | project | PARALLEL_AGENTS concurrency policy | W-257 · C03 L30.9 | done | `docs/PARALLEL_AGENTS.md` | human |
| WBS-P0.4 | P0 | project | ThemeProvider + light theme | W-258 · C10 L104 | done | `audit/.lane-c10/C10.md` (L104); web ThemeProvider | machine |
| WBS-P0.5 | P0 | project | Splash + desktop screenshot baseline | W-259 · C10 L103/L107 | done | `docs/visual/PROVENANCE.md`; splash wiring | machine |
| WBS-P0.6 | P0 | project | Skeleton loading blocks | W-260 · C10 L99 | done | `web/src/components/Skeleton.tsx` | machine |
| WBS-P0.7 | P0 | project | Re-score SCORECARD after Time-2 wave | W-261 · audit | done | `audit/SCORECARD.md` (90% A) | human |
| WBS-P0.8 | P0 | project | Air-gap operator bundle + docs | C11 L121 | done | `docs/AIRGAP.md`; `scripts/airgap_bundle.sh` | machine |
| WBS-P0.9 | P0 | project | Cosign keyless + SLSA attestations on release checksums | C04 L35 · C06 L53 | done | `.github/workflows/release.yml`; `docs/SIGNING.md` | machine |
| WBS-P0.10 | P0 | project | DCO gate + CONTRIBUTING Signed-off-by | C04 L34 | done | `.github/workflows/dco.yml`; `CONTRIBUTING.md` | machine |
| WBS-P0.11 | P0 | project | a11y axe CI + FOCUS/CONTRAST contracts | C09 L81–L83 | done | `.github/workflows/a11y.yml`; `docs/a11y/` | machine |
| WBS-P0.12 | P0 | project | SUPPLY_CHAIN + DISTRIBUTION_POLICY + GOVERNANCE docs | C06 L60 · C11 L122 · C02 L29 | done | `docs/SUPPLY_CHAIN.md`; `docs/DISTRIBUTION_POLICY.md`; `docs/GOVERNANCE.md` | human |
| WBS-P0.13 | P0 | project | Prior closeouts W-101…W-254 | W-101…W-254 | done | `docs/WORK_DAG.md` (#127–#134) | machine |
| WBS-P1.1 | P1 | project | Machine-trace gates (FR JSON/YAML export + WBS Status lint) | C03 L30.1 · MV-FR catalog | done | `docs/fr-status.yaml`; `scripts/check_fr_status.py`; `scripts/check_wbs.py`; `scripts/check_gap_matrix.py`; `.github/workflows/docs-trace.yml` | machine |
| WBS-P1.2 | P1 | project | Render-worker CPU/memory quotas | C02 L25 | done | `backend/src/melosviz/bridge/security.py`; `backend/tests/test_bridge_security.py` | machine |
| WBS-P1.3 | P1 | project | Circuit breaker for bridge/render failures | C02 L26 | done | `backend/src/melosviz/bridge/security.py`; `backend/tests/test_bridge_security.py` | machine |
| WBS-P1.4 | P1 | project | Reserved-name CI scanner (dep-confusion) | C06 L55 | done | `scripts/check_reserved_names.py`; `docs/SUPPLY_CHAIN.md`; `.github/workflows/supply-chain.yml` | machine |
| WBS-P1.5 | P1 | project | SOURCE_DATE_EPOCH / bit-repro check on release artifacts | C06 L52 | done | `scripts/check_repro_smoke.sh`; `.github/workflows/supply-chain.yml` (`repro-smoke`); `.github/workflows/release.yml`; `docs/SUPPLY_CHAIN.md`; `docs/PACKAGING.md` | machine |
| WBS-P1.6 | P1 | project | Hermetic / offline build path (CI offline smoke after fetch) | C06 L54 · C07 | done | `scripts/check_hermetic_smoke.sh`; `.github/workflows/supply-chain.yml` (`hermetic-smoke`); `docs/AIRGAP.md`; `docs/SUPPLY_CHAIN.md` | machine |
| WBS-P1.7 | P1 | project | Audit JSONL retention enforcement (rotate/prune vs PRIVACY) | C05 L49 · C02 L23 | done | `backend/src/melosviz/bridge/security.py`; `docs/PRIVACY.md`; `backend/tests/test_bridge_security.py` | machine |
| WBS-P1.8 | P1 | project | OSSF TokenPermissions sweep on remaining workflows | C04 L39 | done | `.github/workflows/ci.yml`; `.github/workflows/supply-chain.yml`; `.github/workflows/release.yml`; `.github/workflows/docs-trace.yml` | machine |
| WBS-P1.9 | P1 | project | Host-gated desktop e2e expansion + longer fuzz farm | C07 L64 · C07 L67 | in_progress | fuzz longer done (G-C07-02 mitigated); Linux bridge-layer desktop-e2e in CI (G-C07-01 mitigated); full GUI Electrobun still host-gated | machine |
| WBS-P1.10 | P1 | project | Harden Windows desktop release (drop continue-on-error) | C00 L9 · C07 L68 | done | `release.yml` windows-desktop (job soft-fail removed; package/upload step soft-fail); `docs/PACKAGING.md`; `audit/.lane-c00/C00.md` L9 | machine |
| WBS-P1.11 | P1 | project | Feedback-loop timing budgets (sccache/nextest/hyperfine gate) | C03 L30.10 | done | `docs/TIMING_BUDGETS.md`; `scripts/check_timing_budgets.py`; `.github/workflows/timing-budgets.yml`; `Makefile` (`timing-budgets`) | machine |
| WBS-P1.12 | P1 | project | Shared brand token SoT across web/desktop (token share only) | C10 L96 | done | `desktop/assets/brand/tokens.css`; `desktop/views/main/index.html`; `desktop/views/main/splash.html`; `web/src/styles/brand.css`; `web/vite.config.ts`; `docs/VISUAL_SPEC.md` | machine |
| WBS-P2.1 | P2 | org | Org GPG / signed-commit branch protection | W-228 · C04 L34 | planned | `CONTRIBUTING.md`; `audit/.lane-c04/C04.md` L34 | human |
| WBS-P2.2 | P2 | org | Apple notarization + Authenticode signing | W-224 · C11 L112 · C04 | blocked | `docs/SIGNING.md`; `docs/PACKAGING.md` (needs org certs) | human |
| WBS-P2.3 | P2 | org | IdP (OAuth/SAML) if hosted bridge ever required | C02 L21 | deferred | `audit/.lane-c02/C02.md` L21 (localhost Bearer OK today) | human |
| WBS-P2.4 | P2 | org | qgate reusable workflow promotion | C01 L11 | planned | `audit/.lane-c01/C01.md` L11; `.qgate.toml` | human |
| WBS-P2.5 | P2 | org | Phenotype registry + audit-v38 re-score after P1 | audit spine | planned | `audit/SCORECARD.md`; phenotype-org-audits | human |
| WBS-P3.1 | P3 | project | Publish npm/crates SDK packages (beyond stubs) | C00 L2 · C11 L116 | planned | `docs/sdk/README.md`; `sdk/ts` | machine |
| WBS-P3.2 | P3 | project | Design-system package (shared UI package; token SoT closed under WBS-P1.12) | C10 L105 | planned | token stub `@melosviz/brand-tokens` (`packages/brand-tokens`); full UI lib still open — `audit/.lane-c10/C10.md` L105; `docs/VISUAL_SPEC.md` | machine |
| WBS-P3.3 | P3 | project | R3F canvas screenshot baseline in CI | C10 L107 | planned | `audit/.lane-c10/C10.md` L107 | machine |
| WBS-P3.4 | P3 | project | Always-on continuous profiler agent (opt-in prod path) | C05 L45 | in_progress | in-process continuous sample ships (`MELOSVIZ_PROFILE=continuous`/`2`); external py-spy sidecar agent still open — `docs/OBSERVABILITY.md`; `/debug/profile` | machine |
| WBS-P3.5 | P3 | project | Full locale coverage (desktop/CLI beyond en/es web) | C01 L16 | in_progress | scaffold: `backend/src/melosviz/i18n/`; `desktop/locales/`; `docs/I18N.md` — full string coverage still open | machine |
| WBS-P3.6 | P3 | project | Lift C02/C04/C06/C07/C10/C11 to ≥92% each | SCORECARD clusters | planned | `audit/SCORECARD.md` | human |
| WBS-P4.1 | P4 | project | Native mobile (iOS/Android) | W-223 · C11 L117 | deferred | `audit/.lane-c11/C11.md` L117; `docs/DISTRIBUTION_POLICY.md` | human |
| WBS-P4.2 | P4 | project | Tray/menubar quick-actions | C11 L110 | deferred | `audit/.lane-c11/C11.md` L110 | machine |
| WBS-P4.3 | P4 | project | Full vendored Electrobun offline installer | C11 L121 | deferred | `docs/AIRGAP.md` | machine |
| WBS-P4.4 | P4 | project | MSI uninstaller (after Authenticode) | C11 L120 · W-224 | deferred | `docs/UNINSTALL.md` | human |
| WBS-P4.5 | P4 | org | Cloud KMS/HSM for bridge tokens | C02 L22 · C01 L18 | deferred | `docs/KEY_ROTATION.md` | human |
| WBS-P4.6 | P4 | org | Licensed real-track eval corpus | C08 | deferred | `docs/EVAL.md`; `audit/.lane-c08/C08.md` (legal) | human |

## Phase intent

| Phase | Intent |
|-------|--------|
| **P0** | Shipped waves already reflected in SCORECARD ~90% A (OpenAPI, journeys, theme, airgap, cosign, a11y, governance docs). |
| **P1** | Engineering wave: machine-trace, C02 quotas/breaker, C06 reserved-name+SDE/repro, C03 timing budgets, C10 token SoT, C07 hermetics, C05 audit retention, C04 token perms. |
| **P2** | Org governance + certificate-backed distribution + re-audit to lock A+/92%+. |
| **P3** | Cluster polish to clear remaining B grades (SDK, design-system package, profiler, i18n). |
| **P4** | Explicitly deferred L-effort / out-of-scope product bets (mobile, tray, full airgap desktop, KMS, licensed corpus). |

---

`last_updated`: 2026-07-13

Machine note: `scripts/check_wbs.py` validates that every row’s **Status** is one of `planned|in_progress|done|blocked|deferred`.
