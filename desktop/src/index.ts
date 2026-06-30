/**
 * MelosViz desktop app — Electrobun main process (bun side).
 *
 * Responsibilities:
 *  1. Open the main BrowserWindow immediately on startup
 *  2. Locate the bundled Python backend sidecar (non-blocking)
 *  3. Spawn the FastAPI HTTP bridge on a free port asynchronously
 *     — the UI renders immediately; backend connects in the background
 */

import { BrowserWindow, defineElectrobunRPC, Utils } from "electrobun/bun";
const { openFileDialog, showItemInFolder } = Utils;
import * as path from "path";
import * as fs from "fs";
import type { BunRequests, WebviewRequests } from "./rpc";

// ---------------------------------------------------------------------------
// Backend sidecar state — populated asynchronously after window opens
// ---------------------------------------------------------------------------

let backendDir: string | null = null;
let backendPort: number = 0;
let bridgeProc: ReturnType<typeof Bun.spawn> | null = null;
let bridgeReady = false;

const python = Bun.which("python3") ?? Bun.which("python") ?? "python3";

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

async function bridgeFetch(
  endpoint: string,
  body: Record<string, string>
): Promise<string> {
  const res = await fetch(`http://127.0.0.1:${backendPort}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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

      async pickFile({ accept }) {
        const paths = await openFileDialog({
          allowedFileTypes: accept === "wav" ? "wav" : "*",
          canChooseFiles: true,
          canChooseDirectory: false,
          allowsMultipleSelection: false,
        });
        return paths[0] ?? null;
      },

      async pickDirectory() {
        const paths = await openFileDialog({
          canChooseFiles: false,
          canChooseDirectory: true,
          allowsMultipleSelection: false,
        });
        return paths[0] ?? null;
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
  title: "MelosViz",
  frame: { x: 100, y: 100, width: 1280, height: 800 },
  url: "views://main/index.html",
  titleBarStyle: "hiddenInset",
  rpc,
});

console.log("[MelosViz] window created, id=", win.id);

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

  bridgeProc = Bun.spawn(
    [python, bridgeScript, "--port", String(backendPort)],
    {
      cwd: backendDir,
      env: {
        ...process.env,
        MELOSVIZ_BACKEND_PORT: String(backendPort),
        PYTHONPATH: path.join(backendDir, "src"),
      },
      stdout: "inherit",
      stderr: "inherit",
    }
  );
  console.log(`[MelosViz] bridge pid   : ${bridgeProc.pid}`);

  // Give the bridge up to 5 s to become ready (non-blocking — window is already open)
  for (let i = 0; i < 10; i++) {
    await Bun.sleep(500);
    try {
      const r = await fetch(`http://127.0.0.1:${backendPort}/health`);
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

process.on("exit", () => bridgeProc?.kill());
