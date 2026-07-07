# MelosViz — Identity Demo Media (L105)

Animated SVG + MP4 showcasing the [MelosViz warm-spectrum palette](../../desktop/assets/brand/tokens.css) in motion.

## Files

| File | Purpose |
|---|---|
| `demo.svg` | 480×270 animated SVG — 24 spectrum EQ bars + wave horizon + glowing mark (looped CSS animation, ~5s) |
| `demo.mp4` | H.264/MP4 rendered from `demo.svg` via playwright + ffmpeg (24fps, 5s loop) |

## Palette (MelosViz — warm spectrum)

- Outer background `#1a0e1f` → `#2d1b3a`
- Spectrum gradient: `#ef4444` → `#f59e0b` → `#facc15` → `#22d3ee` → `#a371f7`
- Highlight `#facc15` (conductor mark)
- Off-white `#f6f8fa` (label)

## Animation

- EQ bars: 1.2s ease-in-out scaleY 0.3 → 1, staggered 24 bars
- Wave overlay: 4s ease-in-out horizontal drift (horizon)
- Mark glow: 2.4s ease-in-out scale + opacity breathing

## Render command

```sh
python /tmp/svg2mp4.py demo.svg demo.mp4 480 270 24 5
```

## Source of truth

- Tokens: [`../../desktop/assets/brand/tokens.css`](../../desktop/assets/brand/tokens.css)
- Source icon: [`../../desktop/assets/brand/logo.svg`](../../desktop/assets/brand/logo.svg)
- Scorecard: `.claude/audit/.vision/L96-L107.md`