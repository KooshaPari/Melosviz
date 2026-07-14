#!/usr/bin/env bash
# Hermetic / offline Rust build smoke (WBS-P1.6 / C06 L54).
#
# Scope (see docs/AIRGAP.md + docs/SUPPLY_CHAIN.md):
#   1) Online once: cargo fetch --locked (populate the local cargo cache)
#   2) Offline: CARGO_NET_OFFLINE=true cargo check -p melosviz-mir --locked
#
# Python offline wheelhouse smoke lives in ``check_hermetic_python_smoke.sh``
# (same ``hermetic-smoke`` CI job). A committed ``vendor/`` tree remains optional.
#
# Linux-only. On Windows/macOS the script skips (exit 0).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

uname_s="$(uname -s 2>/dev/null || echo unknown)"
case "$uname_s" in
  Linux) ;;
  *)
    echo "check_hermetic_smoke: skip on ${uname_s} (Linux CI only)"
    exit 0
    ;;
esac

# Prefer rust-toolchain.toml / rustup so local stale Cargo does not fail.
CARGO=(cargo)
if command -v rustup >/dev/null 2>&1 && [[ -f "$ROOT/rust-toolchain.toml" ]]; then
  CARGO=(rustup run stable cargo)
elif ! command -v cargo >/dev/null 2>&1; then
  echo "check_hermetic_smoke: cargo not found" >&2
  exit 1
fi

cargo_ver="$("${CARGO[@]}" --version 2>/dev/null || true)"
echo "using: ${CARGO[*]} (${cargo_ver})"

export CARGO_TERM_COLOR=never

echo "==> [1/2] cargo fetch --locked (online once)"
"${CARGO[@]}" fetch --locked

echo "==> [2/2] offline cargo check -p melosviz-mir --locked"
export CARGO_NET_OFFLINE=true
"${CARGO[@]}" check -p melosviz-mir --locked

# Optional full-workspace offline check (set HERMETIC_WORKSPACE=1).
if [[ "${HERMETIC_WORKSPACE:-0}" == "1" ]]; then
  echo "==> [optional] offline cargo check --workspace --locked"
  "${CARGO[@]}" check --workspace --locked
fi

echo "OK: hermetic rust smoke passed (prefetch + CARGO_NET_OFFLINE melosviz-mir check)"
