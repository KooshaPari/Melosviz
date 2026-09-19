#!/usr/bin/env python3
"""Export MelosViz bridge OpenAPI schema to docs/api/openapi.json.

`--check` compares the committed schema against the one the app generates and
exits non-zero on drift.

It compares the *parsed* documents, not the raw text, because the committed
file is formatted by Prettier (which keeps short `required` arrays inline)
while this script writes `json.dumps(indent=2)` (which always expands them).
A text diff made those two checks mutually unsatisfiable: regenerating the
file to satisfy the drift check broke `prettier --check`, and formatting the
file to satisfy Prettier broke the drift check. Comparing semantics keeps the
schema honest without either check fighting the other.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "api" / "openapi.json"


def build_schema() -> dict:
    sys.path.insert(0, str(REPO / "backend" / "src"))
    from melosviz.bridge.server import app  # noqa: WPS433

    return app.openapi()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or verify the bridge OpenAPI schema.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the committed schema with the generated one and write nothing.",
    )
    args = parser.parse_args()

    schema = build_schema()
    rel = OUT.relative_to(REPO)
    paths = len(schema.get("paths", {}))

    if args.check:
        if not OUT.is_file():
            print(f"::error::{rel} is missing; run scripts/export_openapi.py")
            return 1
        committed = json.loads(OUT.read_text(encoding="utf-8"))
        if committed != schema:
            print(
                "::error::OpenAPI drift — run scripts/export_openapi.py, then "
                f"prettier --write {rel}"
            )
            return 1
        print(f"{rel} matches the generated schema ({paths} paths)")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {rel} ({paths} paths); run `prettier --write {rel}` before committing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
