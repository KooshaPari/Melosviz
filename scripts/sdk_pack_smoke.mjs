#!/usr/bin/env bun
/**
 * Import smoke for npm-packed @melosviz/* tarballs installed in installDir.
 * Invoked by scripts/check_sdk_pack_smoke.sh (C11 L116 publishable-shape gate).
 *
 * Resolves packages via absolute paths under installDir/node_modules — bun does
 * not always honor process.chdir for bare @scope imports when the entry script
 * lives outside the install tree.
 */

import { existsSync } from "node:fs";
import { join, pathToFileURL } from "node:path";

const installDir = process.argv[2];
if (!installDir || !existsSync(installDir)) {
  console.error("sdk_pack_smoke: usage: bun sdk_pack_smoke.mjs <install-dir>");
  process.exit(1);
}

function pkgEntry(name, ...parts) {
  const p = join(installDir, "node_modules", name, ...parts);
  if (!existsSync(p)) {
    throw new Error(`missing package entry: ${p}`);
  }
  return pathToFileURL(p).href;
}

const { BRIDGE_PATHS, analyze } = await import(
  pkgEntry("@melosviz/bridge-client", "src", "index.ts"),
);
if (!Array.isArray(BRIDGE_PATHS) || BRIDGE_PATHS.length < 5) {
  throw new Error("bridge-client: BRIDGE_PATHS missing or too short");
}
if (typeof analyze !== "function") {
  throw new Error("bridge-client: analyze export missing");
}

const { Button, EmptyState, Skeleton } = await import(
  pkgEntry("@melosviz/ui", "src", "index.ts"),
);
for (const [name, exp] of [
  ["Button", Button],
  ["EmptyState", EmptyState],
  ["Skeleton", Skeleton],
]) {
  if (typeof exp !== "function") {
    throw new Error(`@melosviz/ui: ${name} export missing`);
  }
}

const tokensPath = join(
  installDir,
  "node_modules",
  "@melosviz",
  "brand-tokens",
  "tokens.css",
);
if (!existsSync(tokensPath)) {
  throw new Error("@melosviz/brand-tokens: tokens.css missing in install tree");
}

console.log(
  JSON.stringify({
    ok: true,
    bridge_paths: BRIDGE_PATHS.length,
    ui_exports: ["Button", "EmptyState", "Skeleton"],
    brand_tokens: tokensPath,
  }),
);
