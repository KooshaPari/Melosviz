#!/usr/bin/env node
/**
 * Pixel-diff a fresh screenshot against a committed baseline.
 *
 * Usage (from repo root after `npm ci` in scripts/visual-gate):
 *   node scripts/visual-gate/compare.mjs <baseline> <actual> [diff] [maxDiffRatio]
 *
 * UPDATE_SCREENSHOT_BASELINE=1 copies actual → baseline.
 */
import fs from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const [baselinePath, actualPath, diffPath = "diff.png", maxRatioArg] =
  process.argv.slice(2);
if (!baselinePath || !actualPath) {
  console.error(
    "usage: compare.mjs <baseline> <actual> [diff] [maxDiffRatio]",
  );
  process.exit(2);
}

const maxDiffRatio = Number(maxRatioArg ?? "0.002");

if (process.env.UPDATE_SCREENSHOT_BASELINE === "1") {
  fs.mkdirSync(path.dirname(baselinePath), { recursive: true });
  fs.copyFileSync(actualPath, baselinePath);
  console.log(`updated baseline: ${baselinePath}`);
  process.exit(0);
}

if (!fs.existsSync(baselinePath)) {
  console.error(`missing baseline: ${baselinePath}`);
  process.exit(1);
}

const baseline = PNG.sync.read(fs.readFileSync(baselinePath));
const actual = PNG.sync.read(fs.readFileSync(actualPath));

if (baseline.width !== actual.width || baseline.height !== actual.height) {
  console.error(
    `size mismatch: baseline ${baseline.width}x${baseline.height} vs actual ${actual.width}x${actual.height}`,
  );
  process.exit(1);
}

const { width, height } = baseline;
const diff = new PNG({ width, height });
const mismatched = pixelmatch(
  baseline.data,
  actual.data,
  diff.data,
  width,
  height,
  { threshold: 0.1 },
);
const total = width * height;
const ratio = mismatched / total;

fs.mkdirSync(path.dirname(diffPath), { recursive: true });
fs.writeFileSync(diffPath, PNG.sync.write(diff));

console.log(
  `pixelmatch: ${mismatched}/${total} (${(ratio * 100).toFixed(3)}%) vs max ${(maxDiffRatio * 100).toFixed(3)}%`,
);

if (ratio > maxDiffRatio) {
  console.error(`FAIL: visual regression exceeds threshold → ${diffPath}`);
  process.exit(1);
}

console.log("PASS: within threshold");
