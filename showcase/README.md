# MelosViz Polish Showcase

Interactive live-preview of every polish surface in the MelosViz design system.

## Contents

### Motion tokens (`web/src/hooks/motion.ts`)
- 4 distinct easing curves (standard / emphasized / decelerate / tween-out)
- Critically-damped `withSpring()` solver
- `prefersReducedMotion()` helper
- `motionTokens` reference map

### React motion hooks (`web/src/hooks/motion-hooks.ts`)
- `useReducedMotion()` — early-exit all animations when user prefers reduced motion
- `useSpring(initial, target, opts)` — critically-damped
- `useInView(ref, {threshold, once})` — rise-in on scroll
- `useStagger(items, {delay=40})` — staggered mount/unmount
- `useHover()` — press + rise feedback

### A11y utilities (`web/src/utils/a11y.ts`)
- `contrastRatio(fg, bg)` — WCAG 2.2 relative luminance
- `meetsAA(ratio)` / `meetsAAA(ratio)`
- `suggestAlternative(fg, bg)` — auto-shift hue until AAA
- `focusRing(opts)` — 3px outset + AAA contrast
- `announceLive(text, opts)` — aria-live mount

### Sound design (`web/src/utils/sound.ts`)
- Render-complete chime (3-note ascending arpeggio)
- Render-failed chime (descending diminished)
- Stage-cue blip
- Toggleable via preferences; respects autoplay policy

### Command palette (`web/src/components/CommandPalette.tsx`)
- Cmd+K / Ctrl+K opens fuzzy-search
- Esc closes; backdrop click closes
- Enter or click to run

### Inspectability panel (`web/src/components/InspectabilityPanel.tsx`)
- `recordDecision({kind, summary, detail})`
- `subscribeDecisions(fn)` — 50-entry rolling panel
- Shows why / how / trace decisions from the render pipeline

### Confetti (`web/src/components/Confetti.tsx`)
- 24 particles, 600ms life, hue-rotated
- Triggers on stage=complete + progress>=1
- Camera-fixed (no scroll interference)

### Progress bar (`web/src/components/ProgressBar.tsx`)
- 4 staged labels: decoding → routing → muxing → complete
- Gradient pulse (1.2s loop)
- Error state: drains to red + "we hit a snag"

### Undo/redo (`web/src/hooks/undoRedo.ts`)
- Bounded history stack (64 steps)
- `createHistory<T>(initial, {maxSteps})`
- `undoRedo<T, Op>(initial, mutator)` — op-based variant

### Autosave (`web/src/hooks/autosave.ts`)
- `withAutosave<T>(key, initial, {debounceMs: 300})`
- localStorage round-trip; cancel does not write

### Keyboard shortcuts (`web/src/hooks/shortcuts.ts` via `web/src/shortcuts.ts`)
- `ShortcutRegistry.bind(combo, callback)`
- "mod" auto-detects Cmd (macOS) / Ctrl (other)
- Handles mod+K, mod+Z, mod+Shift+Z, mod+S

### Error boundary (`web/src/components/ErrorBoundary.tsx`)
- Component-level boundary emitting `journey_abandoned`
- Fallback: refresh + copy-error-id
- Wraps App at root

### Web MCP client (`web/src/utils/mcpClient.ts`)
- JSON-RPC 2.0 over bridge /mcp
- `initialize`, `tools/list`, `tools/call`
- Exponential backoff reconnect

### Web plugin registry (`web/src/utils/pluginRegistry.ts`)
- Browser-side discovery mirroring backend `conductor/plugins.py`
- `register(plugin)`, `discover()`, `enable(id)`, `disable(id)`
- localStorage persist + postMessage export

## How to preview

```bash
# Web surfaces (vitest-based)
cd web && npx vitest run src/__tests__/polish.test.ts

# CSS tokens (open in browser)
open desktop/assets/brand/motion.css

# Backend CLI expressiveness
cd backend && python3 -m pytest tests/test_cli_expressiveness.py -v
```
