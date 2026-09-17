"""Shared subprocess helpers for the audio-finishing package.

Kept separate so ``loudness``, ``stems``, ``master`` and ``reference`` can all
depend on it without importing each other.
"""

from __future__ import annotations

import shutil
import subprocess

__all__ = ["run", "ffmpeg_available"]


def run(cmd: list[str], timeout: float = 120.0) -> tuple[int, str, str]:
    """Run a subprocess, capturing stdout + stderr."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return 127, "", f"command not found: {exc}"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    return proc.returncode, proc.stdout, proc.stderr


def ffmpeg_available() -> bool:
    """True when ``ffmpeg`` is resolvable on PATH."""
    return shutil.which("ffmpeg") is not None
