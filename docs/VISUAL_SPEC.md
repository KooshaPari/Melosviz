# MelosViz Visual Spec (C10)

Canonical visual language for desktop + web surfaces. Tokens live in
`desktop/assets/brand/tokens.css`; this doc is the agent-facing contract.

## Brand mark

- Primary mark: `desktop/assets/brand/logo.svg` / `assets/brand/icon.svg`
- App iconset: `desktop/assets/icons/MelosViz.iconset`

## Palette (warm spectrum)

| Role | Token / hex |
|------|-------------|
| Canvas deep | `#1a0e1f` → `#2d1b3a` |
| Spectrum | `#ef4444` → `#f59e0b` → `#facc15` → `#22d3ee` → `#a371f7` |
| Conductor highlight | `#facc15` |
| Label / off-white | `#f6f8fa` |

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

## Golden / regression

- Shape goldens: `eval/golden/` (RenderSpec JSON, not pixels)
- Screenshot goldens: backlog (WORK_DAG W-205) — prefer Playwright against
  `web/` once a11y CI lands

## Theme

Dark studio default. Light theme tokens are backlog (W-206).
