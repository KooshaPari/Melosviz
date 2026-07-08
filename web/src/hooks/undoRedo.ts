/**
 * Bounded undo/redo history for any serializable value.
 *
 * Provides two export levels:
 *   - `createHistory<T>(initial, maxSteps?)` — low-level state container
 *   - `undoRedo<T, Op>(initial, apply, options?)` — operation-based convenience wrapper
 *
 * Both cap history at 64 entries by default.
 * Pure TypeScript — no React imports.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A bounded undo/redo history container. */
export interface History<T> {
  /** The current value (live-updated by push/undo/redo). */
  readonly value: T;

  /** Push a new state onto the history, discarding any "future" (redo) entries. */
  push(next: T): void;

  /** Rewind to the previous state. Returns `true` if the value changed. */
  undo(): boolean;

  /** Advance to a previously-undone state. Returns `true` if the value changed. */
  redo(): boolean;

  /** Index of the current state in the internal list (0 = oldest). */
  readonly index: number;

  /** Total number of entries currently stored. */
  readonly length: number;

  /** Whether an undo step is available. */
  readonly canUndo: boolean;

  /** Whether a redo step is available. */
  readonly canRedo: boolean;

  /** Reset to the initial value, discarding the entire history. */
  clear(): void;

  /** Replace the current value *in place* without creating a new history entry. */
  replace(next: T): void;
}

/** Options shared by both `createHistory` and `undoRedo`. */
export interface UndoRedoOptions {
  /** Maximum number of history entries (default: 64, min: 2). */
  maxSteps?: number;
}

/** Return shape of the higher-level `undoRedo` wrapper. */
export interface UndoRedoController<T, Op = unknown> {
  /** Current (committed) value. */
  readonly value: T;

  /** Apply an operation — transforms the current state and pushes a history entry. */
  execute(op: Op): void;

  /** Undo the most recent operation. Returns `true` if the value changed. */
  undo(): boolean;

  /** Redo a previously-undone operation. Returns `true` if the value changed. */
  redo(): boolean;

  /** Whether undo is available. */
  readonly canUndo: boolean;

  /** Whether redo is available. */
  readonly canRedo: boolean;

  /** Discard all history and reset to the initial value. */
  clear(): void;

  /** The underlying history instance (for advanced inspection). */
  readonly history: History<T>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_MAX_STEPS = 64;

// ---------------------------------------------------------------------------
// createHistory
// ---------------------------------------------------------------------------

/**
 * Create a bounded undo/redo history container.
 *
 * @param initial - The starting value.
 * @param options - Optional `maxSteps` (default 64, minimum 2).
 */
export function createHistory<T>(
  initial: T,
  options: number | UndoRedoOptions = {},
): History<T> {
  const maxSteps = Math.max(
    2,
    typeof options === "number"
      ? options
      : (options.maxSteps ?? DEFAULT_MAX_STEPS),
  );

  /** Internal ring of states. `cursor` points to the **current** entry. */
  const entries: T[] = [initial];
  let cursor = 0;

  const history: History<T> = {
    get value(): T {
      return entries[cursor] as T;
    },

    push(next: T): void {
      // Discard any future (redo) entries beyond the cursor.
      entries.length = cursor + 1;

      entries.push(next);

      // Evict the oldest entry when we exceed the cap.
      if (entries.length > maxSteps) {
        entries.shift();
      } else {
        cursor++;
      }
    },

    undo(): boolean {
      if (cursor <= 0) return false;
      cursor--;
      return true;
    },

    redo(): boolean {
      if (cursor >= entries.length - 1) return false;
      cursor++;
      return true;
    },

    get index(): number {
      return cursor;
    },

    get length(): number {
      return entries.length;
    },

    get canUndo(): boolean {
      return cursor > 0;
    },

    get canRedo(): boolean {
      return cursor < entries.length - 1;
    },

    clear(): void {
      entries.length = 0;
      entries.push(history.value); // keep current value as the sole entry
      cursor = 0;
    },

    replace(next: T): void {
      entries[cursor] = next;
    },
  };

  return history;
}

// ---------------------------------------------------------------------------
// undoRedo
// ---------------------------------------------------------------------------

/**
 * Higher-level undo/redo controller that maps domain operations (`Op`) to
 * state transitions via an `apply` reducer.
 *
 * @example
 * ```ts
 * const counter = undoRedo(
 *   0,                                              // initial
 *   (state, op: "inc" | "dec" | { set: number }) => // apply
 *     op === "inc" ? state + 1 :
 *     op === "dec" ? state - 1 :
 *     op.set,
 * );
 *
 * counter.execute("inc");       // 1
 * counter.execute("inc");       // 2
 * counter.execute("dec");       // 1
 * counter.undo();               // → 2
 * counter.redo();               // → 1
 * ```
 */
export function undoRedo<T, Op = unknown>(
  initial: T,
  apply: (state: T, operation: Op) => T,
  options: UndoRedoOptions = {},
): UndoRedoController<T, Op> {
  const history = createHistory<T>(initial, options);

  const controller: UndoRedoController<T, Op> = {
    get value(): T {
      return history.value;
    },

    execute(op: Op): void {
      const next = apply(history.value, op);
      history.push(next);
    },

    undo(): boolean {
      return history.undo();
    },

    redo(): boolean {
      return history.redo();
    },

    get canUndo(): boolean {
      return history.canUndo;
    },

    get canRedo(): boolean {
      return history.canRedo;
    },

    clear(): void {
      history.clear();
    },

    get history(): History<T> {
      return history;
    },
  };

  return controller;
}
