#!/usr/bin/env python3
"""Portability smoke: core melosviz + CLI without FFmpeg/Blender (C07 L70).

Proves the default install graph imports cleanly and host render tools fail
with actionable errors when absent — they are not required for core usage.

Wired as ``portability-smoke`` in ``.github/workflows/supply-chain.yml``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))


def _clean_host_tool_env() -> None:
    for key in ("MELOSVIZ_FFMPEG_BIN", "MELOSVIZ_BLENDER_BIN"):
        os.environ.pop(key, None)


def main() -> int:
    _clean_host_tool_env()

    import melosviz
    from melosviz.cli.main import _cmd_version
    import argparse

    assert melosviz.__version__, "melosviz.__version__ must be set"
    assert _cmd_version(argparse.Namespace()) == 0, "CLI version subcommand failed"

    from melosviz.render.blender_exporter import (
        BlenderNotFoundError,
        _resolve_blender_binary,
    )
    from melosviz.render.video_exporter import (
        FFMpegNotFoundError,
        _resolve_ffmpeg_binary,
    )

    with patch("shutil.which", return_value=None):
        try:
            _resolve_ffmpeg_binary()
        except FFMpegNotFoundError as exc:
            assert exc, "FFMpegNotFoundError must carry a message"
        else:
            print(
                "FAIL: _resolve_ffmpeg_binary succeeded with ffmpeg absent",
                file=sys.stderr,
            )
            return 1

        try:
            _resolve_blender_binary()
        except BlenderNotFoundError as exc:
            assert exc, "BlenderNotFoundError must carry a message"
        else:
            print(
                "FAIL: _resolve_blender_binary succeeded with blender absent",
                file=sys.stderr,
            )
            return 1

    print(
        "PASS: portability smoke (core import + CLI version; "
        "FFmpeg/Blender gracefully absent)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
