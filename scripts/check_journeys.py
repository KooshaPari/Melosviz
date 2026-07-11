#!/usr/bin/env python3
"""CI friction gate for docs/USER_JOURNEYS.md (C03 L30.12).

Fails if required journeys/gap rows are missing or linked eval surfaces vanish.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JOURNEYS = REPO / "docs" / "USER_JOURNEYS.md"

REQUIRED_HEADINGS = (
    "## J1 — Analyze a WAV (desktop)",
    "## J2 — Apply preset + export",
    "## J3 — Web preview",
    "## J4 — Release install",
    "## J5 — Operator bridge",
    "## Gap log",
)

REQUIRED_PATHS = (
    REPO / "scripts" / "diagnose.py",
    REPO / "eval" / "harbor" / "adapter.py",
    REPO / "web" / "a11y" / "fixture.html",
    REPO / "docs" / "EVAL.md",
    REPO / "deploy" / "prometheus" / "melosviz-bridge-rules.yaml",
)


def main() -> int:
    if not JOURNEYS.is_file():
        print(f"FAIL: missing {JOURNEYS}", file=sys.stderr)
        return 1
    text = JOURNEYS.read_text(encoding="utf-8")
    missing = [h for h in REQUIRED_HEADINGS if h not in text]
    if missing:
        print("FAIL: USER_JOURNEYS missing sections:", file=sys.stderr)
        for h in missing:
            print(f"  - {h}", file=sys.stderr)
        return 1
    if "| Journey | Known gap | Tracking |" not in text:
        print("FAIL: gap log table header missing", file=sys.stderr)
        return 1
    absent = [p for p in REQUIRED_PATHS if not p.exists()]
    if absent:
        print("FAIL: journey-linked paths missing:", file=sys.stderr)
        for p in absent:
            print(f"  - {p.relative_to(REPO)}", file=sys.stderr)
        return 1
    print(f"PASS: {len(REQUIRED_HEADINGS)} journeys + {len(REQUIRED_PATHS)} surfaces OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
