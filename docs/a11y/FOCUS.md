# Focus choreography contract

Applies to desktop shell (`desktop/views/main/index.html`), web SPA modals
(`KeyboardHelp`, `PresetEditor`), and `web/a11y/fixture.html`.

## Rules

1. **Skip link** — first focusable control is “Skip to main content” → `#main`.
2. **Focus ring** — interactive controls use `:focus-visible` with
   `outline: 3px solid var(--mv-neon-cyan / #22d3ee); outline-offset: 2px`.
3. **Tab order** — DOM order only; no positive `tabindex` except skip target
   (`#main` uses `tabIndex={-1}` as a programmatic focus target after skip).
   Desktop shell: titlebar → pipeline actions → inspector → status.
   Web SPA: see **Web SPA tab order** and **PlaybackTransport** below.
4. **Modals / errors** — error dismiss button remains in tab order when visible.
5. **Reduced motion** — focus rings stay; animations collapse (see tokens).

## Modal focus trap (SPA)

Radix `Dialog` hosts (`KeyboardHelp`, `PresetEditor`) own modal choreography:

| Concern | Contract |
|---------|----------|
| **Trap** | While open, Tab / Shift+Tab cycle only inside `Dialog.Content` (Radix focus scope). |
| **Initial focus** | On open, move focus into the dialog via `onOpenAutoFocus` — prefer the first labeled control (close, select, or primary field), not the page behind. |
| **Esc** | Escape closes the dialog (`onOpenChange(false)`); do not swallow Esc outside the dialog. |
| **Restore** | On close (Esc, close control, or Apply), return focus to the element that opened the dialog (trigger) or the last focused page control. Radix `onCloseAutoFocus` handles this by default — do not `preventDefault` unless replacing with an explicit restore target. |

### Implementation notes

- Prefer Radix defaults; only override `onOpenAutoFocus` when the first
  focusable in DOM order is a poor landing spot (e.g. a decorative icon).
- Do not nest focus traps. One modal at a time.
- Backdrop clicks close when Radix dismiss is enabled; focus still restores.

## Canvas / R3F screen reader (SceneView)

WebGL `<canvas>` pixels are opaque to assistive tech. `SceneView` provides a
**deterministic text mirror** of the interpolated scene state (W-329):

| Surface | Role | Content |
|---------|------|---------|
| Canvas wrapper | `role="img"` | Short `aria-label` (scene + playhead %) |
| Detail paragraph | `aria-describedby` target | Full non-visual summary: time, tempo, key, beats, colors, camera, geometry |
| Live region | `role="status"` + `aria-live="polite"` | Announces when scene label or discrete seek changes |

`buildSceneSummary` in `web/src/utils/sceneSummary.ts` derives all strings from
`RenderSpec` + `playbackT` only (no wall-clock) so Vitest and a11y CI stay
stable while the mesh animates. Pass `currentSceneLabel` from the shell
(see `App.tsx`). The canvas is `aria-hidden` so AT prefers the text mirror.

See also `docs/a11y/CANVAS_SR.md` for the full contract.

## Web SPA tab order (studio shell)

Cold-start Tab sequence in `web/src/App.tsx` (W-352, W-365, W-356–362):

| # | Region | Controls (in order) |
|---|--------|---------------------|
| 1 | Skip link | “Skip to main content” → `#main` |
| 2 | `#main` header | LocaleSwitcher → high-contrast (HC) → theme (Aa) → **fullscreen** (`aria-pressed`, **F**) → keyboard help (**?**) |
| 3 | Analyze card | AudioDropzone (path input, recent list, clear-recent) → **Analyze** / **Cancel** |
| 4 | Error alert (when visible) | **Retry** → **Dismiss** (`aria-label`; stays in tab order per rule 4) |
| 5 | SpecViewer | summary line → Download JSON → Copy JSON |
| 6 | Presets row | Start/Stop Audio → **Preset quick-apply** `<select>` → Preset Editor trigger |
| 7 | Playlist (`left-72`) | playlist rows → Alt+↑/↓ reorder buttons when row focused |
| 8 | Scene panel (right) | scene-jump buttons |
| 9 | **PlaybackTransport** (bottom bar) | see table below |

Fullscreen (**F** or titlebar control) raises the canvas `z-index`; **Esc** exits
fullscreen or closes Keyboard Help / Preset Editor (modal restore per above).

## PlaybackTransport (W-358–370)

Bottom-bar transport in `web/src/components/PlaybackTransport.tsx`. All controls
use i18n `aria-label` / `aria-valuetext`; decorative emoji icons are not named
separately (label carries meaning).

### Tab order (left → right within the bar)

| # | Control | Role / notes |
|---|---------|--------------|
| 1 | Play / pause | `button`; `aria-label` reflects playing vs paused |
| 2 | Seek scrubber | `range`; `aria-valuetext` = elapsed / total time readout (W-358) |
| 3 | Mute | `button`; `aria-pressed` = muted; keyboard **M** (W-360, W-366) |
| 4 | Volume | `range`; 0–100%; un-mutes when dragged above 0 while muted |
| 5 | Rate presets | `role="group"` + preset `button`s (0.5× / 1× / 1.5×); `aria-pressed` on active preset; hidden below `sm` breakpoint (W-370) |
| 6 | Rate slider | `range`; 50–150%; `aria-valuetext` includes current × multiplier (W-367) |
| 7 | Loop | `button`; `aria-pressed` = loop on; keyboard **L** (W-369, W-372) |
| 8 | Reset | `button`; restarts playhead at 0 (keyboard **R** at window level) |

Below the bar: status dot + text (not focusable). **Seek hint chips** (← ±5 s,
→ ±5 s) are `aria-hidden="true"` — visual reminders only; actual seek is
**←** / **→** window shortcuts (W-363). BPM footer is static text.

### Screen reader notes

| Concern | Contract |
|---------|----------|
| **Time** | Elapsed/total shown in seek `aria-valuetext`; footer time span is `aria-live="off"` (no duplicate announcements on scrub) |
| **Mute / loop** | Toggle buttons expose state via `aria-pressed`; prefs persist (`playbackVolume`, `playbackLoop` localStorage) |
| **Rate** | Preset group has `aria-label`; active preset `aria-pressed`; slider `aria-valuetext` names multiplier |
| **Scene context** | `currentSceneLabel` under seek bar is visual; discrete scene changes also hit SceneView `role="status"` live region |
| **Hidden audio** | `<audio class="sr-only" aria-hidden="true">` — volume/mute UI is the accessible surface |
| **Keyboard parity** | **Space** play/pause, **←/→** ±5 s seek, **M** mute, **L** loop, **R** reset, **F** fullscreen, **P** preset editor, **?** help — listed in Keyboard Help dialog (grouped Playback / View / Help) |

### Preset quick-apply (W-362)

`<select>` in `#main` presets row: native focus ring; choosing a built-in preset
applies without opening Preset Editor. Editor dialog follows modal trap above.

## Verification

- Manual: Tab from cold start; skip link appears; Enter lands in `#main`.
- Manual (SPA): open Keyboard Help / Preset Editor — focus is inside the
  panel; Tab cycles within; Esc restores focus to the opener.
- Manual (SPA): scrub playback / jump scenes — SR announces scene label,
  playhead position, tempo, and interpolated visual state via the SceneView
  live region; focus the canvas wrapper for the full `aria-describedby` summary.
- Manual (SPA): Tab through PlaybackTransport — play → seek → mute → volume →
  rate presets (wide viewport) → rate slider → loop → reset; **M** / **L** toggle
  mute and loop with `aria-pressed` feedback; seek hint chips are skipped by AT.
- Manual (SPA): fullscreen **F** / Esc; preset quick-apply `<select>` before
  opening full Preset Editor.
- Automated: axe `wcag2a,wcag2aa` on fixture (includes focusable controls).
- Fixture note: `web/a11y/fixture.html` documents the modal trap contract for
  Playwright / axe goldens (static page has no live Dialog; SPA tests cover
  trap/restore).
