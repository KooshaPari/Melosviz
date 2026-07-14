#!/usr/bin/env bash
# Hermetic Python offline wheelhouse smoke (WBS-P1.14 / C06 L54 v2).
#
# Scope (see docs/AIRGAP.md + docs/SUPPLY_CHAIN.md):
#   1) Online once: export locked runtime deps, build melosviz wheel, download wheels
#   2) Offline: PIP_NO_INDEX=1 pip install --find-links=wheelhouse + import smoke
#
# Does NOT commit a vendor/ tree — wheelhouse lives under dist/ (gitignored).
# Linux-only. On Windows/macOS the script skips (exit 0).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

uname_s="$(uname -s 2>/dev/null || echo unknown)"
case "$uname_s" in
  Linux) ;;
  *)
    echo "check_hermetic_python_smoke: skip on ${uname_s} (Linux CI only)"
    exit 0
    ;;
esac

command -v uv >/dev/null 2>&1 || {
  echo "check_hermetic_python_smoke: uv not found" >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo "check_hermetic_python_smoke: python3 not found" >&2
  exit 1
}

WHEELHOUSE="${HERMETIC_WHEELHOUSE:-$ROOT/dist/wheelhouse-python-smoke}"
VENV="${HERMETIC_PYTHON_VENV:-$ROOT/dist/hermetic-python-smoke-venv}"
REQS="$ROOT/dist/hermetic-python-reqs.txt"

cleanup() {
  rm -rf "$WHEELHOUSE" "$VENV" "$REQS"
}
trap cleanup EXIT

mkdir -p "$WHEELHOUSE"

echo "==> [1/3] export locked runtime deps + build melosviz wheel (online once)"
(
  cd "$ROOT/backend"
  uv export --frozen --no-dev --no-emit-project --no-hashes -o "$REQS"
  uv build --wheel -o "$WHEELHOUSE"
)

echo "==> [2/3] download dependency wheels into wheelhouse (online once)"
python3 -m pip download -r "$REQS" -d "$WHEELHOUSE" --quiet

wheel="$(ls -1 "$WHEELHOUSE"/melosviz-*.whl | head -1)"
[[ -f "$wheel" ]] || {
  echo "check_hermetic_python_smoke: missing melosviz wheel in $WHEELHOUSE" >&2
  exit 1
}

echo "==> [3/3] offline venv install + import smoke (PIP_NO_INDEX=1)"
python3 -m venv "$VENV"
# shellcheck source=/dev/null
source "$VENV/bin/activate"
export PIP_NO_INDEX=1
python -m pip install --no-index --find-links="$WHEELHOUSE" "$wheel" --quiet
python -c "import melosviz; print('import melosviz OK —', melosviz.__version__)"

echo "OK: hermetic python smoke passed (wheelhouse prefetch + offline import)"
echo "Note: committed vendor/ tree remains optional (operator path in AIRGAP.md)."
