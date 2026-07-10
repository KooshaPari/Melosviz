#!/usr/bin/env python3
"""Optional atheris harness for RenderSpec JSON parsing (C07 L67).

    pip install atheris
    python fuzz/atheris_renderspec.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

try:
    import atheris  # type: ignore[import-not-found]
except ImportError:
    print("atheris not installed; pip install atheris", file=sys.stderr)
    raise SystemExit(0)

with atheris.instrument_imports():
    from melosviz.analysis.models import RenderSpec


def TestOneInput(data: bytes) -> None:
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return
    try:
        RenderSpec.model_validate_json(text)
    except Exception:
        # Expected for random bytes — harness looks for crashes/hangs.
        return


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
