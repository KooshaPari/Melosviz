# Committed screenshot baselines (C10 L107)

| File | Source | Gate |
|------|--------|------|
| `a11y-fixture.baseline.png` | Ubuntu Chromium 1280×720 of `web/a11y/fixture.html` | `.github/workflows/a11y.yml` pixelmatch ≤0.2% |
| `desktop-splash.baseline.png` | Ubuntu Chromium 1280×720 of `desktop/views/main/splash.html` | same workflow ≤2% |
| `r3f-canvas.baseline.png` | Ubuntu Chromium 960×540 of `web/fixtures/r3f-canvas.html` | same workflow ≤4% (WebGL) |

Fresh captures land as `*.png` (gitignored / CI-only). Diffs as `*.diff.png`.

Update baseline after intentional fixture changes:

```bash
npm ci --prefix scripts/visual-gate
UPDATE_SCREENSHOT_BASELINE=1 node scripts/visual-gate/compare.mjs \
  eval/golden/screenshots/a11y-fixture.baseline.png \
  eval/golden/screenshots/a11y-fixture.png
UPDATE_SCREENSHOT_BASELINE=1 node scripts/visual-gate/compare.mjs \
  eval/golden/screenshots/r3f-canvas.baseline.png \
  eval/golden/screenshots/r3f-canvas.png
```
