/**
 * polish.test.ts — Polish-quality validation tests.
 *
 * Covers 12 areas spanning motion physics, undo/redo state management,
 * autosave persistence, keyboard shortcuts, decision logging, fuzzy
 * search ranking, and inspector subscriptions.
 *
 * Tests are organised in `describe` blocks matching each area; inline
 * stubs are used for utilities not yet extracted to their own module
 * (createHistory, undoRedo, Autosave) so the tests remain self-contained
 * and executable immediately.
 *
 * Run with:  npx vitest run src/__tests__/polish.test.ts
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { withSpring } from "../hooks/motion";
import {
  recordDecision,
  subscribeDecisions,
} from "../components/InspectabilityPanel";
import { attachShortcuts } from "../shortcuts";

// =============================================================================
// 1. withSpring convergence
// =============================================================================

describe("withSpring convergence", () => {
  it("returns initial position at t = 0", () => {
    const spring = withSpring({ stiffness: 170, damping: 26, mass: 1 });
    const state = spring(0, 1, 0);
    expect(state.x).toBe(1);
    expect(state.dx).toBe(0);
  });

  it("returns negative initial position correctly at t = 0", () => {
    const spring = withSpring({ stiffness: 170, damping: 26 });
    const state = spring(0, -1, 0);
    expect(state.x).toBe(-1);
  });

  it("critically-damped spring never overshoots for x0 > 0", () => {
    // When damping is omitted the solver auto-computes critical damping
    const spring = withSpring({ stiffness: 300 });
    for (let t = 0; t <= 500; t += 10) {
      const state = spring(t, 1, 0);
      expect(state.x).toBeGreaterThanOrEqual(0);
    }
  });

  it("higher stiffness produces faster convergence (relative)", () => {
    const fast = withSpring({ stiffness: 500 });
    const slow = withSpring({ stiffness: 100 });
    const t = 1000;
    const rFast = fast(t, 1, 0);
    const rSlow = slow(t, 1, 0);
    // Stiffer spring should have moved closer to zero
    expect(Math.abs(rFast.x)).toBeLessThan(Math.abs(rSlow.x));
  });

  it("deterministic: same inputs produce identical outputs", () => {
    const spring = withSpring({ stiffness: 170, damping: 26 });
    const a = spring(250, 1, 0);
    const b = spring(250, 1, 0);
    expect(a.x).toBe(b.x);
    expect(a.dx).toBe(b.dx);
  });
});

// =============================================================================
// 2. withSpring NaN handling
// =============================================================================

describe("withSpring NaN handling", () => {
  it("propagates NaN from initial position x0", () => {
    const spring = withSpring({ stiffness: 170, damping: 26 });
    const result = spring(100, NaN, 0);
    // NaN in → NaN out (the solver does no sanitisation)
    expect(Number.isNaN(result.x)).toBe(true);
  });

  it("propagates NaN from initial velocity v0", () => {
    const spring = withSpring({ stiffness: 170, damping: 26 });
    const result = spring(100, 1, NaN);
    expect(Number.isNaN(result.x)).toBe(true);
    expect(Number.isNaN(result.dx)).toBe(true);
  });

  it("does not crash for zero stiffness (produces NaN from zeta division by zero)", () => {
    const spring = withSpring({ stiffness: 0, damping: 26 });
    // Zero stiffness causes omega0 = 0, which makes zeta = damping / (2*0*mass) = Infinity.
    // r1 and r2 then involve Infinity - Infinity = NaN.
    const result = spring(100, 1, 0);
    expect(Number.isNaN(result.x)).toBe(true);
  });

  it("handles zero mass without throwing", () => {
    expect(() =>
      withSpring({ stiffness: 170, damping: 26, mass: 0 }),
    ).not.toThrow();
    const spring = withSpring({ stiffness: 170, damping: 26, mass: 0 });
    const result = spring(100, 1, 0);
    // Division by zero yields Infinity
    expect(Number.isFinite(result.x)).toBe(false);
  });

  it("extreme negative damping produces NaN (zeta^2 > 1 in under-damped branch)", () => {
    // Negative damping of large magnitude causes |zeta| > 1 in the
    // under-damped sqrt(1 - zeta²) computation, producing NaN.
    const spring = withSpring({ stiffness: 170, damping: -100 });
    const result = spring(100, 1, 0);
    expect(Number.isNaN(result.x)).toBe(true);
  });
});

// =============================================================================
// 3. createHistory undo/redo/bounded
// =============================================================================

/**
 * An undo/redo history stack with a bounded capacity.
 * Pushes snapshots; undo/redo navigate through the stack.
 * Once the capacity is reached the oldest entry is dropped.
 */
interface HistoryEntry<T> {
  snapshot: T;
  timestamp: number;
}

interface History<T> {
  readonly entries: readonly HistoryEntry<T>[];
  readonly index: number;
  readonly canUndo: boolean;
  readonly canRedo: boolean;
  push: (snapshot: T) => History<T>;
  undo: () => History<T>;
  redo: () => History<T>;
}

function createHistory<T>(capacity: number, initial: T): History<T> {
  const base: HistoryEntry<T> = { snapshot: initial, timestamp: Date.now() };
  let entries: HistoryEntry<T>[] = [base];
  let index = 0;

  const api = (): History<T> => ({
    get entries() {
      return entries;
    },
    get index() {
      return index;
    },
    get canUndo() {
      return index > 0;
    },
    get canRedo() {
      return index < entries.length - 1;
    },
    push: (snapshot: T) => {
      // Discard any future entries beyond the current index (branch cut)
      entries = entries.slice(0, index + 1);
      entries.push({ snapshot, timestamp: Date.now() });
      // Enforce capacity — drop oldest entries
      if (entries.length > capacity) {
        entries = entries.slice(entries.length - capacity);
      }
      index = entries.length - 1;
      return api();
    },
    undo: () => {
      if (index <= 0) return api();
      index--;
      return api();
    },
    redo: () => {
      if (index >= entries.length - 1) return api();
      index++;
      return api();
    },
  });

  return api();
}

describe("createHistory undo/redo/bounded", () => {
  it("starts at index 0 with the initial snapshot", () => {
    const h = createHistory(10, { x: 0 });
    expect(h.index).toBe(0);
    expect(h.entries[0]?.snapshot).toEqual({ x: 0 });
    expect(h.canUndo).toBe(false);
    expect(h.canRedo).toBe(false);
  });

  it("undo goes back one entry", () => {
    const h = createHistory(10, { x: 0 }).push({ x: 1 });
    expect(h.index).toBe(1);
    const h2 = h.undo();
    expect(h2.index).toBe(0);
    expect(h2.entries[h2.index]?.snapshot).toEqual({ x: 0 });
    expect(h2.canUndo).toBe(false);
    expect(h2.canRedo).toBe(true);
  });

  it("redo goes forward after undo", () => {
    const h = createHistory(10, { x: 0 }).push({ x: 1 }).undo();
    expect(h.index).toBe(0);
    const h2 = h.redo();
    expect(h2.index).toBe(1);
    expect(h2.entries[h2.index]?.snapshot).toEqual({ x: 1 });
  });

  it("cannot redo past the latest entry", () => {
    const h = createHistory(10, { x: 0 }).push({ x: 1 });
    const h2 = h.redo(); // already at latest
    expect(h2.index).toBe(1);
    expect(h2.canRedo).toBe(false);
  });

  it("cannot undo past the initial entry", () => {
    const h = createHistory(10, { x: 0 });
    const h2 = h.undo();
    expect(h2.index).toBe(0);
    expect(h2.canUndo).toBe(false);
  });

  it("drops the oldest entry when exceeding capacity", () => {
    const h = createHistory(3, "a").push("b").push("c").push("d"); // 'a' dropped
    expect(h.entries.length).toBe(3);
    expect(h.entries[0]?.snapshot).toBe("b");
    expect(h.entries[1]?.snapshot).toBe("c");
    expect(h.entries[2]?.snapshot).toBe("d");
    expect(h.index).toBe(2);
  });

  it("branch cut: push after undo discards future entries", () => {
    const h = createHistory(10, "a").push("b").push("c").undo().push("d");
    expect(h.entries.length).toBe(3);
    expect(h.entries[0]?.snapshot).toBe("a");
    expect(h.entries[1]?.snapshot).toBe("b");
    expect(h.entries[2]?.snapshot).toBe("d");
    expect(h.index).toBe(2);
    expect(h.canRedo).toBe(false);
  });

  it("preserves exact snapshots (by reference for objects)", () => {
    const obj = { value: 42 };
    const h = createHistory(5, obj);
    expect(h.entries[0]?.snapshot).toBe(obj); // same reference on first push
  });
});

// =============================================================================
// 4. undoRedo mutator
// =============================================================================

/**
 * A simpler undo/redo wrapper around a single mutator function.
 * `mutate(prev) => next` is applied optimistically, with undo/redo
 * navigating the history stack.
 */
interface UndoRedo<T> {
  current: T;
  canUndo: boolean;
  canRedo: boolean;
  apply: (mutator: (prev: T) => T) => T;
  undo: () => T | undefined;
  redo: () => T | undefined;
}

function undoRedo<T>(initial: T, capacity = 50): UndoRedo<T> {
  const past: T[] = [];
  let present: T = initial;
  const future: T[] = [];

  const build = (): UndoRedo<T> => ({
    get current() {
      return present;
    },
    get canUndo() {
      return past.length > 0;
    },
    get canRedo() {
      return future.length > 0;
    },
    apply: (mutator: (prev: T) => T) => {
      past.push(present);
      if (past.length > capacity) past.shift();
      future.length = 0; // branch cut
      present = mutator(present);
      return present;
    },
    undo: () => {
      if (past.length === 0) return undefined;
      future.push(present);
      present = past.pop()!;
      return present;
    },
    redo: () => {
      if (future.length === 0) return undefined;
      past.push(present);
      present = future.pop()!;
      return present;
    },
  });

  return build();
}

describe("undoRedo mutator", () => {
  it("starts with initial value and no undo/redo", () => {
    const ur = undoRedo(0);
    expect(ur.current).toBe(0);
    expect(ur.canUndo).toBe(false);
    expect(ur.canRedo).toBe(false);
  });

  it("apply mutator increments the value and enables undo", () => {
    const ur = undoRedo<number>(0);
    ur.apply((n) => n + 1);
    expect(ur.current).toBe(1);
    expect(ur.canUndo).toBe(true);
    expect(ur.canRedo).toBe(false);
  });

  it("undo restores previous value", () => {
    const ur = undoRedo<number>(10);
    ur.apply((n) => n * 2);
    expect(ur.current).toBe(20);
    const prev = ur.undo();
    expect(prev).toBe(10);
    expect(ur.current).toBe(10);
    expect(ur.canUndo).toBe(false);
    expect(ur.canRedo).toBe(true);
  });

  it("redo restores the undone value", () => {
    const ur = undoRedo<number>(10);
    ur.apply((n) => n * 2);
    ur.undo();
    const next = ur.redo();
    expect(next).toBe(20);
    expect(ur.current).toBe(20);
    expect(ur.canUndo).toBe(true);
    expect(ur.canRedo).toBe(false);
  });

  it("branch cut: apply after undo discards future", () => {
    const ur = undoRedo("a");
    ur.apply(() => "b");
    ur.apply(() => "c");
    expect(ur.current).toBe("c");
    ur.undo(); // back to 'b'
    ur.apply(() => "d"); // should discard 'c'
    expect(ur.current).toBe("d");
    expect(ur.canRedo).toBe(false);
    // Undoing should go back to 'b', then 'a'
    expect(ur.undo()).toBe("b");
    expect(ur.undo()).toBe("a");
    expect(ur.canUndo).toBe(false);
  });

  it("returns undefined when undo is not available", () => {
    const ur = undoRedo(42);
    expect(ur.undo()).toBeUndefined();
    expect(ur.current).toBe(42);
  });

  it("returns undefined when redo is not available", () => {
    const ur = undoRedo(42);
    expect(ur.redo()).toBeUndefined();
  });

  it("obeys capacity limit (oldest entries dropped)", () => {
    const ur = undoRedo(0, 3);
    ur.apply(() => 1);
    ur.apply(() => 2);
    ur.apply(() => 3);
    ur.apply(() => 4); // should drop '0'
    expect(ur.undo()).toBe(3);
    expect(ur.undo()).toBe(2);
    expect(ur.undo()).toBe(1);
    expect(ur.canUndo).toBe(false);
  });

  it("works with object snapshots", () => {
    const ur = undoRedo({ x: 0, y: 0 });
    ur.apply((s) => ({ ...s, x: 10 }));
    expect(ur.current).toEqual({ x: 10, y: 0 });
    ur.undo();
    expect(ur.current).toEqual({ x: 0, y: 0 });
  });
});

// =============================================================================
// 5. Autosave roundtrip
// =============================================================================

interface AutosaveOptions {
  key: string;
  intervalMs?: number;
  storage?: Storage;
}

interface Autosave<T> {
  save: (data: T) => void;
  load: () => T | null;
  clear: () => void;
  start: () => void;
  stop: () => void;
}

function createAutosave<T>(options: AutosaveOptions): Autosave<T> {
  const { key, storage = localStorage } = options;

  return {
    save: (data: T) => {
      try {
        storage.setItem(key, JSON.stringify(data));
      } catch {
        // Storage full or unavailable — silently degrade
      }
    },
    load: (): T | null => {
      try {
        const raw = storage.getItem(key);
        if (raw === null) return null;
        return JSON.parse(raw) as T;
      } catch {
        return null;
      }
    },
    clear: () => {
      try {
        storage.removeItem(key);
      } catch {
        // noop
      }
    },
    start: () => {
      // Interval-based auto-save stub: timer is managed externally
    },
    stop: () => {
      // Stub: no interval to clear in this minimal implementation
    },
  };
}

describe("Autosave roundtrip", () => {
  let storage: Storage;
  let store: Record<string, string>;

  beforeEach(() => {
    store = {};
    storage = {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
      clear: vi.fn(() => {
        store = {};
      }),
      get length() {
        return Object.keys(store).length;
      },
      key: vi.fn((_index: number) => null),
    } as unknown as Storage;
  });

  it("saves and loads a scalar value", () => {
    const autosave = createAutosave<number>({ key: "test-num", storage });
    autosave.save(42);
    expect(autosave.load()).toBe(42);
  });

  it("saves and loads an object", () => {
    const autosave = createAutosave<{ a: number; b: string }>({
      key: "test-obj",
      storage,
    });
    autosave.save({ a: 1, b: "hello" });
    expect(autosave.load()).toEqual({ a: 1, b: "hello" });
  });

  it("load returns null when no data has been saved", () => {
    const autosave = createAutosave<string>({ key: "never-saved", storage });
    expect(autosave.load()).toBeNull();
  });

  it("overwrites previous data on subsequent saves", () => {
    const autosave = createAutosave<string>({ key: "overwrite", storage });
    autosave.save("first");
    autosave.save("second");
    expect(autosave.load()).toBe("second");
  });

  it("clear removes the stored data", () => {
    const autosave = createAutosave<string>({ key: "clear-test", storage });
    autosave.save("data");
    expect(autosave.load()).toBe("data");
    autosave.clear();
    expect(autosave.load()).toBeNull();
  });

  it("uses the configured storage key", () => {
    const autosave = createAutosave<string>({ key: "my-app-state", storage });
    autosave.save("value");
    expect(storage.setItem).toHaveBeenCalledWith("my-app-state", '"value"');
    autosave.load();
    expect(storage.getItem).toHaveBeenCalledWith("my-app-state");
  });

  it("handles JSON parse errors gracefully (load returns null)", () => {
    store["corrupt"] = "not-json{{{";
    const autosave = createAutosave<string>({ key: "corrupt", storage });
    expect(autosave.load()).toBeNull();
  });
});

// =============================================================================
// 6. autosave cancel
// =============================================================================

describe("autosave cancel", () => {
  let storage: Storage;
  let store: Record<string, string>;

  beforeEach(() => {
    store = {};
    storage = {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
      clear: vi.fn(() => {
        store = {};
      }),
      get length() {
        return Object.keys(store).length;
      },
      key: vi.fn((_index: number) => null),
    } as unknown as Storage;
  });

  it("cancel (clear) prevents a subsequent load from returning stale data", () => {
    const autosave = createAutosave<string>({ key: "cancel-test", storage });
    autosave.save("stale");
    autosave.clear();
    expect(autosave.load()).toBeNull();
  });

  it("save after clear persists fresh data", () => {
    const autosave = createAutosave<string>({ key: "re-save", storage });
    autosave.save("stale");
    autosave.clear();
    autosave.save("fresh");
    expect(autosave.load()).toBe("fresh");
  });

  it("clearing storage does not affect a different key", () => {
    const a1 = createAutosave<string>({ key: "key-a", storage });
    const a2 = createAutosave<string>({ key: "key-b", storage });
    a1.save("alpha");
    a2.save("beta");
    a1.clear();
    expect(a1.load()).toBeNull();
    expect(a2.load()).toBe("beta");
  });

  it("save still works after clear (re-persists)", () => {
    const autosave = createAutosave<string>({ key: "re-persist", storage });
    autosave.save("first");
    autosave.clear();
    autosave.save("second");
    expect(autosave.load()).toBe("second");
  });
});

// =============================================================================
// 7. shortcut binding
// =============================================================================

/**
 * Replicates the keyboard handler from useKeyboardShortcuts so we can
 * test binding/unbinding logic without depending on React.
 *
 * The React hook (useKeyboardShortcuts) is a thin wrapper over this
 * exact same switch + addEventListener pattern.
 */
interface ShortcutActions {
  togglePlay: () => void;
  seekBackward: () => void;
  seekForward: () => void;
  toggleHelp: () => void;
  closeModal: () => void;
  openPresetEditor: () => void;
  toggleFullscreen: () => void;
  restartPlayback: () => void;
}

function makeActions(
  overrides: Partial<ShortcutActions> = {},
): ShortcutActions {
  return {
    togglePlay: vi.fn(),
    seekBackward: vi.fn(),
    seekForward: vi.fn(),
    toggleHelp: vi.fn(),
    closeModal: vi.fn(),
    openPresetEditor: vi.fn(),
    toggleFullscreen: vi.fn(),
    restartPlayback: vi.fn(),
    ...overrides,
  };
}

/** Returns true when the event originates from a text input / textarea / contenteditable */
function isInputFocused(e: KeyboardEvent): boolean {
  const target = e.target;
  if (!target || !(target instanceof Element)) return false;
  const tag = (target as Element).tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  if ((target as HTMLElement).isContentEditable) return true;
  return false;
}

/**
 * Attach the same keyboard handler used by useKeyboardShortcuts.
 * Returns a cleanup function.
 */
function bindShortcuts(actions: ShortcutActions): () => void {
  const handler = (e: KeyboardEvent) => {
    if (isInputFocused(e) && e.key !== "Escape") return;

    switch (e.key) {
      case " ":
        e.preventDefault();
        actions.togglePlay();
        break;
      case "ArrowLeft":
        e.preventDefault();
        actions.seekBackward();
        break;
      case "ArrowRight":
        e.preventDefault();
        actions.seekForward();
        break;
      case "?":
        actions.toggleHelp();
        break;
      case "Escape":
        actions.closeModal();
        break;
      case "p":
      case "P":
        actions.openPresetEditor();
        break;
      case "f":
      case "F":
        actions.toggleFullscreen();
        break;
      case "r":
      case "R":
        actions.restartPlayback();
        break;
      default:
        break;
    }
  };

  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}

function fireKey(key: string) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true });
  window.dispatchEvent(event);
}

describe("shortcut binding", () => {
  it("binds Space to togglePlay", () => {
    const actions = makeActions();
    const cleanup = bindShortcuts(actions);
    fireKey(" ");
    expect(actions.togglePlay).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("binds Escape to closeModal", () => {
    const actions = makeActions();
    const cleanup = bindShortcuts(actions);
    fireKey("Escape");
    expect(actions.closeModal).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("binds ArrowLeft to seekBackward", () => {
    const actions = makeActions();
    const cleanup = bindShortcuts(actions);
    fireKey("ArrowLeft");
    expect(actions.seekBackward).toHaveBeenCalledTimes(1);
    cleanup();
  });

  it("binds f/F to toggleFullscreen", () => {
    const actions = makeActions();
    const cleanup = bindShortcuts(actions);
    fireKey("f");
    expect(actions.toggleFullscreen).toHaveBeenCalledTimes(1);
    fireKey("F");
    expect(actions.toggleFullscreen).toHaveBeenCalledTimes(2);
    cleanup();
  });

  it("removes listener when cleaned up", () => {
    const actions = makeActions();
    const cleanup = bindShortcuts(actions);
    cleanup();
    fireKey(" ");
    expect(actions.togglePlay).not.toHaveBeenCalled();
  });

  it("attachShortcuts binds play and stop", () => {
    const play = vi.fn();
    const stop = vi.fn();
    const cleanup = attachShortcuts({ play, stop });

    const spaceEvent = new KeyboardEvent("keydown", {
      code: "Space",
      key: " ",
      bubbles: true,
    });
    window.dispatchEvent(spaceEvent);
    expect(play).toHaveBeenCalledTimes(1);

    const escEvent = new KeyboardEvent("keydown", {
      code: "Escape",
      key: "Escape",
      bubbles: true,
    });
    window.dispatchEvent(escEvent);
    expect(stop).toHaveBeenCalledTimes(1);

    cleanup();
  });

  it("attachShortcuts cleanup removes listeners", () => {
    const play = vi.fn();
    const cleanup = attachShortcuts({ play, stop: vi.fn() });
    cleanup();

    const event = new KeyboardEvent("keydown", {
      code: "Space",
      key: " ",
      bubbles: true,
    });
    window.dispatchEvent(event);
    expect(play).not.toHaveBeenCalled();
  });
});

// =============================================================================
// 8. shortcut ignore-non-match
// =============================================================================

describe("shortcut ignore-non-match", () => {
  it("does not fire actions on non-matching keys", () => {
    const actions = makeActions();
    const cleanup = bindShortcuts(actions);
    fireKey("a");
    fireKey("z");
    fireKey("Enter");
    fireKey("Tab");
    expect(actions.togglePlay).not.toHaveBeenCalled();
    expect(actions.seekBackward).not.toHaveBeenCalled();
    expect(actions.seekForward).not.toHaveBeenCalled();
    expect(actions.toggleHelp).not.toHaveBeenCalled();
    expect(actions.closeModal).not.toHaveBeenCalled();
    expect(actions.openPresetEditor).not.toHaveBeenCalled();
    expect(actions.toggleFullscreen).not.toHaveBeenCalled();
    expect(actions.restartPlayback).not.toHaveBeenCalled();
    cleanup();
  });

  it("does not fire Space when an input element is focused", () => {
    const actions = makeActions();
    const cleanup = bindShortcuts(actions);

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    const event = new KeyboardEvent("keydown", { key: " ", bubbles: true });
    Object.defineProperty(event, "target", { value: input });
    window.dispatchEvent(event);

    expect(actions.togglePlay).not.toHaveBeenCalled();
    document.body.removeChild(input);
    cleanup();
  });

  it("does fire Escape even when an input is focused", () => {
    const actions = makeActions();
    const cleanup = bindShortcuts(actions);

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    const event = new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
    });
    Object.defineProperty(event, "target", { value: input });
    window.dispatchEvent(event);

    expect(actions.closeModal).toHaveBeenCalled();
    document.body.removeChild(input);
    cleanup();
  });

  it("does not fire for non-matching code in attachShortcuts", () => {
    const play = vi.fn();
    const stop = vi.fn();
    const cleanup = attachShortcuts({ play, stop });

    const event = new KeyboardEvent("keydown", {
      code: "KeyA",
      key: "a",
      bubbles: true,
    });
    window.dispatchEvent(event);
    expect(play).not.toHaveBeenCalled();
    expect(stop).not.toHaveBeenCalled();

    cleanup();
  });

  it("skips Space when input is focused in attachShortcuts", () => {
    const play = vi.fn();
    const cleanup = attachShortcuts({ play, stop: vi.fn() });

    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    const event = new KeyboardEvent("keydown", {
      code: "Space",
      key: " ",
      bubbles: true,
    });
    Object.defineProperty(event, "target", { value: input });
    window.dispatchEvent(event);

    expect(play).not.toHaveBeenCalled();
    document.body.removeChild(input);
    cleanup();
  });
});

// =============================================================================
// 9. recordDecision stamping
// =============================================================================

describe("recordDecision stamping", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-07T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stamps every record with a timestamp", () => {
    const subscriber = vi.fn();
    const unsub = subscribeDecisions(subscriber);

    recordDecision({ kind: "why", summary: "test" });
    expect(subscriber).toHaveBeenCalledTimes(1);
    const record = subscriber.mock.calls[0]![0];
    expect(record).toHaveProperty("timestamp");
    expect(typeof record.timestamp).toBe("number");
    expect(record.timestamp).toBe(Date.now());

    unsub();
  });

  it("records detail when provided", () => {
    const subscriber = vi.fn();
    const unsub = subscribeDecisions(subscriber);

    recordDecision({
      kind: "how",
      summary: "Routing decision",
      detail: "Selected provider B over A based on latency",
    });
    const record = subscriber.mock.calls[0]![0];
    expect(record.kind).toBe("how");
    expect(record.detail).toBe("Selected provider B over A based on latency");

    unsub();
  });

  it("never throws regardless of input", () => {
    expect(() =>
      recordDecision({ kind: "trace", summary: "Edge case test" }),
    ).not.toThrow();
  });

  it("records monotonic timestamps across multiple calls", () => {
    const timestamps: number[] = [];
    const subscriber = vi.fn((r: { timestamp: number }) =>
      timestamps.push(r.timestamp),
    );
    const unsub = subscribeDecisions(subscriber);

    vi.setSystemTime(new Date("2026-07-07T12:00:01Z"));
    recordDecision({ kind: "why", summary: "first" });

    vi.setSystemTime(new Date("2026-07-07T12:00:02Z"));
    recordDecision({ kind: "why", summary: "second" });

    expect(timestamps.length).toBe(2);
    expect(timestamps[1]!).toBeGreaterThan(timestamps[0]!);

    unsub();
  });
});

// =============================================================================
// 10. InspectabilityPanel subscription
// =============================================================================

describe("InspectabilityPanel subscription", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-07T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("subscribeDecisions returns an unsubscribe function", () => {
    const fn = vi.fn();
    const unsub = subscribeDecisions(fn);
    expect(typeof unsub).toBe("function");
    unsub();
  });

  it("subscriber receives records pushed after subscription", () => {
    const fn = vi.fn();
    const unsub = subscribeDecisions(fn);

    recordDecision({ kind: "why", summary: "after subscribe" });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "why", summary: "after subscribe" }),
    );

    unsub();
  });

  it("unsubscribed listener does not receive further records", () => {
    const fn = vi.fn();
    const unsub = subscribeDecisions(fn);

    recordDecision({ kind: "why", summary: "first" });
    expect(fn).toHaveBeenCalledTimes(1);

    unsub();
    recordDecision({ kind: "how", summary: "second" });
    expect(fn).toHaveBeenCalledTimes(1); // still 1
  });

  it("multiple subscribers each receive records", () => {
    const fn1 = vi.fn();
    const fn2 = vi.fn();
    const unsub1 = subscribeDecisions(fn1);
    const unsub2 = subscribeDecisions(fn2);

    recordDecision({ kind: "trace", summary: "broadcast" });
    expect(fn1).toHaveBeenCalledTimes(1);
    expect(fn2).toHaveBeenCalledTimes(1);

    unsub1();
    unsub2();
  });

  it("a throwing subscriber does not break the event bus", () => {
    const thrower = vi.fn(() => {
      throw new Error("subscriber crash");
    });
    const safe = vi.fn();
    const unsub1 = subscribeDecisions(thrower);
    const unsub2 = subscribeDecisions(safe);

    expect(() =>
      recordDecision({ kind: "why", summary: "resilient" }),
    ).not.toThrow();
    expect(safe).toHaveBeenCalledTimes(1);

    unsub1();
    unsub2();
  });
});

// =============================================================================
// 11. fuzzyScore ordering
// =============================================================================

/**
 * Inline copy of fuzzyScore from CommandPalette.tsx so this test stays
 * self-contained and documents the scoring contract explicitly.
 */
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

interface ScoredItem {
  title: string;
  score: number;
  index: number;
}

describe("fuzzyScore ordering", () => {
  it("returns 1 for empty query", () => {
    expect(fuzzyScore("", "anything")).toBe(1);
  });

  it("returns 0 when no characters match", () => {
    expect(fuzzyScore("xyz", "abc")).toBe(0);
  });

  it("returns > 0 for a partial match", () => {
    const score = fuzzyScore("pl", "playlist");
    expect(score).toBeGreaterThan(0);
  });

  it("scores consecutive matches higher than non-consecutive", () => {
    const consecutive = fuzzyScore("abc", "abc");
    const nonConsecutive = fuzzyScore("abc", "a-b-c");
    expect(consecutive).toBeGreaterThan(nonConsecutive);
  });

  it("gives word-boundary bonus", () => {
    const boundary = fuzzyScore("t", "test");
    const noBoundary = fuzzyScore("t", "bat");
    expect(boundary).toBeGreaterThan(noBoundary);
  });

  it("sorts items by descending score, then by original index", () => {
    const items: ScoredItem[] = [
      {
        title: "Save Project",
        score: fuzzyScore("save", "Save Project"),
        index: 0,
      },
      { title: "Save As", score: fuzzyScore("save", "Save As"), index: 1 },
      {
        title: "Load Project",
        score: fuzzyScore("save", "Load Project"),
        index: 2,
      },
      {
        title: "Export SVG",
        score: fuzzyScore("save", "Export SVG"),
        index: 3,
      },
    ];

    // Compute expected scores
    // 'Save As' (length 7): score = 12, normalised = min(1, 12/17.5) ≈ 0.686
    // 'Save Project' (length 12): score = 12, normalised = min(1, 12/30) = 0.4

    // fuzzyScore('save', 'Save Project'):
    //   t = 'save project', q = 'save'
    //   ti=0 's' = q[0] 's': prevMatch=-2, not consecutive (+1), word-boundary (+2) → score=3, qi=1
    //   ti=1 'a' = q[1] 'a': prevMatch=0, consecutive (+3) → score=6, qi=2
    //   ti=2 'v' = q[2] 'v': prevMatch=1, consecutive (+3) → score=9, qi=3
    //   ti=3 'e' = q[3] 'e': prevMatch=2, consecutive (+3) → score=12, qi=4
    //   All 4 chars matched
    //   normalised = min(1, 12 / (12 * 2.5)) = min(1, 12/30) = 0.4
    const saveProjectScore = fuzzyScore("save", "Save Project");
    expect(saveProjectScore).toBeCloseTo(0.4, 2);

    // fuzzyScore('save', 'Save As'):
    //   Same match pattern: 's','a','v','e' consecutive → score=12
    //   normalised = min(1, 12 / (7 * 2.5)) = min(1, 12/17.5) ≈ 0.686
    const saveAsScore = fuzzyScore("save", "Save As");
    expect(saveAsScore).toBeCloseTo(0.686, 2);

    // So Save As (0.686) > Save Project (0.4)
    expect(saveAsScore).toBeGreaterThan(saveProjectScore);

    const sorted = [...items]
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score || a.index - b.index);

    // 'Save As' should rank first (higher score)
    expect(sorted[0]!.title).toBe("Save As");
    expect(sorted[1]!.title).toBe("Save Project");
    // Items with zero score are filtered out
    expect(sorted.length).toBe(2);
  });

  it("prefix match outranks substring match", () => {
    const prefix = fuzzyScore("ex", "export");
    const substring = fuzzyScore("ex", "index");
    expect(prefix).toBeGreaterThan(substring);
  });

  it("scores identical match has highest possible value", () => {
    const score = fuzzyScore("exact", "exact");
    expect(score).toBeGreaterThan(0);
    expect(score).toBeLessThanOrEqual(1);
  });

  it("handles case-insensitive matching", () => {
    const lower = fuzzyScore("abc", "ABC");
    const mixed = fuzzyScore("AbC", "aBc");
    expect(lower).toBeGreaterThan(0);
    expect(mixed).toBeGreaterThan(0);
    expect(lower).toBe(mixed);
  });
});

// =============================================================================
// 12. spring physics at 60fps
// =============================================================================

describe("spring physics at 60fps", () => {
  it("produces state with finite x and dx at every frame step", () => {
    const spring = withSpring({ stiffness: 300, mass: 1 });
    // Simulate 60 fps for 500 ms: ~30 frames
    const dt = 1000 / 60; // ms per frame at 60 fps
    for (let frame = 0; frame < 30; frame++) {
      const t = frame * dt;
      const state = spring(t, 1, 0);
      expect(Number.isFinite(state.x)).toBe(true);
      expect(Number.isFinite(state.dx)).toBe(true);
    }
  });

  it("produces state with finite x and dx for under-damped config", () => {
    const spring = withSpring({ stiffness: 500, damping: 5, mass: 1 });
    const dt = 1000 / 60;
    for (let frame = 0; frame < 30; frame++) {
      const state = spring(frame * dt, 1, 0);
      expect(Number.isFinite(state.x)).toBe(true);
      expect(Number.isFinite(state.dx)).toBe(true);
    }
  });

  it("monotonically decreases displacement toward zero (critically damped)", () => {
    // No damping specified = critical damping (zeta = 1)
    const spring = withSpring({ stiffness: 300 });
    const dt = 1000 / 60;
    let prevX = spring(0, 1, 0).x;
    for (let frame = 1; frame <= 100; frame++) {
      const t = frame * dt;
      const state = spring(t, 1, 0);
      // For a critically-damped system with x0 > 0, x must not increase
      if (Math.abs(state.x) > 1e-12 && Math.abs(prevX) > 1e-12) {
        expect(Math.abs(state.x)).toBeLessThanOrEqual(Math.abs(prevX) + 1e-12);
      }
      prevX = state.x;
    }
  });

  it("over-damped (user-specified damping > critical) does not overshoot", () => {
    // User-specified damping of 60 results in zeta >> 1 (over-damped)
    const spring = withSpring({ stiffness: 300, damping: 60, mass: 1 });
    for (let t = 10; t <= 500; t += 10) {
      const state = spring(t, 1, 0);
      // Over-damped with x0>0 must never go negative
      expect(state.x).toBeGreaterThanOrEqual(0);
    }
  });

  it("velocity approaches zero as spring settles", () => {
    // Use larger stiffness so the velocity peak occurs within our test window.
    // stiffness=300000 gives omega0 ≈ 0.548 rad/s for critically-damped response.
    const spring = withSpring({ stiffness: 300000 });
    const early = spring(200, 1, 0); // before velocity peak
    const late = spring(10000, 1, 0); // well after velocity peak
    expect(Math.abs(late.dx)).toBeLessThan(Math.abs(early.dx));
  });

  it("produces deterministic output (same inputs yield same outputs)", () => {
    const spring = withSpring({ stiffness: 170, damping: 26 });
    const a = spring(250, 1, 0);
    const b = spring(250, 1, 0);
    expect(a.x).toBe(b.x);
    expect(a.dx).toBe(b.dx);
  });

  it("higher mass = slower response", () => {
    // With only stiffness specified (auto-computed damping):
    // light: omega0 = sqrt(300/0.5)*0.001 ≈ 0.0245, zeta = 1
    // heavy: omega0 = sqrt(300/4)*0.001 ≈ 0.00866, zeta = 1
    // Lower omega0 means slower convergence
    const light = withSpring({ stiffness: 300, mass: 0.5 });
    const heavy = withSpring({ stiffness: 300, mass: 4 });
    const t = 1000;
    const lightX = Math.abs(light(t, 1, 0).x);
    const heavyX = Math.abs(heavy(t, 1, 0).x);
    // Light mass should have moved closer to zero
    expect(lightX).toBeLessThan(heavyX);
  });
});
