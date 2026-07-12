#!/usr/bin/env python3
"""Validate Status enum rows in docs/GAP_AUDIT_QA_MATRIX.md."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GAP = REPO / "docs" / "GAP_AUDIT_QA_MATRIX.md"
ALLOWED = frozenset({"open", "mitigated", "closed", "accepted", "blocked"})


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(cells: list[str]) -> bool:
    return bool(cells) and all(set(c) <= {"-", ":"} and c for c in cells)


def main() -> int:
    if not GAP.is_file():
        print(f"FAIL: missing {GAP}", file=sys.stderr)
        return 1

    lines = GAP.read_text(encoding="utf-8").splitlines()
    status_idx: int | None = None
    counts: Counter[str] = Counter()
    errors: list[str] = []
    rows = 0

    for lineno, line in enumerate(lines, 1):
        if not line.strip().startswith("|"):
            status_idx = None
            continue
        cells = _cells(line)
        if not cells:
            continue
        if status_idx is None:
            lowered = [c.lower() for c in cells]
            if "status" in lowered:
                status_idx = lowered.index("status")
            continue
        if _is_sep(cells):
            continue
        rows += 1
        if status_idx >= len(cells):
            errors.append(f"L{lineno}: missing Status column")
            continue
        status = cells[status_idx]
        if not status:
            errors.append(f"L{lineno}: empty Status")
        elif status not in ALLOWED:
            errors.append(f"L{lineno}: invalid Status {status!r}")
        else:
            counts[status] += 1

    if errors:
        print("FAIL: GAP matrix Status lint:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    if rows == 0:
        print("FAIL: no GAP data rows with Status column", file=sys.stderr)
        return 1

    parts = [f"{s}={counts[s]}" for s in sorted(ALLOWED) if counts[s]]
    print(f"PASS: {rows} GAP rows — " + ", ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
