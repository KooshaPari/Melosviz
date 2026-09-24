#!/usr/bin/env python3
"""CI gate: en + es locale catalogs must have identical key sets.

WBS-P3.5 closes the full locale-coverage work item. Drift (a key added
to one locale but missing from the other) silently falls back to English
at runtime, so this gate keeps the en + es surfaces in lockstep.

Scans every ``locales/{en,es}.json`` under the repo root and fails on
the first pair whose key sets differ. Exits 0 with a one-line summary
on parity, exits 1 with a diff on drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOCALES_GLOBS = (
    REPO / "backend" / "src" / "melosviz" / "i18n" / "locales",
    REPO / "desktop" / "locales",
    REPO / "web" / "src" / "i18n" / "locales",
)


def _catalogs(locales_dir: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for path in sorted(locales_dir.glob("*.json")):
        locale = path.stem
        try:
            out[locale] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"{locales_dir}: invalid JSON in {path.name}: {exc}", file=sys.stderr)
            sys.exit(2)
    return out


def main() -> int:
    failed = False
    for locales_dir in LOCALES_GLOBS:
        if not locales_dir.exists():
            continue
        catalogs = _catalogs(locales_dir)
        if "en" not in catalogs:
            print(f"{locales_dir}: missing en.json (skipping)", file=sys.stderr)
            continue
        en_keys = set(catalogs["en"].keys())
        for locale, catalog in catalogs.items():
            if locale == "en":
                continue
            loc_keys = set(catalog.keys())
            missing = en_keys - loc_keys
            extra = loc_keys - en_keys
            if not missing and not extra:
                print(
                    f"{locales_dir.relative_to(REPO)}/{locale}.json: "
                    f"parity OK ({len(en_keys)} keys)"
                )
                continue
            failed = True
            print(
                f"{locales_dir.relative_to(REPO)}/{locale}.json: drift vs en",
                file=sys.stderr,
            )
            for key in sorted(missing):
                print(f"  - missing in {locale}: {key}", file=sys.stderr)
            for key in sorted(extra):
                print(f"  - extra in {locale}: {key}", file=sys.stderr)
    if failed:
        print("locale parity gate FAILED", file=sys.stderr)
        return 1
    print("locale parity gate OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
