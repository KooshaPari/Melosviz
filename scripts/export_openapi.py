#!/usr/bin/env python3
"""Export MelosViz bridge OpenAPI schema to docs/api/openapi.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "api" / "openapi.json"


def main() -> int:
    sys.path.insert(0, str(REPO / "backend" / "src"))
    from melosviz.bridge.server import app  # noqa: WPS433

    schema = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} ({len(schema.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
