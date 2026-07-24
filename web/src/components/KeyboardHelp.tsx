import { Dialog, DialogContent, DialogOverlay } from './Dialog'
import { t } from '../i18n'
import { SHORTCUT_DEFS, SHORTCUT_GROUPS } from '../hooks/useKeyboardShortcuts'

interface KeyboardHelpProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function KeyboardHelp({ open, onOpenChange }: KeyboardHelpProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        {/* Backdrop */}
        <DialogOverlay className="z-50" />

        {/* Panel */}
        <DialogContent
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-white/10 bg-[#0e0e0e]/95 p-6 shadow-2xl"
          aria-describedby="keyboard-help-desc"
          onOpenAutoFocus={(e) => {
            // Land on the labeled close control (docs/a11y/FOCUS.md initial-focus).
            e.preventDefault()
            const close = e.currentTarget.querySelector<HTMLElement>(
              '#keyboard-help-close',
            )
            close?.focus()
          }}
        >
          <Dialog.Title className="mb-1 text-base font-semibold text-white/90">
            {t('keyboard.title')}
          </Dialog.Title>
          <Dialog.Description id="keyboard-help-desc" className="mb-4 text-xs text-white/40">
            {t('keyboard.dismiss')}
          </Dialog.Description>

          <div className="flex flex-col gap-4">
            {SHORTCUT_GROUPS.map((group) => (
              <section key={group} aria-labelledby={`keyboard-section-${group}`}>
                <h3
                  id={`keyboard-section-${group}`}
                  className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-white/35"
                >
                  {t(`keyboard.section.${group}`)}
                </h3>
                <div className="grid grid-cols-1 gap-1">
                  {SHORTCUT_DEFS.filter((s) => s.group === group).map((s) => (
                    <div
                      key={s.key}
                      className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-white/5 transition-colors"
                    >
                      <Kbd>{t(s.labelKey)}</Kbd>
                      <span className="text-sm text-white/70">{t(s.description)}</span>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>

          <Dialog.Close asChild>
            <button
              id="keyboard-help-close"
              className="absolute right-4 top-4 flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/80 text-xs transition-colors"
              aria-label={t('keyboard.close')}
            >
              ✕
            </button>
          </Dialog.Close>
        </DialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex min-w-[2rem] items-center justify-center rounded border border-white/20 bg-white/10 px-1.5 py-0.5 font-mono text-[11px] text-white/80 shadow-sm">
      {children}
    </kbd>
  )
}
