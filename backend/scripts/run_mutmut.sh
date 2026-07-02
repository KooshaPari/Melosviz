#!/usr/bin/env bash
# Run mutmut against the MelosViz backend and enforce the >=75% kill-score
# gate from .qgate.toml (qgate [mutation].target_score = 75).
#
# Usage:
#   backend/scripts/run_mutmut.sh           # full run
#   backend/scripts/run_mutmut.sh fast      # single-process, fewer operators
#   backend/scripts/run_mutmut.sh --summary # tail the report
#
# Exit codes:
#   0  mutation score >= target
#   1  mutation score below target (or mutmut itself failed)
#   2  missing dependency (mutmut not installed)
set -euo pipefail

cd "$(dirname "$0")/.."  # backend/

TARGET_SCORE="${MUTMUT_TARGET_SCORE:-75}"

if ! python -m mutmut --version >/dev/null 2>&1; then
  echo "mutmut not installed — pip install mutmut>=3.0" >&2
  exit 2
fi

if [[ "${1:-}" == "fast" ]]; then
  python -m mutmut run \
    --paths-to-mutate src/melosviz/ \
    --jobs 1 \
    --no-progress || true
elif [[ "${1:-}" == "--summary" ]]; then
  python -m mutmut results || true
  exit 0
else
  python -m mutmut run \
    --paths-to-mutate src/melosviz/ \
    --jobs 4 \
    --no-progress || true
fi

# Compute kill score from mutmut JSON cache and enforce threshold.
python - <<EOF
import json, os, sys, pathlib
cache = pathlib.Path(".mutmut-cache")  # mutmut 3.x default cache file
if not cache.exists():
    print("no mutmut cache — run the sweep first", file=sys.stderr)
    sys.exit(1)
try:
    data = json.loads(cache.read_text())
except Exception as e:
    print(f"could not parse {cache}: {e}", file=sys.stderr)
    sys.exit(1)

total = len(data)
killed = sum(1 for m in data.values() if m.get("status") == "killed")
score = (killed / total * 100.0) if total else 0.0
print(f"mutmut: killed={killed}/{total} ({score:.1f}%) target={${TARGET_SCORE}}")
sys.exit(0 if score >= float(${TARGET_SCORE}) else 1)
EOF
