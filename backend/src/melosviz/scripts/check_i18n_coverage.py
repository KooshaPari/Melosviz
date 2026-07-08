#!/usr/bin/env python3
"""Check that all keys in en.json exist in every other locale file."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repos/melosviz/
I18N_DIR = ROOT / "i18n" / "messages"


def main() -> int:
    if not I18N_DIR.is_dir():
        print(f"FAIL: {I18N_DIR} not found")
        return 1

    locale_files = sorted(I18N_DIR.glob("*.json"))
    if not locale_files:
        print("FAIL: no locale files found")
        return 1

    # Load reference locale (en)
    ref_path = I18N_DIR / "en.json"
    if not ref_path.exists():
        print("FAIL: en.json (reference) not found")
        return 1

    ref = json.loads(ref_path.read_text())
    ref_keys = set(ref.keys())
    errors = 0

    for lf in locale_files:
        locale = lf.stem
        data = json.loads(lf.read_text())
        keys = set(data.keys())

        # Missing keys
        missing = ref_keys - keys
        if missing:
            print(f"  MISS  {locale}: {sorted(missing)}")
            errors += 1

        # Extra keys (not in reference)
        extra = keys - ref_keys
        if extra:
            print(f"  EXTRA {locale}: {sorted(extra)}")
            errors += 1

        # Empty values
        empty = [k for k, v in data.items() if not isinstance(v, str) or not v.strip()]
        if empty:
            print(f"  EMPTY {locale}: {empty}")
            errors += 1

    total = len(ref_keys)
    coverage = f"{total - errors}/{total}" if errors == 0 else f"errors={errors}"
    print(f"\n  coverage: {len(ref_keys)} keys, {coverage}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
