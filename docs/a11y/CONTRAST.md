# Token contrast pairs (WCAG AA sketch)

Dark studio default (`desktop/assets/brand/tokens.css` / desktop shell).
Ratios are approximate against `#0d0d10` / `#f6f8fa` using relative luminance.

| Foreground | Background | Approx ratio | Role |
|------------|------------|-------------:|------|
| `#f0f0f8` (`--mv-text-hi`) | `#0d0d10` (`--mv-bg-base`) | ~15.5:1 | Body / headings |
| `#9090b0` (`--mv-text-mid`) | `#0d0d10` | ~6.2:1 | Secondary (AA large / UI) |
| `#a78bfa` (`--mv-text-accent`) | `#0d0d10` | ~6.8:1 | Accent text |
| `#ffffff` on `#5b4cdb` button | — | ~5.5:1 | Primary CTA (fixture) |
| `#1a0e1f` | `#f6f8fa` (light theme) | ~14:1 | Light body |

Regression: axe-core WCAG2 AA tags on `web/a11y/fixture.html` in
`.github/workflows/a11y.yml`. Update this table when tokens change.
