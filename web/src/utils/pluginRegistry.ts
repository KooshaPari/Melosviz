// Browser-side plugin registry for Melosviz.
//
// Features:
//   - register(plugin) — add a plugin to the registry
//   - discover() — list registered plugins with their enabled/disabled status
//   - enable(name) / disable(name) — toggle plugin state at runtime
//   - Optional localStorage persistence via the WebPersistable adapter
//   - postMessage bridge for Capacitor / native WebView integration
//
// Workstream plug-in points (future):
//   F — dependency graph resolution between plugins (before/after constraints)
//   G — hot-reload: unregister + re-register without full-page refresh

export interface Plugin {
  /** Unique identifier for this plugin. */
  name: string;
  /** SemVer version string (e.g. "1.2.3"). */
  version: string;
  /** Human-readable summary of what the plugin provides. */
  description?: string;
  /** Lifecycle: called immediately after the plugin is registered. */
  onRegister?: () => void;
  /** Lifecycle: called when the plugin transitions from disabled → enabled. */
  onEnable?: () => void;
  /** Lifecycle: called when the plugin transitions from enabled → disabled. */
  onDisable?: () => void;
}

export interface PluginEntry {
  /** The registered plugin descriptor. */
  plugin: Plugin;
  /** Whether the plugin is currently enabled. */
  enabled: boolean;
}

/**
 * Optional persistence adapter.
 *
 * When supplied the registry will read/write the enabled-set through this
 * interface instead of raw `localStorage`.  Each method accepts sync or async
 * return values so it can wrap IndexedDB, OPFS, or a native Capacitor storage
 * plugin without forcing the caller into a particular style.
 */
export interface WebPersistable {
  getItem(key: string): string | null | Promise<string | null>;
  setItem(key: string, value: string): void | Promise<void>;
  removeItem(key: string): void | Promise<void>;
}

// ---- PostMessage protocol types ------------------------------------------
//
// Messages the registry accepts from a Capacitor / native host:
//   { type: "plugin:discover" }
//   { type: "plugin:enable",  name: "my-plugin" }
//   { type: "plugin:disable", name: "my-plugin" }
//
// Corresponding responses are posted back to `event.source`:
//   { type: "plugin:discovered", plugins: PluginEntry[], requestId?: string }
//   { type: "plugin:enabled",    name: "...",      requestId?: string }
//   { type: "plugin:disabled",   name: "...",      requestId?: string }
//   { type: "plugin:error",      error: "...",     requestId?: string }

export interface PluginMessageEvent {
  type: "plugin:discover" | "plugin:enable" | "plugin:disable";
  /** Plugin name — required for enable / disable. */
  name?: string;
  /** Opaque correlation token echoed back in the response. */
  requestId?: string;
}

export interface PluginMessageResponse {
  type:
    "plugin:discovered" | "plugin:enabled" | "plugin:disabled" | "plugin:error";
  plugins?: PluginEntry[];
  name?: string;
  requestId?: string;
  error?: string;
}

// ---- Registry ------------------------------------------------------------

const STORAGE_KEY = "melosviz:pluginRegistry:enabled";

export interface PluginRegistry {
  /**
   * Register a new plugin.
   *
   * - Throws if `plugin.name` is empty or a plugin with the same name already
   *   exists.
   * - Automatically enables the plugin if its name was previously persisted
   *   in localStorage (i.e. it was enabled before a page reload).
   */
  register(plugin: Plugin): void;

  /**
   * Return every registered plugin annotated with its current enabled state.
   * Lazily loads persisted state on first call.
   */
  discover(): Promise<PluginEntry[]>;

  /**
   * Enable a plugin by name.
   * Returns `false` if no plugin with that name is registered.
   * Persists the updated enabled-set to storage.
   */
  enable(name: string): Promise<boolean>;

  /**
   * Disable a plugin by name.
   * Returns `false` if no plugin with that name is registered.
   * Persists the updated enabled-set to storage.
   */
  disable(name: string): Promise<boolean>;

  /**
   * Look up a plugin by name without affecting its enabled state.
   * Returns `undefined` if the plugin has not been registered.
   */
  getPlugin(name: string): Plugin | undefined;

  /**
   * Start listening for `plugin:*` postMessage events from a native wrapper
   * (Capacitor, Electron, etc.).
   *
   * Returns a cleanup function that removes the listener.  Calling this
   * method while the bridge is already active is a no-op and returns the
   * **same** cleanup function.
   */
  startPostMessageBridge(): () => void;
}

/**
 * Create a new plugin registry.
 *
 * @example
 * ```ts
 * import { createPluginRegistry } from "../utils/pluginRegistry"
 *
 * const registry = createPluginRegistry()
 *
 * registry.register({
 *   name: "spectral-textures",
 *   version: "0.1.0",
 *   description: "Workstream A — spectral FFT texture overlay",
 *   onEnable() { console.log("spectral-textures enabled") },
 *   onDisable() { console.log("spectral-textures disabled") },
 * })
 *
 * // Later, in a React effect:
 * useEffect(() => {
 *   const stop = registry.startPostMessageBridge()
 *   return stop
 * }, [])
 * ```
 */
export function createPluginRegistry(
  persistable?: WebPersistable,
): PluginRegistry {
  const plugins = new Map<string, Plugin>();
  const enabled = new Set<string>();

  /** Names that were present in storage when persistence was loaded.
   *  Used to auto-enable plugins that register *after* the storage read. */
  const persistedNames = new Set<string>();

  let loaded = false;
  let loadPromise: Promise<void> | null = null;
  let bridgeCleanup: (() => void) | null = null;

  // ---- Persistence helpers ------------------------------------------------

  async function ensureLoaded(): Promise<void> {
    if (loaded) return;
    if (loadPromise) return loadPromise;

    loadPromise = (async () => {
      try {
        const raw = persistable
          ? await persistable.getItem(STORAGE_KEY)
          : localStorage.getItem(STORAGE_KEY);

        if (raw) {
          const names = JSON.parse(raw) as string[];
          for (const name of names) {
            persistedNames.add(name);
            const plugin = plugins.get(name);
            if (plugin) {
              enabled.add(name);
              plugin.onEnable?.();
            }
          }
        }
      } catch {
        // Corrupt JSON, storage unavailable, or quota denial — start fresh
      }
      loaded = true;
    })();

    return loadPromise;
  }

  async function persistState(): Promise<void> {
    const data = JSON.stringify([...enabled]);
    try {
      if (persistable) {
        await persistable.setItem(STORAGE_KEY, data);
      } else {
        localStorage.setItem(STORAGE_KEY, data);
      }
    } catch {
      // Storage full, sandbox denied, or adapter threw — best-effort
    }
  }

  // ---- PostMessage bridge -------------------------------------------------

  function handleBridgeMessage(event: MessageEvent<PluginMessageEvent>): void {
    const { type, name, requestId } = event.data;

    if (!type || !type.startsWith("plugin:")) return;

    const respond = (
      response: Omit<PluginMessageResponse, "requestId">,
    ): void => {
      try {
        if (event.source && "postMessage" in event.source) {
          (event.source as Window).postMessage(
            { ...response, requestId },
            { targetOrigin: "*" },
          );
        }
      } catch {
        // Cross-origin restrictions or detached iframe — swallow
      }
    };

    switch (type) {
      case "plugin:discover":
        registry.discover().then((plugs) => {
          respond({ type: "plugin:discovered", plugins: plugs });
        });
        break;

      case "plugin:enable":
        if (!name) {
          respond({ type: "plugin:error", error: "Missing plugin name" });
          return;
        }
        registry.enable(name).then((ok) => {
          if (ok) respond({ type: "plugin:enabled", name });
          else
            respond({
              type: "plugin:error",
              error: `Plugin "${name}" not found`,
            });
        });
        break;

      case "plugin:disable":
        if (!name) {
          respond({ type: "plugin:error", error: "Missing plugin name" });
          return;
        }
        registry.disable(name).then((ok) => {
          if (ok) respond({ type: "plugin:disabled", name });
          else
            respond({
              type: "plugin:error",
              error: `Plugin "${name}" not found`,
            });
        });
        break;
    }
  }

  // ---- Public API ---------------------------------------------------------

  const registry: PluginRegistry = {
    register(plugin: Plugin): void {
      if (!plugin.name) {
        throw new Error('Plugin must have a "name" property');
      }
      if (plugins.has(plugin.name)) {
        throw new Error(`Plugin "${plugin.name}" is already registered`);
      }

      plugins.set(plugin.name, plugin);
      plugin.onRegister?.();

      // If persistence was already loaded and this name was previously saved,
      // auto-enable the plugin now.
      if (
        loaded &&
        persistedNames.has(plugin.name) &&
        !enabled.has(plugin.name)
      ) {
        enabled.add(plugin.name);
        plugin.onEnable?.();
      }
    },

    async discover(): Promise<PluginEntry[]> {
      await ensureLoaded();
      return Array.from(plugins.values()).map((plugin) => ({
        plugin,
        enabled: enabled.has(plugin.name),
      }));
    },

    async enable(name: string): Promise<boolean> {
      await ensureLoaded();
      const plugin = plugins.get(name);
      if (!plugin) return false;
      if (enabled.has(name)) return true;
      enabled.add(name);
      plugin.onEnable?.();
      await persistState();
      return true;
    },

    async disable(name: string): Promise<boolean> {
      await ensureLoaded();
      const plugin = plugins.get(name);
      if (!plugin) return false;
      if (!enabled.has(name)) return true;
      enabled.delete(name);
      plugin.onDisable?.();
      await persistState();
      return true;
    },

    getPlugin(name: string): Plugin | undefined {
      return plugins.get(name);
    },

    startPostMessageBridge(): () => void {
      if (bridgeCleanup) return bridgeCleanup;
      window.addEventListener("message", handleBridgeMessage);
      bridgeCleanup = (): void => {
        window.removeEventListener("message", handleBridgeMessage);
        bridgeCleanup = null;
      };
      return bridgeCleanup;
    },
  };

  return registry;
}
