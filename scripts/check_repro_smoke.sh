#!/usr/bin/env bash
# SOURCE_DATE_EPOCH reproducible-build smoke (WBS-P1.5 / C06 L52).
#
# Scope (intentionally narrow — see docs/SUPPLY_CHAIN.md):
#   1) Deterministic archive of lockfiles / manifests under a fixed epoch
#   2) Double cargo build of melosviz-mir --release with the same epoch +
#      path remapping; compare SHA-256 of the two binaries
#
# Linux-only. On Windows/macOS the script skips (exit 0) — full Windows MSI
# bit-identity is out of scope.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

uname_s="$(uname -s 2>/dev/null || echo unknown)"
case "$uname_s" in
  Linux) ;;
  *)
    echo "check_repro_smoke: skip on ${uname_s} (Linux CI only; Windows MSI bit-identity out of scope)"
    exit 0
    ;;
esac

if ! command -v sha256sum >/dev/null 2>&1; then
  echo "check_repro_smoke: sha256sum not found" >&2
  exit 1
fi
if ! command -v tar >/dev/null 2>&1; then
  echo "check_repro_smoke: tar not found" >&2
  exit 1
fi

# Prefer rust-toolchain.toml / rustup so local stale Cargo (e.g. 1.75) does not fail.
CARGO=(cargo)
if command -v rustup >/dev/null 2>&1 && [[ -f "$ROOT/rust-toolchain.toml" ]]; then
  CARGO=(rustup run stable cargo)
elif ! command -v cargo >/dev/null 2>&1; then
  echo "check_repro_smoke: cargo not found" >&2
  exit 1
fi

cargo_ver="$("${CARGO[@]}" --version 2>/dev/null || true)"
echo "using: ${CARGO[*]} (${cargo_ver})"
# melosviz-mir requires rust-version 1.80+; skip binary compare on older toolchains.
SKIP_BIN=0
if [[ "$cargo_ver" =~ cargo\ ([0-9]+)\.([0-9]+) ]]; then
  maj="${BASH_REMATCH[1]}"
  min="${BASH_REMATCH[2]}"
  if (( maj < 1 || (maj == 1 && min < 80) )); then
    echo "check_repro_smoke: cargo ${maj}.${min} < 1.80 — archive check only (binary skip)"
    SKIP_BIN=1
  fi
fi

EPOCH="${SOURCE_DATE_EPOCH:-}"
if [[ -z "$EPOCH" ]]; then
  EPOCH="$(git log -1 --pretty=%ct)"
fi
export SOURCE_DATE_EPOCH="$EPOCH"
echo "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/melosviz-repro.XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

# --- 1) Deterministic source-derived archive (always stable) ---------------
ARCHIVE_LIST=(
  Cargo.lock
  Cargo.toml
  backend/uv.lock
  crates/melosviz-mir/Cargo.toml
  crates/melosviz-render-wgpu/Cargo.toml
)
for f in "${ARCHIVE_LIST[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "check_repro_smoke: missing required file: $f" >&2
    exit 1
  fi
done

pack_once() {
  local out="$1"
  # Portable GNU tar flags for reproducible archives.
  tar --sort=name \
    --mtime="@${SOURCE_DATE_EPOCH}" \
    --owner=0 --group=0 --numeric-owner \
    -cf "$out" \
    "${ARCHIVE_LIST[@]}"
}

pack_once "$WORKDIR/a.tar"
pack_once "$WORKDIR/b.tar"
HASH_A="$(sha256sum "$WORKDIR/a.tar" | awk '{print $1}')"
HASH_B="$(sha256sum "$WORKDIR/b.tar" | awk '{print $1}')"
echo "archive sha256 a=${HASH_A}"
echo "archive sha256 b=${HASH_B}"
if [[ "$HASH_A" != "$HASH_B" ]]; then
  echo "check_repro_smoke: deterministic archive hashes differ" >&2
  exit 1
fi
echo "OK: deterministic archive hashes match"

# --- 2) Double cargo release build of melosviz-mir -------------------------
if [[ "$SKIP_BIN" -eq 1 ]]; then
  echo "OK: archive repro smoke passed (binary compare skipped — upgrade cargo via rustup)"
  exit 0
fi

REPO_ABS="$ROOT"
export CARGO_TERM_COLOR=never
# Remap absolute paths so debug/path metadata does not encode the host cwd.
export RUSTFLAGS="--remap-path-prefix=${REPO_ABS}=. ${RUSTFLAGS:-}"

build_once() {
  local target_dir="$1"
  "${CARGO[@]}" build -p melosviz-mir --release --locked --target-dir "$target_dir"
}

build_once "$WORKDIR/target-a"
build_once "$WORKDIR/target-b"

BIN_A="$WORKDIR/target-a/release/melosviz-mir"
BIN_B="$WORKDIR/target-b/release/melosviz-mir"
if [[ ! -f "$BIN_A" || ! -f "$BIN_B" ]]; then
  echo "check_repro_smoke: expected release binaries missing" >&2
  ls -la "$WORKDIR/target-a/release" "$WORKDIR/target-b/release" || true
  exit 1
fi

BIN_HASH_A="$(sha256sum "$BIN_A" | awk '{print $1}')"
BIN_HASH_B="$(sha256sum "$BIN_B" | awk '{print $1}')"
echo "binary sha256 a=${BIN_HASH_A}"
echo "binary sha256 b=${BIN_HASH_B}"
if [[ "$BIN_HASH_A" != "$BIN_HASH_B" ]]; then
  echo "check_repro_smoke: melosviz-mir binaries differ under fixed SOURCE_DATE_EPOCH" >&2
  echo "  (same runner / toolchain expected; see docs/SUPPLY_CHAIN.md)" >&2
  exit 1
fi
echo "OK: melosviz-mir release binaries match under SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}"
