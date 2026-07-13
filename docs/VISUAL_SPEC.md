# MelosViz Visual Spec (C10)

Canonical visual language for desktop + web surfaces. **Token SoT:**
`desktop/assets/brand/tokens.css` — single shared file loaded by the desktop
shell (`index.html` / `splash.html`) and imported by web `src/styles/brand.css`
via the private stub package `@melosviz/brand-tokens`
(`packages/brand-tokens`; re-export `@import` → the SoT — do not copy/fork hex there).
Web keeps only aliases/layout helpers. Full shared UI component library remains
WBS-P3.2 / C10 L105.

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
