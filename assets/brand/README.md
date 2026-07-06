# MelosViz Brand

**AI-CODED, not AI-generated.** Vision-pillar L96 ships the static icon set; L101 ships the
animated motion variant.

## The mark

Three stacked waveforms (primary / secondary / tertiary) over a charcoal panel with a glowing
playhead dot — reads "melody + music visualization" at a glance.

## Files

| File | Purpose |
|------|---------|
| `icon.svg` | Source of truth — static, hand-coded vector |
| `icon-animated.svg` | L101 motion variant — SMIL warm-spectrum color shift (no JavaScript) |
| `favicon.svg` | Tab favicon (smaller variant) |

## Regenerating

Static raster exports derive from the SVG via the repo's brand-export script.

## Motion variant (L101)

`icon-animated.svg` ships a 5-second loop:

- The waveform gradient cycles through a warm spectrum: pink `#ec4899` → amber `#f59e0b` → teal
  `#7ebab5` → pink.
- All three waveform layers + the playhead dot shift color in unison.
- The radial glow backdrop follows the same hue cycle.
- Loop is seamless: last frame == first frame.

All animation is SVG-native SMIL — no JavaScript, no external CSS. Safe to inline in HTML, SVG
`<img src>`, and README previews.