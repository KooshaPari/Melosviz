#!/usr/bin/env bash
# Run cargo-mutants against the entire MelosViz workspace and enforce the
# >=75% kill-score gate from .qgate.toml.
#
# Usage:
#   crates/scripts/run_cargo_mutants.sh           # full sweep
#   crates/scripts/run_cargo_mutants.sh melosviz-mir             # single crate
#   crates/scripts/run_cargo_mutants.sh --report-only           # tally existing
#
# Exit codes:
#   0  mutation score >= TARGET
#   1  mutation score below TARGET (or cargo-mutants failed)
#   2  missing dependency (cargo-mutants not installed)
set -euo pipefail

cd "$(dirname "$0")/.."
# Jump to repo root so the workspace Cargo.toml resolves correctly.
cd "$(git rev-parse --show-toplevel)"

TARGET_SCORE="${CARGO_MUTANTS_TARGET:-75}"
JOBS="${JOBS:-4}"

if ! command -v cargo-mutants >/dev/null 2>&1; then
  echo "cargo-mutants not installed — install with: cargo install cargo-mutants --version '^25'" >&2
  exit 2
fi

REPORT="target/mutants/mutants.out"

if [[ "${1:-}" == "--report-only" ]]; then
  if [[ ! -d "${REPORT}" ]]; then
    echo "no prior cargo-mutants run found at ${REPORT}" >&2
    exit 2
  fi
else
  pkg_args=()
  if [[ "${1:-}" =~ ^[A-Za-z0-9_-]+$ ]]; then
    pkg_args=(-p "$1")
  fi
  cargo mutants "${pkg_args[@]}" \
    --no-shuffle \
    --test-threads "${JOBS}" \
    --output "${REPORT}" \
    --no-times \
    --baseline skip || true
fi

# cargo-mutants emits mutants.json + caught/missed/unviable summary lists.
python - <<EOF
import json, pathlib, re, sys
report = pathlib.Path("${REPORT}")
if not report.is_dir():
    print("no report dir — skipping score", file=sys.stderr)
    sys.exit(2)
# cargo-mutants prints per-file summaries like:
#   caught/missed/unviable  12 / 3 / 2
caught = missed = unviable = 0
for line in report.glob("mutants.*.txt"):
    txt = line.read_text()
    for block in re.findall(r"(\d+)\s*/\s*(\d+)\s*/\s*(\d+)", txt):
        c, m, u = (int(x) for x in block)
        caught += c; missed += m; unviable += u
total_mutants = caught + missed
score = (caught / total_mutants * 100.0) if total_mutants else 0.0
target = float(${TARGET_SCORE})
print(f"cargo-mutants: caught={caught} missed={missed} unviable={unviable} -> score={score:.1f}% (target={target}%)")
sys.exit(0 if score >= target else 1)
EOF
