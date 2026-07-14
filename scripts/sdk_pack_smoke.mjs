#!/usr/bin/env bun
/**
 * Import smoke for npm-packed @melosviz/* tarballs installed in installDir.
 * Invoked by scripts/check_sdk_pack_smoke.sh (C11 L116 publishable-shape gate).
 */

import { existsSync } from "node:fs";
import { join } from "node:path";

const installDir = process.argv[2];
if (!installDir || !existsSync(installDir)) {
  console.error("sdk_pack_smoke: usage: bun sdk_pack_smoke.mjs <install-dir>");
  process.exit(1);
}

process.chdir(installDir);

const { BRIDGE_PATHS, analyze } = await import("@melosviz/bridge-client");
if (!Array.isArray(BRIDGE_PATHS) || BRIDGE_PATHS.length < 5) {
  throw new Error("bridge-client: BRIDGE_PATHS missing or too short");
}
if (typeof analyze !== "function") {
  throw new Error("bridge-client: analyze export missing");
}

const { Button, EmptyState, Skeleton } = await import("@melosviz/ui");
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
