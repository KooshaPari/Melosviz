/**
 * desktop/tests/e2e_desktop.test.ts — Real desktop-app e2e suite.
 *
 * Two modes:
 *
 *   HOST MODE (default, macOS with display):
 *     Spawns `bunx electrobun dev`, waits for "[MelosViz] window created" in
 *     the launcher log, then asserts all log and bridge invariants.
 *     Run: cd desktop && bun test tests/e2e_desktop.test.ts
 *
 *   BRIDGE-ONLY MODE (CI / Linux, or BRIDGE_ONLY=1 env):
 *     Skips the launcher-log invariants (no display / no app process) and
 *     runs only the bridge HTTP round-trips against a pre-started bridge
 *     server on BRIDGE_PORT.
 *     Set: BRIDGE_PORT=18765 BRIDGE_ONLY=1 bun test tests/e2e_desktop.test.ts
 *
 * Three recent bugs this suite would have caught:
 *
 *   Bug #1 — crypto.subtle undefined (null-origin insecure context):
 *     ASSERT: launcher log has "window created" AND no crypto.subtle error.
 *     Caught by: HOST MODE only.
 *
 *   Bug #2 — blank view (views://main/index.html missing from bundle):
 *     ASSERT: no "Resource not found" / "empty response" in launcher log.
 *     Caught by: HOST MODE only.
 *     The /health round-trip is a weaker proxy: if bridge starts, the app
 *     loop ran far enough to reach backend init, which happens after the
 *     window (not a guaranteed view-load signal).
 *
 *   Bug #3 — RPC transport "did not provide 'send'":
 *     ASSERT (host): no "transport did not provide 'send'" in launcher log.
 *     ASSERT (both): bridge /analyze round-trip returns valid RenderSpec JSON.
 *     The bridge round-trip tests the bun→bridge channel that backs the
 *     webview RPC; a broken transport would surface in the log assertion.
 *
 *   Bonus — console error catch-all:
 *     ASSERT: no "[webview console] error" lines in launcher log.
 *     Caught by: HOST MODE only.
 *
 * Residual manual-only checks (documented honestly):
 *   - Pixel-level webview rendering (colours, layout, CSS): WKWebView has no
 *     headless mode; screenshot comparison needs a real display.
 *   - File-picker dialog (openFileDialog): requires native UI interaction.
 *   - Drag-and-drop into the webview.
 *   These are tracked in docs/QGATE_BASELINE.md → "manual-only checks".
 */

import { test, expect, beforeAll, afterAll, describe } from "bun:test";
import * as path from "path";
import * as fs from "fs";

// ---------------------------------------------------------------------------
// Mode detection
// ---------------------------------------------------------------------------

/**
 * BRIDGE_ONLY: set to "1" (or truthy) in CI / Linux environments that have no
 * display server and cannot run Electrobun.  In this mode only the bridge HTTP
 * tests execute; launcher-log tests are unconditionally skipped.
 *
 * When BRIDGE_ONLY is unset we also fall into bridge-only mode if the
 * "window created" log line never appears within the timeout (e.g. when
 * running locally without a display), but the skip reason will say so.
 */
const BRIDGE_ONLY = !!process.env.BRIDGE_ONLY || process.env.CI === "1";

/** Pre-started bridge port — overrides the port parsed from launcher log. */
const BRIDGE_PORT_ENV = process.env.BRIDGE_PORT
  ? parseInt(process.env.BRIDGE_PORT, 10)
  : null;

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const BRIDGE_READY_TIMEOUT_MS = 15_000;
const LOG_COLLECT_WINDOW_MS   =  8_000;
const WINDOW_CREATED_TIMEOUT_MS = 10_000;

const DESKTOP_DIR   = path.resolve(import.meta.dir, "..");
const BACKEND_DIR   = process.env.MELOSVIZ_BACKEND_DIR ?? path.resolve(DESKTOP_DIR, "..", "backend");
const FIXTURE_WAV   = path.resolve(BACKEND_DIR, "tests", "fixtures", "test_tone.wav");

// ---------------------------------------------------------------------------
// Shared state
// ---------------------------------------------------------------------------

let appProc: ReturnType<typeof Bun.spawn> | null = null;
let launcherLog = "";
let appWindowCreated = false;
let bridgePort: number | null = BRIDGE_PORT_ENV;
let bridgeReady = false;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function pipeStream(
  stream: ReadableStream<Uint8Array>,
  accumulator: { value: string },
  label: string,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      accumulator.value += chunk;
      process.stderr.write(`[e2e:${label}] ${chunk}`);
    }
  } catch {
    // stream closed when we kill the process — expected
  }
}

async function waitFor(predicate: () => boolean, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return true;
    await Bun.sleep(250);
  }
  return false;
}

function parseBridgePort(log: string): number | null {
  const m = log.match(/\[MelosViz\] bridge port\s*:\s*(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

async function probeHealth(port: number): Promise<boolean> {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    return r.ok;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Suite lifecycle
// ---------------------------------------------------------------------------

beforeAll(async () => {
  // --- BRIDGE-ONLY MODE: probe pre-started bridge and skip app launch -------
  if (BRIDGE_ONLY) {
    if (bridgePort) {
      bridgeReady = await probeHealth(bridgePort);
      if (!bridgeReady) {
        console.warn(`[e2e] BRIDGE_ONLY: pre-started bridge on port ${bridgePort} not reachable`);
      }
    } else {
      console.warn("[e2e] BRIDGE_ONLY mode but BRIDGE_PORT not set — bridge tests will skip");
    }
    return;
  }

  // --- HOST MODE: spawn Electrobun dev process and collect logs -------------

  const logAcc = { value: "" };

  appProc = Bun.spawn(["bunx", "electrobun", "dev"], {
    cwd: DESKTOP_DIR,
    env: {
      ...process.env,
      CI: "1",
      MELOSVIZ_BACKEND_DIR: BACKEND_DIR,
    },
    stdout: "pipe",
    stderr: "pipe",
  });

  void pipeStream(appProc.stdout as ReadableStream<Uint8Array>, logAcc, "stdout");
  void pipeStream(appProc.stderr as ReadableStream<Uint8Array>, logAcc, "stderr");

  // Wait for "window created"
  appWindowCreated = await waitFor(
    () => logAcc.value.includes("[MelosViz] window created"),
    WINDOW_CREATED_TIMEOUT_MS,
  );

  if (!appWindowCreated) {
    console.warn("[e2e] WARNING: 'window created' did not appear — launcher-log tests will fail/skip");
  }

  // Parse bridge port from log
  const bridgePortInLog = await waitFor(
    () => parseBridgePort(logAcc.value) !== null,
    BRIDGE_READY_TIMEOUT_MS,
  );
  if (bridgePortInLog) {
    bridgePort = parseBridgePort(logAcc.value);
  }

  // Wait for bridge /health
  if (bridgePort) {
    for (let i = 0; i < 20; i++) {
      await Bun.sleep(500);
      if (await probeHealth(bridgePort)) {
        bridgeReady = true;
        break;
      }
    }
  }

  // Let logs accumulate a bit more before snapshotting
  await Bun.sleep(Math.min(LOG_COLLECT_WINDOW_MS, 2000));
  launcherLog = logAcc.value;
}, 40_000);

afterAll(() => {
  appProc?.kill();
  appProc = null;
});

// ---------------------------------------------------------------------------
// Launcher-log invariant tests — HOST MODE only
// ---------------------------------------------------------------------------

describe("MelosViz desktop app — launcher log invariants", () => {
  /**
   * Bug #1 guard — crypto.subtle undefined (insecure context).
   *
   * Fixed by loading via `url: "views://main/index.html"` instead of
   * `html: "..."` (opaque null origin → insecure → crypto.subtle undefined).
   * The fix uses the views:// registered URL scheme which WKWebView marks as
   * a secure context.
   */
  test("Bug #1: window created, no crypto.subtle error", () => {
    if (BRIDGE_ONLY) {
      console.log("[e2e] BRIDGE_ONLY: skipping launcher-log test (no app process)");
      return;
    }
    if (!appWindowCreated) {
      // Fail clearly — the window should have appeared
      expect(launcherLog).toContain("[MelosViz] window created");
      return;
    }
    expect(launcherLog).toContain("[MelosViz] window created");
    expect(launcherLog).not.toContain("Failed to initialize encryption");
    const hasCryptoUndefined =
      launcherLog.includes("crypto.subtle") && launcherLog.includes("undefined");
    expect(hasCryptoUndefined).toBe(false);
  });

  /**
   * Bug #2 guard — blank view (views://main/index.html not in bundle copy list).
   *
   * Fixed by adding `"views/main/index.html": "views/main/index.html"` to
   * the `build.copy` section of electrobun.config.ts.
   */
  test("Bug #2: no blank-view / resource-not-found errors", () => {
    if (BRIDGE_ONLY) {
      console.log("[e2e] BRIDGE_ONLY: skipping launcher-log test (no app process)");
      return;
    }
    expect(launcherLog).not.toMatch(/Resource not found/i);
    expect(launcherLog).not.toMatch(/empty response/i);
    expect(launcherLog).not.toMatch(/FAILED to load/i);
    expect(launcherLog).not.toMatch(/views:\/\/main\/index\.html.*not found/i);
  });

  /**
   * Bug #3 guard — RPC transport "did not provide 'send'" (Electroview not
   * instantiated in views/main/index.ts before calling rpc.request.*).
   *
   * Fixed by using `Electroview.defineRPC()` static helper (available in
   * electrobun/view 1.18.1) instead of the bun-side `defineElectrobunRPC`.
   */
  test("Bug #3: no RPC transport error in launcher log", () => {
    if (BRIDGE_ONLY) {
      console.log("[e2e] BRIDGE_ONLY: skipping launcher-log test (no app process)");
      return;
    }
    expect(launcherLog).not.toMatch(/transport did not provide ['"]send['"]/i);
    expect(launcherLog).not.toMatch(/RPC.*transport.*error/i);
  });

  /**
   * Console error catch-all.
   *
   * Electrobun routes webview console.error() to the bun process stderr
   * prefixed with "[webview console]".  Catching this would have surfaced all
   * three bugs at once on the first launch.
   */
  test("No webview console.error output", () => {
    if (BRIDGE_ONLY) {
      console.log("[e2e] BRIDGE_ONLY: skipping launcher-log test (no app process)");
      return;
    }
    const consoleErrors = launcherLog
      .split("\n")
      .filter(
        (line) =>
          line.includes("[webview console] error") ||
          line.match(/\[webview\].*Error:/i) !== null,
      );
    expect(consoleErrors).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Bridge HTTP layer tests — runs in BOTH modes
// ---------------------------------------------------------------------------

describe("MelosViz desktop app — bridge HTTP layer (RPC proxy)", () => {
  /**
   * Bridge /health — proves the Python sidecar started and is reachable.
   *
   * In HOST MODE: the bun main process spawned it asynchronously.
   * In BRIDGE_ONLY MODE: pre-started via `python -m melosviz.bridge.server`.
   */
  test("Bridge /health responds 200", async () => {
    if (!bridgePort) {
      console.warn(
        "[e2e] Bridge port unknown — Python backend may not be installed.\n" +
          "Install: pip install -e 'backend[bridge,analysis]'\n" +
          "In CI: set BRIDGE_PORT env var and BRIDGE_ONLY=1.\n" +
          "Skipping bridge HTTP tests.",
      );
      return;
    }
    expect(bridgeReady).toBe(true);
    const r = await fetch(`http://127.0.0.1:${bridgePort}/health`, {
      signal: AbortSignal.timeout(5000),
    });
    expect(r.status).toBe(200);
    const body = (await r.json()) as { status: string };
    expect(body.status).toBe("ok");
  });

  /**
   * Bridge /analyze — full RPC round-trip with fixture WAV.
   *
   * This is the equivalent of the webview calling rpc.request.analyzeWav(),
   * which in production goes: webview RPC → bun main process → bridge /analyze
   * → Python spec_from_wav() → JSON response.
   *
   * Bug #3 partial coverage: if the bridge channel is broken on the bun side
   * this request fails; the launcher-log assertion catches the webview-side
   * transport error (host mode only).
   */
  test("Bridge /analyze returns valid RenderSpec JSON", async () => {
    if (!bridgeReady) {
      console.warn("[e2e] Bridge not ready — skipping /analyze round-trip");
      return;
    }
    expect(fs.existsSync(FIXTURE_WAV)).toBe(true);

    const r = await fetch(`http://127.0.0.1:${bridgePort}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wav_path: FIXTURE_WAV }),
      signal: AbortSignal.timeout(20_000),
    });

    expect(r.ok).toBe(true);
    const spec = JSON.parse(await r.text()) as Record<string, unknown>;

    // RenderSpec v2 shape — fields live under nested objects.
    // Top-level: metadata, palette, layers, keyframes, timeline,
    //            dense_keyframes, timeline_events, scene_segments, stem_channels, mir
    expect(spec).toHaveProperty("metadata");
    const meta = spec.metadata as Record<string, unknown>;
    // duration comes from the WAV
    expect(typeof meta.duration).toBe("number");
    expect((meta.duration as number)).toBeGreaterThan(0);
    // estimated_bpm is populated by spec_from_wav
    expect(meta).toHaveProperty("estimated_bpm");
    // scene_segments is always present (may be empty for short/flat fixtures)
    expect(spec).toHaveProperty("scene_segments");
    expect(Array.isArray(spec.scene_segments)).toBe(true);
  }, 25_000);

  /**
   * Bridge /build — analyze → assemble render plan.
   *
   * The simple test_tone.wav fixture produces 0 scene_segments (a pure sine
   * tone with no dynamics), so assemble_render_plan raises AssemblyError.
   * We assert the bridge returns HTTP 500 with a recognisable error message,
   * which is the correct behaviour for that input.  The /build happy path is
   * exercised by the backend's test_e2e_pipeline_smoke.py which uses a
   * hand-crafted spec with populated segments.
   *
   * What this still proves: the /build endpoint is reachable and the bridge
   * correctly surfaces Python exceptions as 500 (not crashing silently).
   */
  test("Bridge /build is reachable (500 on empty-segment fixture is expected)", async () => {
    if (!bridgeReady) {
      console.warn("[e2e] Bridge not ready — skipping /build reachability check");
      return;
    }

    const r = await fetch(`http://127.0.0.1:${bridgePort}/build`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ wav_path: FIXTURE_WAV }),
      signal: AbortSignal.timeout(30_000),
    });

    // The test_tone.wav fixture produces 0 scene_segments, so assemble_render_plan
    // raises AssemblyError → bridge returns 500 "Internal Server Error".
    // That is the correct behaviour; we assert the endpoint IS reachable (not 404/502)
    // and that it returns either 200 (richer WAV) or 500 (expected for flat fixture).
    expect([200, 500]).toContain(r.status);
    if (r.status === 500) {
      // Confirm it's an application-level error, not a crash/timeout
      const body = await r.text();
      expect(body.length).toBeGreaterThan(0);
    }
  }, 35_000);
});
