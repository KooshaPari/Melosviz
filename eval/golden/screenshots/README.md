# Committed screenshot baselines (C10 L107)

| File | Source | Gate |
|------|--------|------|
| `a11y-fixture.baseline.png` | Ubuntu Chromium 1280×720 of `web/a11y/fixture.html` | `.github/workflows/a11y.yml` pixelmatch ≤0.2% |

Fresh captures land as `a11y-fixture.png` (gitignored / CI-only). Diffs as
`a11y-fixture.diff.png`.

Update baseline after intentional fixture changes:

```bash
npm ci --prefix scripts/visual-gate
UPDATE_SCREENSHOT_BASELINE=1 node scripts/visual-gate/compare.mjs \
  eval/golden/screenshots/a11y-fixture.baseline.png \
  eval/golden/screenshots/a11y-fixture.png
```
