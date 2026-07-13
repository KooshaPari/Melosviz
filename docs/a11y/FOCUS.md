# Focus choreography contract

Applies to desktop shell (`desktop/views/main/index.html`), web SPA modals
(`KeyboardHelp`, `PresetEditor`), and `web/a11y/fixture.html`.

## Rules

1. **Skip link** — first focusable control is “Skip to main content” → `#main`.
2. **Focus ring** — interactive controls use `:focus-visible` with
   `outline: 3px solid var(--mv-neon-cyan / #22d3ee); outline-offset: 2px`.
3. **Tab order** — titlebar → pipeline actions → inspector → status; no
   positive `tabindex` except skip target.
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

## Verification

- Manual: Tab from cold start; skip link appears; Enter lands in `#main`.
- Manual (SPA): open Keyboard Help / Preset Editor — focus is inside the
  panel; Tab cycles within; Esc restores focus to the opener.
- Automated: axe `wcag2a,wcag2aa` on fixture (includes focusable controls).
- Fixture note: `web/a11y/fixture.html` documents the modal trap contract for
  Playwright / axe goldens (static page has no live Dialog; SPA tests cover
  trap/restore).
