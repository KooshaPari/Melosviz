# MelosViz Visual Spec (C10)

Canonical visual language for desktop + web surfaces. **Token SoT:**
`desktop/assets/brand/tokens.css` — single shared file loaded by the desktop
shell (`index.html` / `splash.html`) and imported by web `src/styles/brand.css`
via the private stub package `@melosviz/brand-tokens`
(`packages/brand-tokens`; re-export `@import` → the SoT — do not copy/fork hex there).
Web keeps only aliases/layout helpers.

## Shared UI component package (`@melosviz/ui`)

`packages/ui` (`@melosviz/ui`, private) is the shared **component** package
(WBS-P3.2 / C10 L105), companion to the token-only `@melosviz/brand-tokens`.
It ships a deliberately small, real surface — components that already lived
under `web/src/components/` and are now imported from the shared package
instead of re-implemented per surface:

| Component | Source | Consumed by |
|-----------|--------|-------------|
| `Skeleton`, `SkeletonBlock` | `packages/ui/src/Skeleton.tsx` | `web/src/components/Skeleton.tsx` (re-export), `LoadingOverlay.tsx` |
| `Button` (`accent`/`ghost`) | `packages/ui/src/Button.tsx` | `web/src/components/PlaylistPanel.tsx` |
| `EmptyState` | `packages/ui/src/EmptyState.tsx` | `web/src/components/PlaylistPanel.tsx` (zero-queue state) |

Wiring mirrors `@melosviz/brand-tokens`: `web/package.json` depends on it via
`"@melosviz/ui": "file:../packages/ui"`, and `web/vite.config.ts` sets
`resolve.dedupe: ['react', 'react-dom']` so the linked package never bundles
a second React copy. See `packages/ui/README.md` for full usage/non-goals —
this is not a full app-wide UI rebuild; most feature views
(`WaveformDisplay`, `PresetEditor`, `SpecViewer`, …) remain app-local.

## Brand mark

- Primary mark: `desktop/assets/brand/logo.svg` / `assets/brand/icon.svg`
- App iconset: `desktop/assets/icons/MelosViz.iconset`

## Palette (warm spectrum + shell)

Shell chrome uses violet-neon tokens (`--mv-accent` / web alias `--mv-primary` =
`#7c6af7`). Web aliases map to SoT vars — no `#7c3aed` drift.

| Role | Token / hex |
|------|-------------|
| Canvas deep | `#0d0d10` → `#2d1b3a` |
| Accent | `#7c6af7` |
| Focus / secondary | `#22d3ee` |
| Spectrum (marketing SVGs) | `#ef4444` → `#f59e0b` → `#facc15` → `#22d3ee` → `#a371f7` |
| Label / off-white | `#f0f0f8` / `#f6f8fa` |

## Motion

- EQ bars: ~1.2s ease-in-out scale, staggered
- Horizon wave: ~4s horizontal drift
- Mark glow: ~2.4s breathe

Demo media: `docs/assets/identity/` (`demo.svg`, `demo.mp4`).

## Surfaces

| Surface | Entry | Notes |
|---------|-------|-------|
| Desktop shell | `desktop/views/main/` | Electrobun WKWebView |
| Web R3F | `web/src/` | Vite + React Three Fiber |
| Empty states | `desktop/assets/brand/gfx/` | SVG placeholders |
| A11y fixture | `web/a11y/fixture.html` | axe + Playwright goldens |
| R3F canvas fixture | `web/fixtures/r3f-canvas.html` | Deterministic SceneView golden (G-C10-03) |

## Theme

Dark studio default (`:root` tokens). Light theme: set
`data-theme="light"` on `<html>` / `<body>` — see
`[data-theme="light"]` overrides in `tokens.css`.

## Golden / regression

- Shape goldens: `eval/golden/` (RenderSpec JSON)
- Screenshot baselines:
  - `eval/golden/screenshots/a11y-fixture.baseline.png` (1280×720, ≤0.2%)
  - `eval/golden/screenshots/desktop-splash.baseline.png` (1280×720, ≤2%)
  - `eval/golden/screenshots/r3f-canvas.baseline.png` (960×540, ≤4% WebGL)
- Gate: `.github/workflows/a11y.yml` pixelmatch via `scripts/visual-gate/compare.mjs`
- Identity: `docs/visual/IDENTITY.md` · Provenance: `docs/visual/PROVENANCE.md`
