// InspectabilityPanel — fixed top-right panel showing decision records.
//
// Exported API (module-level event bus, no React dependency for push):
//   recordDecision({kind, summary, detail?})  — push a decision
//   subscribeDecisions(fn)                     — listen for new decisions
//   InspectabilityPanel                        — React component

import { useCallback, useEffect, useRef, useState } from "react";

// ---- Types -----------------------------------------------------------------

export type DecisionKind = "why" | "how" | "trace";

export interface DecisionRecord {
  kind: DecisionKind;
  summary: string;
  detail?: string;
  timestamp: number;
}

export type DecisionSubscriber = (record: DecisionRecord) => void;

// ---- Event bus (module-level singleton) ------------------------------------
// Decoupled from React: can be called from any context (effects, callbacks,
// worker messages, console helpers) without triggering renders directly.
// The React component subscribes via subscribeDecisions.

type Listener = (record: DecisionRecord) => void;

const listeners = new Set<Listener>();
const history: DecisionRecord[] = [];
const MAX_HISTORY = 50;

/**
 * Push a new decision record to the shared event bus.
 * Safe to call from any context — never throws.
 */
export function recordDecision(input: {
  kind: DecisionKind;
  summary: string;
  detail?: string;
}): void {
  const record: DecisionRecord = {
    kind: input.kind,
    summary: input.summary,
    detail: input.detail,
    timestamp: Date.now(),
  };

  history.push(record);
  if (history.length > MAX_HISTORY) {
    history.shift();
  }

  for (const fn of listeners) {
    try {
      fn(record);
    } catch {
      // Swallow subscriber errors — never break the bus
    }
  }
}

/**
 * Subscribe to new decision records. Returns an unsubscribe function.
 */
export function subscribeDecisions(fn: DecisionSubscriber): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

// ---- Colour map ------------------------------------------------------------

const BADGE_COLORS: Record<DecisionKind, string> = {
  why: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
  how: "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-500/30",
  trace: "bg-amber-500/20 text-amber-300 border-amber-500/30",
};

// ---- Component -------------------------------------------------------------

interface InspectabilityPanelProps {
  /** Maximum visible records (default 50). */
  maxVisible?: number;
}

export function InspectabilityPanel({
  maxVisible = 50,
}: InspectabilityPanelProps) {
  const [records, setRecords] = useState<DecisionRecord[]>(() => [...history]);
  const [collapsed, setCollapsed] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  // Subscribe to the event bus — append new records as they arrive
  useEffect(() => {
    const unsub = subscribeDecisions((record) => {
      setRecords((prev) => {
        const next = [...prev, record];
        return next.length > maxVisible
          ? next.slice(next.length - maxVisible)
          : next;
      });
    });
    return unsub;
  }, [maxVisible]);

  // Auto-scroll to the latest record
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [records]);

  // Per-kind counts for the header summary
  const kindCounts = useCallback(() => {
    const counts = { why: 0, how: 0, trace: 0 };
    for (const r of records) counts[r.kind]++;
    return counts;
  }, [records]);

  // ---- Collapsed state (badge button) -------------------------------------

  if (collapsed) {
    const counts = kindCounts();
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg bg-black/60 border border-white/10 px-2.5 py-1.5 text-[11px] text-white/50 hover:text-white/80 hover:bg-black/70 transition-colors backdrop-blur-sm"
        title="Show decision panel"
      >
        {/* Dot legend */}
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400"
            title="why"
          />
          <span className="text-cyan-400/70">{counts.why}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-fuchsia-400"
            title="how"
          />
          <span className="text-fuchsia-400/70">{counts.how}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400"
            title="trace"
          />
          <span className="text-amber-400/70">{counts.trace}</span>
        </span>
      </button>
    );
  }

  // ---- Expanded panel ------------------------------------------------------

  const counts = kindCounts();

  return (
    <div className="fixed top-4 right-4 z-50 w-72 max-h-[75vh] rounded-lg bg-black/60 border border-white/10 shadow-2xl backdrop-blur-sm flex flex-col overflow-hidden">
      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/10">
        <span className="text-xs font-medium text-white/50 uppercase tracking-wider">
          Decisions
        </span>

        <div className="flex items-center gap-2">
          {/* Kind counters */}
          <span className="text-[10px] text-cyan-400/70 font-medium">
            {counts.why}w
          </span>
          <span className="text-[10px] text-fuchsia-400/70 font-medium">
            {counts.how}h
          </span>
          <span className="text-[10px] text-amber-400/70 font-medium">
            {counts.trace}t
          </span>

          {/* Collapse */}
          <button
            onClick={() => setCollapsed(true)}
            className="text-white/30 hover:text-white/70 text-xs transition-colors ml-1 leading-none"
            title="Collapse panel"
            aria-label="Collapse decision panel"
          >
            −
          </button>
        </div>
      </div>

      {/* ── Record list ─────────────────────────────────────── */}
      <div
        ref={listRef}
        className="flex-1 overflow-y-auto p-2 space-y-1"
        role="log"
        aria-label="Decision records"
        aria-live="polite"
      >
        {records.length === 0 ? (
          <p className="text-[11px] text-white/20 text-center py-6">
            No decisions recorded yet
          </p>
        ) : (
          records.map((r, i) => (
            <div
              // Use timestamp + index as key since timestamps can collide
              key={`${r.timestamp}-${i}`}
              className="rounded-md border border-white/[0.06] px-2.5 py-1.5 text-xs leading-relaxed transition-colors hover:bg-white/[0.03]"
              title={r.detail}
            >
              {/* Kind badge + summary (single line) */}
              <div className="flex items-start gap-2">
                <span
                  className={`shrink-0 rounded px-1 py-[1px] text-[10px] font-medium border leading-normal ${BADGE_COLORS[r.kind]}`}
                >
                  {r.kind}
                </span>
                <span className="text-white/80 break-words min-w-0">
                  {r.summary}
                </span>
              </div>

              {/* Optional expanded detail */}
              {r.detail && (
                <p className="mt-1 text-[10px] text-white/40 pl-10 line-clamp-2 leading-relaxed">
                  {r.detail}
                </p>
              )}
            </div>
          ))
        )}
      </div>

      {/* ── Footer ──────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t border-white/10">
        <span className="text-[10px] text-white/30">
          {records.length} record{records.length !== 1 ? "s" : ""}
        </span>
        <button
          onClick={() => setRecords([])}
          className="text-[10px] text-white/30 hover:text-red-400 transition-colors"
          title="Clear all records"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
