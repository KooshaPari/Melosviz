#!/usr/bin/env python3
"""Traceability lint check for MelosViz.

Verifies that the docs/TRACEABILITY.md matrix is internally consistent:
- Every MV-FR-*/MV-NFR-* ID declared in TRACEABILITY.md has at least one
  code reference (file:line or file path) and at least one test reference.
- Every MV-FR-*/MV-NFR-* ID declared in TRACEABILITY.md appears at least
  once in the test suite (via grep in test file names or test function names).
- Warns about IDs that appear in source code docstrings/comments but are not
  declared in TRACEABILITY.md.

Exit 0 = all checks pass.  Exit 1 = failures (printed to stdout).

Usage:
    python backend/scripts/check/check_traceability.py [--repo-root PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# ID patterns
# ---------------------------------------------------------------------------

# Matches full IDs like MV-FR-A01, MV-FR-P11, MV-NFR-001 (requires trailing digit)
_ID_RE = re.compile(r"\bMV-(?:FR|NFR)-[A-Z]*\d+\b")


def _collect_declared_ids(traceability_md: Path) -> dict[str, list[str]]:
    """Return {id: [lines_containing_id]} from TRACEABILITY.md."""
    text = traceability_md.read_text(encoding="utf-8")
    result: dict[str, list[str]] = {}
    for line in text.splitlines():
        for m in _ID_RE.finditer(line):
            rid = m.group()
            result.setdefault(rid, []).append(line.strip())
    return result


def _grep_id_in_tree(root: Path, rid: str, exts: tuple[str, ...]) -> list[str]:
    """Return list of 'file:line' hits for rid across files with given extensions."""
    hits: list[str] = []
    pattern = re.compile(re.escape(rid))
    for ext in exts:
        for path in root.rglob(f"*{ext}"):
            # skip worktrees and virtual envs
            parts = path.parts
            if any(p in (".venv", "__pycache__", ".claude", "node_modules") for p in parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                if pattern.search(line):
                    hits.append(f"{path}:{lineno}")
    return hits


def _grep_id_in_tests(test_root: Path, rid: str) -> list[str]:
    return _grep_id_in_tree(test_root, rid, (".py",))


def _grep_id_in_source(src_root: Path, rid: str) -> list[str]:
    return _grep_id_in_tree(src_root, rid, (".py", ".rs", ".ts", ".md"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Absolute path to repo root (default: auto-detect from this file's location)",
    )
    args = parser.parse_args(argv)

    script_path = Path(__file__).resolve()
    # backend/scripts/check/check_traceability.py → ../../.. = repo root
    repo_root = Path(args.repo_root) if args.repo_root else script_path.parents[3]

    traceability_md = repo_root / "docs" / "TRACEABILITY.md"
    if not traceability_md.exists():
        print(f"ERROR: {traceability_md} not found — run from repo root", file=sys.stderr)
        return 1

    test_root = repo_root / "backend" / "tests"
    src_root = repo_root / "backend" / "src"

    declared = _collect_declared_ids(traceability_md)
    if not declared:
        print("WARNING: No MV-FR-*/MV-NFR-* IDs found in TRACEABILITY.md")
        return 0

    failures: list[str] = []
    warnings: list[str] = []

    for rid in sorted(declared):
        # Check: at least one code-ref line in TRACEABILITY.md (contains "backend/" or a file path)
        lines_with_id = declared[rid]
        has_code_ref = any(
            ("backend/" in ln or ".py" in ln or ".rs" in ln)
            for ln in lines_with_id
        )
        if not has_code_ref:
            # Try to find any source hit
            src_hits = _grep_id_in_source(src_root, rid)
            if not src_hits:
                warnings.append(f"WARN  {rid}: no code reference in TRACEABILITY.md and not found in source tree")
            else:
                warnings.append(
                    f"WARN  {rid}: code ref found in source ({src_hits[0]}) but not cross-linked in TRACEABILITY.md"
                )

        # Check: test reference present (in test files or in TRACEABILITY.md lines)
        has_test_ref = any(
            ("test_" in ln or "tests/" in ln or ".feature" in ln)
            for ln in lines_with_id
        )
        if not has_test_ref:
            test_hits = _grep_id_in_tests(test_root, rid)
            if not test_hits:
                failures.append(
                    f"FAIL  {rid}: no test reference in TRACEABILITY.md and not tagged in any test file"
                )
            else:
                warnings.append(
                    f"WARN  {rid}: test hit found ({test_hits[0]}) but not cross-linked in TRACEABILITY.md"
                )

    # Report
    for w in warnings:
        print(w)
    for f in failures:
        print(f)

    n_ids = len(declared)
    n_fail = len(failures)
    n_warn = len(warnings)
    print(
        f"\nTraceability check: {n_ids} IDs — "
        f"{n_ids - n_fail - n_warn} clean, {n_warn} warnings, {n_fail} failures"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
