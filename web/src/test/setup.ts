// The `/vitest` entry augments Vitest's own `Assertion` interface. Importing
// the bare package only augments Jest's, which left every jest-dom matcher
// untyped under `tsc` (toHaveTextContent, toBeInTheDocument, ...).
import "@testing-library/jest-dom/vitest";

// Polyfill localStorage for Node 26+ (--localstorage-file not provided)
if (typeof localStorage === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const store: Record<string, string> = {};
  (globalThis as any).localStorage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = String(v); },
    removeItem: (k: string) => { delete store[k]; },
    clear: () => { Object.keys(store).forEach(k => delete store[k]); },
    get length() { return Object.keys(store).length; },
    key: (i: number) => Object.keys(store)[i] ?? null,
  };
}

// Polyfill matchMedia for jsdom (used by Dialog, LoadingOverlay, AudioDropzone)
if (typeof window.matchMedia === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  });
}

// Polyfill ResizeObserver for jsdom (used by Radix UI components)
if (typeof ResizeObserver === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Polyfill PointerEvent for Radix UI
if (typeof PointerEvent === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).PointerEvent = class PointerEvent extends MouseEvent {
    constructor(type: string, init?: PointerEventInit) {
      super(type, init);
    }
  };
}
