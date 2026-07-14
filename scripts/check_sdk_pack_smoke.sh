#!/usr/bin/env bash
# SDK pack + tarball install smoke (C11 L116 / WBS-P3.1 partial).
#
# Proves @melosviz/* packages are publishable-shape: `npm pack` succeeds,
# tarballs install into a throwaway dir, and entrypoints import cleanly.
# Does NOT publish to npm/GitHub Packages — live registry publish stays G-C11-06.
#
# Requires: npm, bun (TypeScript entrypoints; matches desktop/web toolchain).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v npm >/dev/null 2>&1 || { echo "check_sdk_pack_smoke: npm not found" >&2; exit 1; }
command -v bun >/dev/null 2>&1 || { echo "check_sdk_pack_smoke: bun not found" >&2; exit 1; }

PACK_DIR="$ROOT/dist/sdk-pack-smoke-pack-$$"
SMOKE_DIR="$ROOT/dist/sdk-pack-smoke-install-$$"
mkdir -p "$PACK_DIR" "$SMOKE_DIR"
trap 'rm -rf "$PACK_DIR" "$SMOKE_DIR"' EXIT

pack_one() {
  local dir="$1"
  echo "==> npm pack in ${dir#"$ROOT"/}"
  local tgz
  tgz="$(cd "$dir" && npm pack 2>/dev/null | tail -1)"
  mv "$dir/$tgz" "$PACK_DIR/"
}

pack_one "$ROOT/packages/brand-tokens"
pack_one "$ROOT/sdk/ts"
pack_one "$ROOT/packages/ui"

BT_TGZ="$(ls -1 "$PACK_DIR"/melosviz-brand-tokens-*.tgz | head -1)"
BC_TGZ="$(ls -1 "$PACK_DIR"/melosviz-bridge-client-*.tgz | head -1)"
UI_TGZ="$(ls -1 "$PACK_DIR"/melosviz-ui-*.tgz | head -1)"

for f in "$BT_TGZ" "$BC_TGZ" "$UI_TGZ"; do
  [[ -f "$f" ]] || { echo "check_sdk_pack_smoke: missing tarball $f" >&2; exit 1; }
done

echo "==> install tarballs into throwaway dir"
(
  cd "$SMOKE_DIR"
  npm init -y >/dev/null
  npm install "$BT_TGZ" "$BC_TGZ" "$UI_TGZ" react@19 >/dev/null
)

echo "==> entrypoint smoke (bun)"
bun "$ROOT/scripts/sdk_pack_smoke.mjs" "$SMOKE_DIR"

echo "check_sdk_pack_smoke: PASS (brand-tokens + bridge-client + ui)"
