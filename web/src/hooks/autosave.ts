// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AutosaveOptions<T> {
  /** Debounce delay in milliseconds. Default 300. */
  delay?: number
  /** Custom serializer. Default `JSON.stringify`. */
  serialize?: (value: T) => string
  /** Custom deserializer. Default `JSON.parse`. */
  deserialize?: (raw: string) => T
  /** Called after a successful localStorage write. */
  onSave?: (value: T) => void
  /** Called when a save fails (quota exceeded, parse error, etc.). */
  onError?: (error: unknown) => void
}

export interface AutosaveHandle<T> {
  /** Current in-memory value (live, read-through to the internal cache). */
  readonly value: T
  /**
   * Update the value and schedule a debounced localStorage write.
   * Accepts a direct value or an updater function `(prev: T) => T`.
   */
  set: (next: T | ((prev: T) => T)) => void
  /** Cancel any pending debounced write. Safe to call when none is pending. */
  cancel: () => void
  /** Immediately persist the current in-memory value to localStorage. */
  flush: () => void
  /** Re-read the value from localStorage (bypasses the in-memory cache). */
  reload: () => T
}

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

function defaultSerialize<T>(value: T): string {
  return JSON.stringify(value)
}

function defaultDeserialize<T>(raw: string): T {
  return JSON.parse(raw) as T
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Create a localStorage-backed debounced autosave handle.
 *
 * Pure TypeScript — no React dependencies.  Works in any context that has
 * access to `localStorage` (browser main thread, web workers via `localstorage-ponyfill`, etc.).
 *
 * @param key     localStorage key
 * @param initial Fallback value when nothing is stored (or when hydration fails)
 * @param opts    Optional configuration
 *
 * @example
 * ```ts
 * const draft = withAutosave<MyFormData>('compose.draft', { title: '', body: '' })
 *
 * draft.set(prev => ({ ...prev, title: 'Hello' }))
 * // → persists to localStorage after 300 ms
 *
 * draft.flush()
 * // → writes immediately
 *
 * draft.cancel()
 * // → discards any pending write
 * ```
 */
export function withAutosave<T>(
  key: string,
  initial: T,
  opts: AutosaveOptions<T> = {},
): AutosaveHandle<T> {
  const {
    delay = 300,
    serialize = defaultSerialize,
    deserialize = defaultDeserialize,
    onSave,
    onError,
  } = opts

  // -----------------------------------------------------------------------
  // Hydrate — seed from localStorage if available
  // -----------------------------------------------------------------------
  let value: T = hydrate(key, initial, deserialize)

  // -----------------------------------------------------------------------
  // Debounce machinery
  // -----------------------------------------------------------------------
  let timer: ReturnType<typeof setTimeout> | null = null
  let disposed = false

  function persist(): void {
    if (disposed) return
    try {
      const serialized = serialize(value)
      localStorage.setItem(key, serialized)
      onSave?.(value)
    } catch (err) {
      onError?.(err)
    }
  }

  function schedule(): void {
    if (timer != null) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      persist()
    }, delay)
  }

  // -----------------------------------------------------------------------
  // Public methods
  // -----------------------------------------------------------------------

  function cancel(): void {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function flush(): void {
    cancel()
    persist()
  }

  function set(next: T | ((prev: T) => T)): void {
    if (disposed) return
    value = typeof next === "function" ? (next as (prev: T) => T)(value) : next
    schedule()
  }

  function reload(): T {
    if (disposed) return value
    try {
      const raw = localStorage.getItem(key)
      if (raw === null) return value
      value = deserialize(raw)
    } catch {
      // Deserialization failed — keep current in-memory value
    }
    return value
  }

  return {
    get value(): T {
      return value
    },
    set,
    cancel,
    flush,
    reload,
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function hydrate<T>(
  key: string,
  fallback: T,
  deserialize: (raw: string) => T,
): T {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    return deserialize(raw)
  } catch {
    return fallback
  }
}
