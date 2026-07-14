#!/usr/bin/env bash
# Publish @melosviz/* SDK packages to GitHub Packages (npm.pkg.github.com).
#
# Order: brand-tokens → bridge-client → ui (ui depends on brand-tokens semver).
# Invoked by .github/workflows/publish-sdk-packages.yml (workflow_dispatch or sdk-v* tag).
#
# Local dry-run (no registry write):
#   MELOSVIZ_SDK_PUBLISH_DRY_RUN=1 bash scripts/publish_sdk_packages.sh
#
# Requires: npm, NODE_AUTH_TOKEN (or npm login to npm.pkg.github.com).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v npm >/dev/null 2>&1 || { echo "publish_sdk_packages: npm not found" >&2; exit 1; }

DRY_RUN="${MELOSVIZ_SDK_PUBLISH_DRY_RUN:-}"
if [[ -z "${NODE_AUTH_TOKEN:-}" && -z "$DRY_RUN" ]]; then
  echo "publish_sdk_packages: NODE_AUTH_TOKEN required (or set MELOSVIZ_SDK_PUBLISH_DRY_RUN=1)" >&2
  exit 1
fi

publish_one() {
  local dir="$1"
  echo "==> publish ${dir#"$ROOT"/}"
  if [[ -n "$DRY_RUN" ]]; then
    (cd "$dir" && npm pack >/dev/null)
    echo "    dry-run: npm pack OK"
    return 0
  fi
  (cd "$dir" && npm publish --access public)
}

BT_DIR="$ROOT/packages/brand-tokens"
BC_DIR="$ROOT/sdk/ts"
UI_DIR="$ROOT/packages/ui"
UI_PKG_BACKUP=""

cleanup_ui_pkg() {
  if [[ -n "$UI_PKG_BACKUP" && -f "$UI_PKG_BACKUP" ]]; then
    mv -f "$UI_PKG_BACKUP" "$UI_DIR/package.json"
  fi
}
trap cleanup_ui_pkg EXIT

BT_VERSION="$(node -p "require('$BT_DIR/package.json').version")"

# Swap ui file: dependency for published semver before publish.
UI_PKG_BACKUP="$(mktemp)"
cp "$UI_DIR/package.json" "$UI_PKG_BACKUP"
node <<NODE
const fs = require("node:fs");
const path = "$UI_DIR/package.json";
const pkg = JSON.parse(fs.readFileSync(path, "utf8"));
pkg.dependencies = pkg.dependencies || {};
pkg.dependencies["@melosviz/brand-tokens"] = "^${BT_VERSION}";
fs.writeFileSync(path, JSON.stringify(pkg, null, 2) + "\n");
NODE

publish_one "$BT_DIR"
publish_one "$BC_DIR"
publish_one "$UI_DIR"

if [[ -n "$DRY_RUN" ]]; then
  echo "publish_sdk_packages: PASS (dry-run pack for brand-tokens + bridge-client + ui)"
else
  echo "publish_sdk_packages: PASS (published to https://npm.pkg.github.com)"
fi
