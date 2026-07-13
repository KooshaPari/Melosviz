import * as Dialog from '@radix-ui/react-dialog'
import { SHORTCUT_DEFS } from '../hooks/useKeyboardShortcuts'

interface KeyboardHelpProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function KeyboardHelp({ open, onOpenChange }: KeyboardHelpProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        {/* Backdrop */}
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />

        {/* Panel */}
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-white/10 bg-[#0e0e0e]/95 p-6 shadow-2xl focus:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          aria-describedby="keyboard-help-desc"
          onOpenAutoFocus={(e) => {
            // Land on the labeled close control (docs/a11y/FOCUS.md initial-focus).
            e.preventDefault()
            const close = e.currentTarget.querySelector<HTMLElement>(
              '[aria-label="Close keyboard help"]',
            )
            close?.focus()
          }}
        >
          <Dialog.Title className="mb-1 text-base font-semibold text-white/90">
            Keyboard Shortcuts
          </Dialog.Title>
          <Dialog.Description id="keyboard-help-desc" className="mb-4 text-xs text-white/40">
            Press <Kbd>?</Kbd> or <Kbd>Esc</Kbd> to dismiss.
          </Dialog.Description>

          <div className="grid grid-cols-1 gap-1.5">
            {SHORTCUT_DEFS.map((s) => (
              <div
                key={s.key}
                className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-white/5 transition-colors"
              >
                <Kbd>{s.label}</Kbd>
                <span className="text-sm text-white/70">{s.description}</span>
              </div>
            ))}
          </div>

          <Dialog.Close asChild>
            <button
              className="absolute right-4 top-4 flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/80 text-xs transition-colors"
              aria-label="Close keyboard help"
            >
              ✕
            </button>
          </Dialog.Close>
        </Dialog.Content>
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
