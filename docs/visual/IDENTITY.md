# MelosViz visual identity

Canonical identity for desktop + web. **Token SoT:**
`desktop/assets/brand/tokens.css` (shared; web imports it via `brand.css`).
Contract: `docs/VISUAL_SPEC.md`. Provenance: `docs/visual/PROVENANCE.md`.

## Signature

Three-waveform mark with a playhead — festival visualizer motif. Appears on
README, splash/loader EQ language, and empty-state spectrum art.

## Palette

Dark studio default (void `#0d0d10`, violet accent `#7c6af7`, cyan focus
`#22d3ee`). Light theme via `data-theme="light"`. Warm-spectrum brand SVGs
(`#ef4444` → `#a371f7`) remain the marketing/mark language; shell chrome uses
the violet-neon token set.

## Motion

Tokenized durations (`--mv-dur-fast/base/slow`) and easing (`--mv-ease`).
Honor `prefers-reduced-motion: reduce` — animations collapse to near-zero
duration on desktop shell, web splash/loader, and brand tokens.
