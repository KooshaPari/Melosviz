/**
 * MelosViz postBuild hook — bundle a uv venv with all backend deps.
 *
 * Electrobun calls this with Bun after the main build completes and all
 * copy entries have been placed.  Env vars available:
 *   ELECTROBUN_BUILD_DIR  — e.g. "build/dev-macos-arm64"
 *   ELECTROBUN_APP_NAME   — e.g. "MelosViz-dev.app" (macOS) or "MelosViz-dev" (win/linux)
 *   ELECTROBUN_OS         — "macos" | "windows" | "linux"
 *
 * What we do:
 *   1. Locate the bundled backend directory inside the built .app bundle.
 *   2. Create a uv virtualenv (python 3.14 → 3.12 → 3.10 fallback chain).
 *   3. Install the backend package with [analysis,bridge] extras so librosa,
 *      numpy, fastapi, uvicorn etc. are all present at runtime.
 *
 * The venv lives at <backend>/.venv.  index.ts resolves python as
 * <backendDir>/.venv/bin/python3 (mac/linux) or .venv/Scripts/python.exe (win)
 * before falling back to system python3.
 */

import * as path from "path";
import * as fs from "fs";

const buildDir = process.env.ELECTROBUN_BUILD_DIR ?? "build";
const appName = process.env.ELECTROBUN_APP_NAME ?? "MelosViz-dev.app";
const os = process.env.ELECTROBUN_OS ?? "macos";

// Resolve the backend dir inside the built bundle.
// On macOS electrobun passes ELECTROBUN_APP_NAME without the .app suffix
// (e.g. "MelosViz-dev"), but the bundle directory is "MelosViz-dev.app".
const macAppBundleName =
  os === "macos" && !appName.endsWith(".app") ? appName + ".app" : appName;

const appResourcesPath =
  os === "macos"
    ? path.join(buildDir, macAppBundleName, "Contents", "Resources", "app", "backend")
    : path.join(buildDir, appName, "resources", "app", "backend");

const backendAbsPath = path.isAbsolute(appResourcesPath)
  ? appResourcesPath
  : path.join(process.cwd(), appResourcesPath);

if (!fs.existsSync(path.join(backendAbsPath, "pyproject.toml"))) {
  console.error(
    `[postBuild] Backend not found at ${backendAbsPath} — skipping venv creation.`
  );
  process.exit(0);
}

console.log(`[postBuild] Creating bundled venv in ${backendAbsPath}/.venv`);

const uv = Bun.which("uv");
if (!uv) {
  console.error(
    "[postBuild] uv not found on PATH — cannot bundle Python venv.\n" +
      "  Install uv: https://docs.astral.sh/uv/getting-started/installation/"
  );
  // Non-fatal: app will fall back to system python3 with a clear error in the UI
  process.exit(0);
}

// Try python versions in preference order (stack pref: 3.14 first)
const pythonVersions = ["3.14", "3.13", "3.12", "3.11", "3.10"];

function run(
  cmd: string[],
  opts: { cwd?: string; env?: Record<string, string> } = {}
): { ok: boolean; stderr: string } {
  const result = Bun.spawnSync(cmd, {
    cwd: opts.cwd ?? backendAbsPath,
    env: { ...process.env, ...(opts.env ?? {}) },
    stdio: ["ignore", "inherit", "pipe"],
  });
  const stderr = result.stderr
    ? new TextDecoder().decode(result.stderr)
    : "";
  return { ok: result.exitCode === 0, stderr };
}

// 1. Create the venv, trying python versions in order
let venvCreated = false;
for (const pyVer of pythonVersions) {
  console.log(`[postBuild] Trying uv venv --python ${pyVer}...`);
  const r = run([uv, "venv", "--python", pyVer, ".venv"]);
  if (r.ok) {
    console.log(`[postBuild] venv created with python ${pyVer}`);
    venvCreated = true;
    break;
  }
  // "No interpreter found" or similar — try next version
  if (r.stderr.includes("No interpreter found") || r.stderr.includes("not found")) {
    console.warn(`[postBuild] python ${pyVer} not available, trying next...`);
    continue;
  }
  // Other error — abort
  console.error(`[postBuild] uv venv failed: ${r.stderr}`);
  process.exit(1);
}

if (!venvCreated) {
  console.error(
    "[postBuild] No suitable Python interpreter found (tried: " +
      pythonVersions.join(", ") +
      ").\n  The app will fall back to system python3 (may lack deps)."
  );
  process.exit(0);
}

// 2. Install the backend package with analysis + bridge extras
console.log("[postBuild] Installing melosviz[analysis,bridge] into .venv...");
const installResult = run([
  uv,
  "pip",
  "install",
  "--python",
  ".venv/bin/python3",
  "-e",
  ".[analysis,bridge]",
]);

if (!installResult.ok) {
  console.error(
    "[postBuild] uv pip install failed:\n" + installResult.stderr
  );
  process.exit(1);
}

console.log("[postBuild] Backend venv ready.");
