# Visual asset provenance

Hand-authored brand surfaces (AI-coded SVG/CSS, not generative image dumps).

| Asset | Path | Role | Source |
|-------|------|------|--------|
| Primary mark | `assets/brand/icon.svg` | README hero / app mark | Hand-authored SVG |
| Animated mark | `assets/brand/icon-animated.svg` | SMIL warm-spectrum loop | Hand-authored SVG |
| Favicon | `assets/brand/favicon.svg` | Browser tab | Derived from mark |
| Desktop logo | `desktop/assets/brand/logo.svg` | Shell chrome | Hand-authored SVG |
| Empty-state art | `desktop/assets/brand/gfx/empty-state.svg` | Zero-data illustration | Hand-authored SVG |
| Iconset | `desktop/assets/icons/MelosViz.iconset/` | macOS / Electrobun | Rasterized from logo |
| Identity demo | `docs/assets/identity/demo.svg` (+ `.mp4`) | Motion showcase | Hand-authored |
| Tokens | `desktop/assets/brand/tokens.css` | Color / type / motion SoT (desktop + web) | Hand-authored CSS |
| A11y fixture | `web/a11y/fixture.html` | axe + screenshot golden | Hand-authored HTML |
| Screenshot baseline | `eval/golden/screenshots/a11y-fixture.baseline.png` | Visual regression gate | CI Chromium capture |

Regenerate the screenshot baseline (Ubuntu CI parity):

```bash
npm ci --prefix scripts/visual-gate
UPDATE_SCREENSHOT_BASELINE=1 node scripts/visual-gate/compare.mjs \
  eval/golden/screenshots/a11y-fixture.baseline.png \
  eval/golden/screenshots/a11y-fixture.png
```
