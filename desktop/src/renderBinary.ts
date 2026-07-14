/**
 * Resolve the melosviz-render CLI binary for desktop wgpu preview.
 *
 * Kept free of Electrobun imports so unit tests can import it directly.
 */

import * as fs from "fs";
import * as path from "path";

const BINARY_STEM = "melosviz-render";

const CARGO_OUTPUT_DIRS = [
  path.join("target", "release"),
  path.join("target", "debug"),
  path.join("crates", "melosviz-render-wgpu", "target", "release"),
  path.join("crates", "melosviz-render-wgpu", "target", "debug"),
] as const;

/** File name of the render binary on the current platform (`melosviz-render` or `.exe`). */
export function melosvizRenderBinaryName(platform: NodeJS.Platform = process.platform): string {
  return platform === "win32" ? `${BINARY_STEM}.exe` : BINARY_STEM;
}

/** Cargo output paths under a repo root (release before debug; workspace before crate). */
export function melosvizRenderCandidatePaths(
  repoRoot: string,
  platform: NodeJS.Platform = process.platform,
): string[] {
  const name = melosvizRenderBinaryName(platform);
  return CARGO_OUTPUT_DIRS.map((relDir) => path.join(repoRoot, relDir, name));
}

/** Ordered repo roots to search (first existing candidate wins). */
export function melosvizRenderSearchRoots(
  searchFrom: string,
  cwd: string = process.cwd(),
): string[] {
  const roots: string[] = [];
  const push = (root: string | null | undefined) => {
    if (!root) return;
    const resolved = path.resolve(root);
    if (!roots.includes(resolved)) roots.push(resolved);
  };

  push(findRepoRoot(searchFrom));
  push(findRepoRoot(cwd));
  push(path.resolve(searchFrom, "..", ".."));
  push(cwd);
  push(path.resolve(cwd, ".."));
  push(path.resolve(searchFrom, ".."));

  return roots;
}

/** Walk upward from *startDir* until a workspace `Cargo.toml` is found. */
export function findRepoRoot(startDir: string): string | null {
  let current = path.resolve(startDir);
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(path.join(current, "Cargo.toml"))) return current;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return null;
}

function isReadableFile(filePath: string): boolean {
  try {
    return fs.statSync(filePath).isFile();
  } catch {
    return false;
  }
}

export type ResolveMelosvizRenderBinaryOptions = {
  /** Directory to start repo-root discovery (defaults to `import.meta.dir`). */
  searchFrom?: string;
  /** Working directory for additional search roots (defaults to `process.cwd()`). */
  cwd?: string;
  /** Extra directories that may contain a bundled copy of the binary. */
  bundledDirs?: string[];
};

/**
 * Return the path to an existing melosviz-render binary, or null if none found.
 *
 * Lookup order:
 *  1. `MELOSVIZ_RENDER_BIN` when set and the file exists
 *  2. `PATH` via `Bun.which`
 *  3. Cargo `target/release` and `target/debug` under each search root, including
 *     `crates/melosviz-render-wgpu/target/*`
 *  4. Bundled copies next to the desktop package or app executable
 */
export function resolveMelosvizRenderBinary(
  options: ResolveMelosvizRenderBinaryOptions = {},
): string | null {
  const name = melosvizRenderBinaryName();

  const envBin = process.env.MELOSVIZ_RENDER_BIN;
  if (envBin && isReadableFile(envBin)) return envBin;

  const onPath = Bun.which(name) ?? Bun.which(BINARY_STEM);
  if (onPath && isReadableFile(onPath)) return onPath;

  const searchFrom =
    options.searchFrom ??
    (typeof import.meta !== "undefined" && import.meta.dir
      ? import.meta.dir
      : process.cwd());
  const cwd = options.cwd ?? process.cwd();

  const candidates: string[] = [];
  for (const root of melosvizRenderSearchRoots(searchFrom, cwd)) {
    candidates.push(...melosvizRenderCandidatePaths(root));
  }

  // Honor CARGO_TARGET_DIR (e.g. shared caches outside the repo).
  const cargoTarget = process.env.CARGO_TARGET_DIR;
  if (cargoTarget) {
    candidates.push(
      path.join(cargoTarget, "release", name),
      path.join(cargoTarget, "debug", name),
    );
  }

  const bundledDirs = options.bundledDirs ?? [
    path.join(searchFrom, ".."),
    path.dirname(process.execPath),
  ];
  for (const dir of bundledDirs) {
    candidates.push(path.join(dir, name));
  }

  for (const candidate of candidates) {
    if (isReadableFile(candidate)) return candidate;
  }
  return null;
}

/** Hint text when binary resolution fails (for thrown Error messages). */
export function formatMelosvizRenderSearchHint(
  searchFrom: string = import.meta.dir,
  cwd: string = process.cwd(),
): string {
  const preview = melosvizRenderSearchRoots(searchFrom, cwd)
    .flatMap((root) => melosvizRenderCandidatePaths(root))
    .slice(0, 4)
    .join(", ");
  return (
    `Checked: ${preview}${preview ? ", …" : ""}. ` +
    "Build with: cargo build -p melosviz-render-wgpu --release " +
    "or set MELOSVIZ_RENDER_BIN to the binary path."
  );
}

/** Truncate long stderr for error messages shown in the webview console. */
export function truncateStderr(stderr: string, maxLen = 500): string {
  const trimmed = stderr.trim().replace(/\s+/g, " ");
  if (trimmed.length <= maxLen) return trimmed;
  return `${trimmed.slice(0, maxLen)}…`;
}

/** argv for `melosviz-render render-mp4` (clap subcommand). */
export function melosvizRenderMp4Argv(
  binary: string,
  specPath: string,
  outputPath: string,
): string[] {
  return [binary, "render-mp4", "--spec", specPath, "--output", outputPath];
}
