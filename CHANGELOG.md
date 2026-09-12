# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- ComfyUI-centric studio pivot: orchestrator over ComfyUI/C4D/UE/AE/DaVinci with multi-shot Director, auto-critic, interpolation bridge, render cache, provenance, LUFS mastering, AI stems, and web/desktop Director's Console.
- Real Demucs / Spleeter / audio-separator Python-import wrappers for audio (`feat(audio)`).
- Click-to-edit modal and GPU smoke CI workflow for the web surface (`feat(web)`, #215).
- Partial-scene re-render policy gated by `MELOSVIZ_DIRECT_NEIGHBORS`, plus a GPU smoke test (`feat(cli)`).
- 88-pillar AgilePlus scorecard workflow for regression prevention (`ci(quality)`).
- User-oriented scorecard covering utility, usability, and expandability (32 pillars).
- `gitleaks.toml` baseline configuration for secret-scanning gate.
- Quality pillar files: fuzz, mutation, and benchmark scaffolds; missing quality gates.
- `Infisical` integration workflow for secrets management.
- README AI slop-inside and downloads badges (#229).

### Changed

- Updated GitHub Actions to current majors: `actions/checkout` 4→7, `actions/setup-node` 4→7, `actions/setup-python` 5→7, `actions/setup-go` 5→7, `astral-sh/setup-uv` 3→7, `actions/upload-artifact` 4→7, `docker/login-action` 3→4, `docker/build-push-action` 6→7, `docker/setup-buildx-action` 3→4, `docker/metadata-action` 5→6, `ossf/scorecard-action` 2.4.0→2.4.4, `sigstore/cosign-installer` 3.8.2→4.1.2, `EmbarkStudios/cargo-deny-action` 1→2, `softprops/action-gh-release` 2.2.1→3.0.2, `gitleaks/gitleaks-action` 2→3, `dtolnay/rust-toolchain` and `oven-sh/setup-bun` bumps.
- Web dependencies: `vite` 8.1.4→8.2.2, `@playwright/test` 1.61.1→1.62.1, `autoprefixer` 10.5.2→10.5.4, `react-dom`/`@types/react-dom`, `@typescript-eslint/parser`, `jsdom` 30.0.0→30.0.1, `three` 0.175.0→0.185.1, `@radix-ui/react-slider` 1.4.3→1.4.7, `postcss`, `wavesurfer.js` 7.12.10→7.12.11, `web-vitals` 5.3.0→6.1.0.
- Rust dependencies: `clap` 4.6.3→4.6.6, `serde_json` 1.0.150→1.0.151, `serde` 1.0.228→1.0.229, `bytemuck` 1.25.0→1.25.2, `anyhow` 1.0.103→1.0.104.
- Desktop shell: `electrobun` 1.18.1→2.0.1 (#218).
- CI workflows migrated to stable lint/test gate names (`ci.yml`, `trunk-check.yml`, `scorecard.yml`); `.pre-commit-config.yaml`, `renovate.json`, `trunk.yaml`, `.trunk/trunk.yaml`, `.circleci/config.yml`, `.github/stale.yml`, and `.mergify.yml` refreshed.
- Brought in CircleCI parallel pipeline, Trunk.io lint/format config, and Mergify auto-merge rules.

### Removed

- Legacy cargo crates: `melosviz-render-wgpu` and `melosviz-mir`.

### Fixed

- Orchestrator: wired `_render_cache` and `_provenance_records` in `__init__`, and renamed `cache_root` → `cache_dir` (#214).
- CI: replaced broken trunk-action with a deterministic prettier-scoped check (#188).
- Release: corrected `softprops/action-gh-release` v2.2.1 SHA pin and `cargo-cyclonedx` v0.5.9 `--format` / `--override-filename` invocation.
- Web: restored clean `App.tsx` and `useAnalysis.ts` and fixed `typescript-eslint` version mismatch.

## [0.2.0] - 2026-07-04

### Added

- **Quality-gate wave P1A–P1Q (full v38 scorecard B-grade):**
  - GitHub Packages SDK publish workflow + consumption docs (97.8% A, #155).
  - Hermetic Python wheelhouse CI + portability smoke (97.5% A, #154).
  - Flaky-quarantine gate + profiler sidecar (97.0% A, #153).
  - SDK pack smoke + desktop bridge auth (96.8% A, #152).
  - Global memory-cap enforcement + tray quick-actions (#151).
  - `@melosviz/ui` shared design-system package (#150).
  - R3F canvas golden + scorecard (95.6% A, #149).
  - Continuous in-process profiler + desktop e2e gap mitigation (#148).
  - SceneView canvas SR chrome + bridge concurrency race suite (#147).
  - Web playlist empty state + bridge-client SDK stub (#146).
  - A11y fixture screenshot baseline refresh (#145).
  - Bun `traceparent`, SPA focus polish, CLI/desktop i18n scaffold (#144).
  - Restore Hypothesis loop indices broken by B007 rename (#143).
  - Restore used loop indices in Hypothesis strategies; ruff B007 unused loop var in fuzz test (#142).
  - Desktop/web threat model, Hypothesis L66, brand-tokens stub, Windows release hardening (#141).
  - LF hermetic script shebang and force nightly for `cargo-fuzz` (#140).
  - Hermetic offline smoke, longer nightly fuzz, `cargo-audit` hard-fail (#139).
  - `SOURCE_DATE_EPOCH` reproducibility, timing budgets, shared brand tokens (#138).
  - Machine-trace WBS / gap gates, bridge quotas / breaker, reserved-name supply (#137).
- **Web studio (W-325, W-329, W-333–352):** SDK + bridge DX, onboarding, accessibility, keyboard shortcuts (`?` help modal), playlist/queue with multi-file analysis, BeatPulse R3F component with beat-crossing pulse animation, PresetEditor modal with Radix Slider + Dialog, WaveSurfer waveform display synced to `playbackT`, brand identity with animated splash + loading overlay, mobile responsive layout with `useIsMobile` hook, Vercel deploy config + `.env.example` + deploy guide, README refresh with features and Vercel guide.
- **Web analysis surface:** expose `bpm`, `key`, and `beat_times` in the `/analyze` response; i18n expansion (`en`/`es`) with keyboard/preset chrome; non-visual R3F canvas scene summary for screen readers.
- **Desktop:** stable wgpu render path with binary resolver and multi-backend support (DX12 / Vulkan / Metal enabled, not metal-only); air-gap Electrobun desktop prebuilt fetch path (W-326, #160); binary resolver on Windows using `render-mp4` CLI.
- **CLI:** `serve`, `presets`, and `version` subcommands with unit tests; `export-png` and `demo-frames` subcommands with PNG encoding (#82); resolve `melosviz-render` binary on Windows (#80).
- **Analysis:** wire onsets + chord/scale into `full_analysis` + render spec (rebased on v8 stack); crash-isolate `librosa.beat_track` (numba cp314 segfault) with a numpy fallback — fixes build exit 139 (#85).
- **Backend:** multi-tool render adapters wired into the conductor — After Effects + Media Encoder + Firefly, TouchDesigner live runtime generator + OSC/WS bridge, headless Blender adapter with RenderSpec v2 → procedural geo/shader scene → MP4 (with flash-safety).
- **Scene engine:** hybrid representation-domain MVP with disco-ball scanner mask and beat-locked domain switching; P8 advanced — radiance-field / 3DGS domain, semantic scanner, procedural camera; RenderSpec v2 shared brain with stems + MIR semantics + dense keyframes + semantic segments.
- **Compose:** anti-repetition narrative composer + e2e music-video assembly + live polish.
- **wgpu realtime renderer:** Rust + wgpu preview renderer with incremental segment cache; `ConductorScene` with perf monitoring; B17 wire RenderSpec v2 into the uniform pipeline; headless export with Python bridge.
- **Bridge:** FastAPI bridge endpoint tests (`test_bridge_api.py`, #98); 5-layer hardening (loopback / auth / rate-limit / audit / path-cap) with 11 RED→GREEN tests (#59); always-settle path validation for null / overlong paths + chaos test hardening (#81); bridge quota/breaker changes with ruff format and `combine with` contexts.
- **Tests:** 14 unit tests for registry and orchestrator (#97); 7 new tests + `ValueError` guard for zero-duration in video exporter (#94); MIR analyzer error path unit tests (#64); 23 new HTTP bridge integration tests (#68); 28 new TouchDesigner generator + scheduler unit tests (#67); 31 new preset load/save round-trip + error handling tests (#69); 10 new renderer frame output + texture correctness tests (#70); 14 Rust MIR edge cases (#71); 31 unit + property tests added; new fastapi-bridge endpoint tests; expand desktop bridge-layer e2e for Linux CI (#161).
- **Performance:** splash render timing + MIR analyzer benchmark (B10, #63, #72); `criterion` frame-setup time benchmark (#65, #66); `wgpu` frame-setup benchmark.
- **Coverage:** install ML deps + cover optional paths (no pragma gaming, #58); tighten coverage gates (95% backend, audio.py 93%); real behavioral coverage for ML optional deps; remove optional-dep `# pragma: no cover`; 100% granular-recursive with gate threshold 100 (#56).
- **CI / supply-chain:**
  - Lift Windows release, OTLP defaults, DX/governance docs.
  - `pip-licenses` gate for backend Python dependencies.
  - Reusable in-repo quality-gate workflow promoted (#158).
  - Pin `actions/attest-build-provenance` 2.4.0→4.1.1; SHA-pin GitHub Actions; trust `softprops/action-gh-release` floating tag.
  - Replace broken `trunk-action` with deterministic prettier-scoped check; install ffmpeg for timing diagnose; serve splash from `desktop/` root.
  - `actions/download-artifact` 4.2.1→8.0.1; `wgpu` 24.0.5→30.0.0; `criterion` 0.5.1→0.8.2; `clap` 4.6.1→4.6.3; `anyhow`, `serde`, `bytemuck`, `pollster` bumps.
  - Multi-genre corpus, `cosign`, `cargo-fuzz` workspace isolation, Criterion smoke.
- **Quality pillars:** committed screenshot baselines + supply-chain policy; air-gap bundle, DCO, focus / contrast, palette align; i18n scaffold, `problem+json`, privacy / governance DX; OpenAPI export, journey CI, `ThemeProvider`, splash baseline; mutmut + `cargo-mutants` + 546 LOC of mutation tests (#60).
- **Branding / UX:** MelosViz app icon + splash screen + Radix UI dark theme (B9, #62); animated SVG variant (L101, L105); centered brand icon + tagline (L104, #110); visual identity demo assets.
- **Electrobun desktop (MelosViz.app):** CLI packaging; bundle uv venv with analysis + bridge deps so RPC `analyze` works; load view via secure `views://` scheme so RPC crypto initializes; instantiate Electroview so RPC transport send is wired; copy `views/main/index.html` into the build so `views://` can serve it; open BrowserWindow non-blocking so UI shows (backend connects async); use `Electroview.defineRPC` in webview (1.18.1 fix); add `tsconfig` (DOM lib + bun types).
- **Live polish (wave/p1p + p1q):** gitignore adoption, `web-vitals`, `eslint-plugin-react-refresh`, `typescript-eslint/parser`, `typescript` 5.9.3→7.0.2, `vite` 6.4.3→8.1.4, Trunk DAG widening, air-gap desktop lane, desktop e2e lane.
- **Recovery work (2026-07-17):** preserve meaningful local work — multi-scene compositions with template crossfades; web studio upload→analyze hardening for large WAVs.
- **Spec / docs:** top-level SPEC, `cliff` config, Makefile, BDD tests, intent docs (#92); FR/NFR + acceptance-criteria oracle + pending test skeletons; OpenAPI LF normalization + CR-tolerant drift check; render engine decision (wgpu primary, Bevy optional, UE out); EEVEE-Next interim fallback + honest measured/estimated labels; traceability + completeness audit (P0–P8); EEVEE-Next headless eval + wgpu recommendation; render performance benchmark; renderer toolchain status documented in `LOCAL_RUN.md`; local install + run validation across completion stages; updated install and usage guidance.
- **Audit:** MelosViz C03–C11 scorecards — full v38 sweep across 9 clusters (#109); C03 scorecard — Agent Readiness (22/36, C) (#108); wave P1P/P1Q merge triage status for PRs #156–#163.

### Changed

- Brought forward stable lint/test gate names; refreshed `pre-commit-config.yaml`, `renovate.json`, `trunk.yaml`, `.trunk/trunk.yaml`, `.circleci/config.yml`, `.github/stale.yml`, `.mergify.yml`.
- Stop tracking Rust `target/` build artifacts.
- Raise render quota ceiling in bridge load-smoke fixture.
- Adopted shared Python `.gitignore` template from `phenotype-tooling`.

### Fixed

- Security: patch 5 open Dependabot alerts (`vitest`, `vite`, `esbuild`, #89).
- Resolve all 318 ruff lint errors in backend (#88).
- Re-enable / isolate quality-gate job; correct `phenotype-pm-core` trace-gate ref (main → master, #84); debug bisection for parse failure; bare quality-gate call without `with` block.
- Audio: dep-light amplitude envelope; `audioop` frame alignment; viz build rich-spec wiring.
- Disable 1000ms RPC timeout that broke `pickFile`; add `k.wav` backend matrix (#80).
- Always-settle path validation; ruff `SIM102` / `SIM117` / `F401` silenced on bridge quota paths.
- Keep desktop e2e on bridge-only install (no `librosa`).
- Unblock latent pytest failures exposed by ruff-green CI.
- Harden `pickFile` / `pickDirectory` RPC with `try/catch` + `showError` (#83).

## [0.1.0] - 2026-06-14

### Added

- Initial scaffold of Melosviz — music-to-visual generation toolkit.
- Hexagonal docs, governance baseline, and Phase 0–4 modernization.
- Release workflow with tag triggers, build, test, and artifact release.
- SHA-pin CI actions; restore web/desktop + grading framework.
- AI-DD metadata badge block.
- Backend foundations:
  - Render spec builder (WP-3).
  - WebGL exporter (WP-5).
  - Video exporter (WP-6) with PNG frame pipeline + 34 mocked tests.
  - MIDI input parser via `mido` (WP-9).
  - Preset library tests (WP-8 + WP-17).
  - Hypothesis-driven property tests (WP-21).
- Melosviz render engine (partial, #21).
- Polygon-glass SVG icon + favicon (brand).
- `gitleaks` baseline.
- Pinned Scorecard action SHAs refresh.
- CONTRIBUTING.md.
- Submodule sync.
- Desktop fix: dialog / notify / deeplink / updater modules; fix `tauri-plugin-dialog` API.
- README with work-state header; polished top matter; `melosviz` governance baseline rebased.
- Dependency upgrades: `vite` 5.4.21→8.0.16 in `/web`; `actions/setup-node` 4.4.0→6.4.0; merge conflicts resolved keeping updated action SHAs; `softprops/action-gh-release` 2.6.2→3.0.0; `actions/checkout` 4.3.1→6.0.3.

### Fixed

- CI: bump action SHAs, resolve merge conflicts, keep updated SHAs (#3).
- Backend pytest import path.
- Restore `melosviz` package so `test_video_exporter` can collect and pass.

[Unreleased]: https://github.com/KooshaPari/Melosviz/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/KooshaPari/Melosviz/releases/tag/v0.2.0
[0.1.0]: https://github.com/KooshaPari/Melosviz/releases/tag/v0.1.0
