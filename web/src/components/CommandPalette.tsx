import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";

// ---- Types ------------------------------------------------------------------

export interface Command {
  id: string;
  title: string;
  /** Optional keyboard-hint label (e.g. "⌘S") shown on the right side. */
  hint?: string;
  /** Called when the command is selected. */
  run: () => void;
}

interface CommandPaletteProps {
  commands: Command[];
}

// ---- Fuzzy scorer -----------------------------------------------------------
// Returns a score in (0, 1] when `query` fuzzy-matches `target`, or 0 if no
// match.  The scorer rewards consecutive characters, word-boundary starts, and
// early-position matches.  It is intentionally simple — no trigram index, no
// Levenshtein — so it stays fast for < 200-item lists.

function fuzzyScore(query: string, target: string): number {
  if (!query) return 1;
  const q = query.toLowerCase();
  const t = target.toLowerCase();

  let qi = 0;
  let score = 0;
  let prevMatch = -2;

  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      // Consecutive match bonus
      if (ti === prevMatch + 1) score += 3;
      else score += 1;
      // Word-boundary bonus
      if (
        ti === 0 ||
        t[ti - 1] === " " ||
        t[ti - 1] === "-" ||
        t[ti - 1] === "_"
      ) {
        score += 2;
      }
      prevMatch = ti;
      qi++;
    }
  }

  // Not every query character was found
  if (qi < q.length) return 0;

  // Normalise so longer targets don't automatically win
  return Math.min(1, score / (t.length * 2.5));
}

// ---- Component --------------------------------------------------------------

export function CommandPalette({ commands }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Filtered + ranked results
  const filtered = useMemo(() => {
    if (!query.trim()) {
      return commands.map((c, i) => ({ command: c, score: 0, index: i }));
    }

    return commands
      .map((c, i) => {
        const titleScore = fuzzyScore(query, c.title);
        const hintScore = c.hint ? fuzzyScore(query, c.hint) * 0.4 : 0;
        const score = titleScore + hintScore;
        return { command: c, score, index: i };
      })
      .filter((item) => item.score > 0)
      .sort((a, b) => {
        // Higher score first; ties broken by original order
        return b.score - a.score || a.index - b.index;
      });
  }, [commands, query]);

  // Auto-select first item whenever results change
  useEffect(() => {
    setSelectedIndex(0);
  }, [filtered.length]);

  // Focus the input when the dialog opens; clear query when it closes
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    } else {
      setQuery("");
    }
  }, [open]);

  // Keep the active item visible during keyboard navigation
  useEffect(() => {
    const el = listRef.current?.children[selectedIndex] as
      HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  const execute = useCallback((item: Command) => {
    setOpen(false);
    // Defer execution so the dialog close animation isn't blocked
    requestAnimationFrame(() => item.run());
  }, []);

  const executeSelected = useCallback(() => {
    const item = filtered[selectedIndex];
    if (item) execute(item.command);
  }, [filtered, selectedIndex, execute]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((prev) => Math.min(prev + 1, filtered.length - 1));
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((prev) => Math.max(prev - 1, 0));
          break;
        case "Enter":
          e.preventDefault();
          executeSelected();
          break;
      }
    },
    [filtered.length, executeSelected],
  );

  // Global keyboard shortcut: Cmd+K / Ctrl+K to toggle
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        {/* Backdrop */}
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />

        {/* Panel */}
        <Dialog.Content
          className="fixed left-1/2 top-[15%] z-50 w-full max-w-lg -translate-x-1/2 rounded-xl border border-white/10 bg-[#0e0e0e]/95 p-0 shadow-2xl focus:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          onKeyDown={handleKeyDown}
        >
          {/* Screen-reader title (hidden visually) */}
          <Dialog.Title className="sr-only">Command Palette</Dialog.Title>

          {/* Search input */}
          <div className="flex items-center gap-2.5 border-b border-white/10 px-4">
            <svg
              className="h-4 w-4 shrink-0 text-white/30"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z"
              />
            </svg>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              placeholder="Type a command…"
              className="flex-1 bg-transparent py-3.5 text-sm text-white/80 placeholder:text-white/30 focus:outline-none"
              aria-label="Search commands"
            />
            <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border border-white/10 bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-white/30">
              <span className="text-[11px]">&#8984;</span>K
            </kbd>
          </div>

          {/* Results */}
          <div
            ref={listRef}
            className="max-h-[280px] overflow-y-auto py-1"
            role="listbox"
            aria-label="Command results"
            aria-activedescendant={
              filtered[selectedIndex]
                ? `cmd-${filtered[selectedIndex].command.id}`
                : undefined
            }
          >
            {filtered.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-white/30">
                {query.trim()
                  ? "No matching commands"
                  : "No commands available"}
              </div>
            ) : (
              filtered.map((item, i) => (
                <button
                  key={item.command.id}
                  id={`cmd-${item.command.id}`}
                  role="option"
                  aria-selected={i === selectedIndex}
                  onMouseEnter={() => setSelectedIndex(i)}
                  onMouseDown={(e) => {
                    // Use onMouseDown so it fires before the input blur
                    e.preventDefault();
                    execute(item.command);
                  }}
                  className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
                    i === selectedIndex
                      ? "bg-white/10 text-white"
                      : "text-white/60 hover:bg-white/5 hover:text-white/80"
                  }`}
                >
                  <span className="flex-1 truncate">{item.command.title}</span>
                  {item.command.hint && (
                    <span className="shrink-0 text-[11px] text-white/30 font-mono">
                      {item.command.hint}
                    </span>
                  )}
                </button>
              ))
            )}
          </div>

          {/* Footer hints */}
          <div className="flex items-center gap-3 border-t border-white/10 px-4 py-2">
            <span className="flex items-center gap-1 text-[10px] text-white/25">
              <KbdSm>&uarr;&darr;</KbdSm> navigate
            </span>
            <span className="flex items-center gap-1 text-[10px] text-white/25">
              <KbdSm>&crarr;</KbdSm> select
            </span>
            <span className="flex items-center gap-1 text-[10px] text-white/25">
              <KbdSm>Esc</KbdSm> close
            </span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// ---- Sub-components ---------------------------------------------------------

/** Tiny inline kbd badge used in the footer hints bar. */
function KbdSm({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex min-w-[1.2rem] items-center justify-center rounded border border-white/10 bg-white/5 px-1 font-mono text-[9px] text-white/30">
      {children}
    </kbd>
  );
}
