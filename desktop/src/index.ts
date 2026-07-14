/**
 * MelosViz desktop app — Electrobun main process (bun side).
 *
 * Responsibilities:
 *  1. Open the main BrowserWindow immediately on startup
 *  2. Locate the bundled Python backend sidecar (non-blocking)
 *  3. Spawn the FastAPI HTTP bridge on a free port asynchronously
 *     — the UI renders immediately; backend connects in the background
 */

import {
  BrowserWindow,
  Tray,
  Updater,
  defineElectrobunRPC,
  Utils,
} from "electrobun/bun";
const { openFileDialog, showItemInFolder } = Utils;
import * as path from "path";
import * as fs from "fs";
import type { BunRequests, WebviewRequests } from "./rpc";
import { t as i18n } from "./i18n";
// ---------------------------------------------------------------------------
// Backend sidecar state — populated asynchronously after window opens
// ---------------------------------------------------------------------------

let backendDir: string | null = null;
let backendPort: number = 0;
let bridgeProc: ReturnType<typeof Bun.spawn> | null = null;
let bridgeReady = false;
/** Bearer token shared with the desktop-spawned bridge when auth is enabled. */
let bridgeToken: string | null = null;

function bridgeLoopbackInsecure(): boolean {
  return process.env.MELOSVIZ_BRIDGE_INSECURE_LOOPBACK === "1";
}

function bridgeAuthEnabled(): boolean {
  return !bridgeLoopbackInsecure();
}

function mintBridgeToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let hex = "";
  for (const b of bytes) hex += b.toString(16).padStart(2, "0");
  return hex;
}

function bridgeAuthHeaders(): Record<string, string> {
  if (!bridgeAuthEnabled() || !bridgeToken) return {};
  return { authorization: `Bearer ${bridgeToken}` };
}

// ---------------------------------------------------------------------------
// Python resolver — prefer the bundled uv venv over system python3.
//
// The postBuild hook (scripts/postBuild.ts) creates <backend>/.venv with
// melosviz[analysis,bridge] installed.  We use that interpreter so librosa,
// numpy, fastapi, uvicorn etc. are always available regardless of what is
// (or isn't) on the user's PATH.
// ---------------------------------------------------------------------------

function resolvePython(resolvedBackendDir: string): string {
  // macOS / Linux
  const venvPython = path.join(resolvedBackendDir, ".venv", "bin", "python3");
  if (fs.existsSync(venvPython)) return venvPython;
  // Windows
  const venvPythonWin = path.join(
    resolvedBackendDir,
    ".venv",
    "Scripts",
    "python.exe"
  );
  if (fs.existsSync(venvPythonWin)) return venvPythonWin;
  // Fallback: system python — will fail with a clear error if deps are missing
  const sys =
    Bun.which("python3") ?? Bun.which("python") ?? "python3";
  console.warn(
    `[MelosViz] Bundled .venv not found in ${resolvedBackendDir}; ` +
      `falling back to system python: ${sys}. ` +
      "If you see ModuleNotFoundError, re-run `bunx electrobun build` to populate the venv."
  );
  return sys;
}

// ---------------------------------------------------------------------------
// Backend sidecar helpers
// ---------------------------------------------------------------------------

function resolveBackendDir(): string | null {
  const candidates = [
    path.join(import.meta.dir, "..", "backend"),
    path.join(import.meta.dir, "backend"),
    path.join(process.cwd(), "..", "backend"),
    path.join(process.cwd(), "backend"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(path.join(c, "pyproject.toml"))) return c;
  }
  // Backend is optional — return null so the UI can fall back to CLI or show
  // a "backend offline" state rather than crashing before the window opens.
  console.warn(
    `[MelosViz] Cannot find backend directory. Searched:\n  ${candidates.join("\n  ")}`
  );
  return null;
}

async function findFreePort(): Promise<number> {
  const { createServer } = await import("net");
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address();
      if (!addr || typeof addr === "string") {
        reject(new Error("[MelosViz] Unexpected address type from TCP server"));
        return;
      }
      const port = addr.port;
      srv.close(() => resolve(port));
    });
    srv.on("error", reject);
  });
}

// ---------------------------------------------------------------------------
// Helpers — used by RPC handlers; tolerate bridgeReady=false gracefully
// ---------------------------------------------------------------------------

async function runVizCli(args: string[]): Promise<string> {
  if (!backendDir) {
    throw new Error(
      "[MelosViz] Backend not found — cannot run CLI. Drop a WAV file after installing the backend."
    );
  }
  const python = resolvePython(backendDir);
  const proc = Bun.spawn(
    [python, "-m", "melosviz.cli.main", ...args],
    {
      cwd: backendDir,
      env: { ...process.env, PYTHONPATH: path.join(backendDir, "src") },
    }
  );
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ]);
  if (exitCode !== 0) {
    throw new Error(`viz ${args[0]} failed (exit ${exitCode}): ${stderr}`);
  }
  return stdout;
}

/** W3C traceparent: `version-trace_id-span_id-flags` (sampled). */
function generateTraceparent(): string {
  const bytes = new Uint8Array(24); // 16-byte trace_id + 8-byte span_id
  crypto.getRandomValues(bytes);
  let hex = "";
  for (const b of bytes) hex += b.toString(16).padStart(2, "0");
  return `00-${hex.slice(0, 32)}-${hex.slice(32, 48)}-01`;
}

const TRACEPARENT_RE =
  /^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$/i;

/** Forward a valid inbound traceparent; otherwise mint a new one. */
function resolveTraceparent(existing?: string | null): string {
  if (existing && TRACEPARENT_RE.test(existing.trim())) {
    return existing.trim();
  }
  return generateTraceparent();
}

async function bridgeFetch(
  endpoint: string,
  body: Record<string, string>,
  init?: { headers?: Record<string, string> }
): Promise<string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...bridgeAuthHeaders(),
    ...(init?.headers ?? {}),
  };
  const inbound =
    headers.traceparent ?? headers.Traceparent ?? headers["TRACEPARENT"];
  delete headers.Traceparent;
  delete headers["TRACEPARENT"];
  headers.traceparent = resolveTraceparent(inbound);

  const res = await fetch(`http://127.0.0.1:${backendPort}${endpoint}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(
      `Bridge ${endpoint} failed (${res.status}): ${await res.text()}`
    );
  }
  return res.text();
}

// ---------------------------------------------------------------------------
// RPC setup (bun side)
// ---------------------------------------------------------------------------

const rpc = defineElectrobunRPC<
  { bun: BunRequests; webview: WebviewRequests }
>("bun", {
  handlers: {
    requests: {
      async analyzeWav({ wavPath }) {
        if (bridgeReady) return bridgeFetch("/analyze", { wav_path: wavPath });
        return runVizCli(["analyze", wavPath]);
      },

      async buildPlan({ wavPath, outDir }) {
        if (bridgeReady) {
          const b: Record<string, string> = { wav_path: wavPath };
          if (outDir) b.out_dir = outDir;
          return bridgeFetch("/build", b);
        }
        const args = ["build", wavPath];
        if (outDir) args.push("--out", outDir);
        return runVizCli(args);
      },

      async renderVideo({ wavPath, outDir }) {
        if (bridgeReady)
          return bridgeFetch("/render", { wav_path: wavPath, out_dir: outDir });
        return runVizCli(["render", wavPath, "--out", outDir]);
      },

      async renderWithWgpu({ renderSpec, outDir }) {
        // Write RenderSpec to a temp JSON file
        const specPath = path.join(outDir, `.melosviz-spec-${Date.now()}.json`);
        await Bun.write(specPath, renderSpec);

        // Find the melosviz-render binary (built from crates/melosviz-render-wgpu)
        const renderBinary = path.join(
          import.meta.dir,
          "..",
          "..",
          "target",
          "release",
          "melosviz-render"
        );

        if (!fs.existsSync(renderBinary)) {
          throw new Error(
            `[MelosViz] melosviz-render binary not found at ${renderBinary}. ` +
              `Run 'cargo build --release' in the crates/melosviz-render-wgpu directory.`
          );
        }

        const videoPath = path.join(outDir, `melosviz-preview-${Date.now()}.mp4`);
        const proc = Bun.spawn([renderBinary, "--spec", specPath, "--output", videoPath], {
          env: { ...process.env, RUST_LOG: "info" },
          stdout: "inherit",
          stderr: "inherit",
        });

        const exitCode = await proc.exited;
        if (exitCode !== 0) {
          throw new Error(
            `[MelosViz] melosviz-render failed (exit ${exitCode})`
          );
        }

        // Clean up temp spec file
        try {
          fs.unlinkSync(specPath);
        } catch {
          // Best effort cleanup
        }

        // Return the MP4 path so the webview can load it
        return videoPath;
      },

      async pickFile({ accept }) {
        try {
          const paths = await openFileDialog({
            allowedFileTypes: accept === "wav" ? "wav" : "*",
            canChooseFiles: true,
            canChooseDirectory: false,
            allowsMultipleSelection: false,
          });
          return paths[0] ?? null;
        } catch (err) {
          console.error("[MelosViz] pickFile dialog error:", err);
          // Always settle — return null so the webview never hangs
          return null;
        }
      },

      async pickDirectory() {
        try {
          const paths = await openFileDialog({
            canChooseFiles: false,
            canChooseDirectory: true,
            allowsMultipleSelection: false,
          });
          return paths[0] ?? null;
        } catch (err) {
          console.error("[MelosViz] pickDirectory dialog error:", err);
          return null;
        }
      },

      async revealInFinder({ filePath }) {
        showItemInFolder(filePath);
      },
    },
  },
});

// ---------------------------------------------------------------------------
// Main window — created FIRST, before any backend I/O
// ---------------------------------------------------------------------------

// Use the views:// custom scheme so WKWebView treats the context as secure —
// window.crypto.subtle (required by electrobun's RPC encryption init) is only
// available in a secure context.  The html: shorthand calls loadHTMLString
// which produces an opaque "null" origin (insecure); url: "views://..." goes
// through electrobun's registered URL scheme handler which is secure.
const win = new BrowserWindow({
  title: i18n("app.name"),
  frame: { x: 100, y: 100, width: 1280, height: 800 },
  url: "views://main/index.html",
  titleBarStyle: "hiddenInset",
  rpc,
});

console.log("[MelosViz] window created, id=", win.id);

// ---------------------------------------------------------------------------
// Tray / menubar quick-actions (C11 L110) — Show window, bridge health, quit.
//
// Best-effort: Electrobun's Tray falls back to a disabled no-op object (see
// Tray.createNativeTray try/catch) on platforms/sandboxes without system-tray
// support, so this never crashes app startup — it just silently has no icon.
// ---------------------------------------------------------------------------

const TRAY_ACTION_SHOW = "melosviz.tray.show";
const TRAY_ACTION_HEALTH = "melosviz.tray.health";
const TRAY_ACTION_QUIT = "melosviz.tray.quit";

/** Bridge health URL for the currently-known port (falls back to the default). */
function bridgeHealthUrl(): string {
  return `http://127.0.0.1:${backendPort || 8765}/health`;
}

function setupTray(): void {
  try {
    const tray = new Tray({ title: i18n("app.name"), template: true });
    tray.setMenu([
      {
        type: "normal",
        label: i18n("tray.show", "Show MelosViz"),
        action: TRAY_ACTION_SHOW,
      },
      {
        type: "normal",
        label: i18n("tray.health", "Open Bridge Health"),
        action: TRAY_ACTION_HEALTH,
      },
      { type: "divider" },
      {
        type: "normal",
        label: i18n("tray.quit", "Quit"),
        action: TRAY_ACTION_QUIT,
      },
    ]);
    tray.on("tray-clicked", (event) => {
      const action = (event as { data?: { action?: string } } | undefined)
        ?.data?.action;
      switch (action) {
        case TRAY_ACTION_SHOW:
          if (win.isMinimized()) win.unminimize();
          win.show();
          break;
        case TRAY_ACTION_HEALTH:
          Utils.openExternal(bridgeHealthUrl());
          break;
        case TRAY_ACTION_QUIT:
          Utils.quit();
          break;
        default:
          break; // clicking the tray icon itself (no menu action) — no-op
      }
    });
  } catch (err) {
    console.warn(
      "[MelosViz] Tray setup skipped (unsupported platform?):",
      err
    );
  }
}

setupTray();

// ---------------------------------------------------------------------------
// Backend bridge — starts AFTER the window is open (non-blocking)
// ---------------------------------------------------------------------------

async function startBackendBridge(): Promise<void> {
  backendDir = resolveBackendDir();
  if (!backendDir) {
    console.warn("[MelosViz] No backend found; UI running in offline mode");
    return;
  }

  try {
    backendPort = await findFreePort();
  } catch (err) {
    console.error("[MelosViz] Could not allocate a free port:", err);
    return;
  }

  console.log(`[MelosViz] backend dir  : ${backendDir}`);
  console.log(`[MelosViz] bridge port  : ${backendPort}`);

  const bridgeScript = path.join(
    backendDir,
    "src",
    "melosviz",
    "bridge",
    "server.py"
  );

  if (!fs.existsSync(bridgeScript)) {
    console.warn(
      `[MelosViz] bridge not found at ${bridgeScript}; using CLI subprocess fallback`
    );
    return;
  }

  const python = resolvePython(backendDir);
  console.log(`[MelosViz] python        : ${python}`);

  const bridgeEnv: Record<string, string> = {
    ...process.env,
    MELOSVIZ_BACKEND_PORT: String(backendPort),
    PYTHONPATH: path.join(backendDir, "src"),
  };
  if (bridgeAuthEnabled()) {
    bridgeToken = mintBridgeToken();
    bridgeEnv.MELOSVIZ_BRIDGE_REQUIRE_AUTH = "1";
    bridgeEnv.MELOSVIZ_BRIDGE_TOKEN = bridgeToken;
    console.log("[MelosViz] bridge auth   : enabled (desktop-spawned token)");
  } else {
    bridgeToken = null;
    console.log(
      "[MelosViz] bridge auth   : legacy loopback (MELOSVIZ_BRIDGE_INSECURE_LOOPBACK=1)"
    );
  }

  bridgeProc = Bun.spawn(
    [python, bridgeScript, "--port", String(backendPort)],
    {
      cwd: backendDir,
      env: bridgeEnv,
      stdout: "inherit",
      stderr: "inherit",
    }
  );
  console.log(`[MelosViz] bridge pid   : ${bridgeProc.pid}`);

  // Give the bridge up to 5 s to become ready (non-blocking — window is already open)
  for (let i = 0; i < 10; i++) {
    await Bun.sleep(500);
    try {
      const r = await fetch(`http://127.0.0.1:${backendPort}/health`, {
        headers: {
          traceparent: generateTraceparent(),
          ...bridgeAuthHeaders(),
        },
      });
      if (r.ok) {
        bridgeReady = true;
        console.log("[MelosViz] bridge ready");
        break;
      }
    } catch {
      // not yet up — keep polling
    }
  }
  if (!bridgeReady) {
    console.warn("[MelosViz] bridge did not respond in 5 s; falling back to CLI");
  }
}

// Fire and forget — window is already visible while this runs
startBackendBridge().catch((err) => {
  console.error("[MelosViz] Backend bridge startup error:", err);
});

// ---------------------------------------------------------------------------
// Auto-update — best-effort check after UI is up (stable/canary channels only)
// ---------------------------------------------------------------------------

async function checkForAppUpdate(): Promise<void> {
  try {
    const info = await Updater.checkForUpdate();
    if (info?.updateAvailable) {
      console.log(
        `[MelosViz] update available: version=${info.version} hash=${info.hash}`
      );
      // Download in background; Electrobun applies on next restart when ready.
      try {
        await Updater.downloadUpdate();
        console.log("[MelosViz] update downloaded; will apply on restart");
      } catch (dlErr) {
        console.warn("[MelosViz] update download skipped:", dlErr);
      }
    } else {
      console.log(
        `[MelosViz] updater: no update (channel check ok; ready=${Boolean(info?.updateReady)})`
      );
    }
  } catch (err) {
    // Dev channel and missing manifests are expected locally.
    console.warn("[MelosViz] updater check skipped:", err);
  }
}

checkForAppUpdate().catch((err) => {
  console.warn("[MelosViz] updater startup error:", err);
});

process.on("exit", () => bridgeProc?.kill());
