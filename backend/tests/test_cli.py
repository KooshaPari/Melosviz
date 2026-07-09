"""Unit tests for the melosviz CLI entry-point (melosviz.cli.main).

Uses subprocess so the argparse-based CLI is exercised end-to-end without
needing click or any heavy optional dep (librosa, uvicorn, etc.).
"""

from __future__ import annotations

import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke ``python -m melosviz.cli.main`` with *args* and capture output."""
    return subprocess.run(
        [sys.executable, "-m", "melosviz.cli.main", *args],
        capture_output=True,
        text=True,
    )


class TestVersionCommand:
    def test_version_exits_zero(self) -> None:
        result = _run("version")
        assert result.returncode == 0

    def test_version_prints_something(self) -> None:
        result = _run("version")
        assert result.stdout.strip() != ""


class TestPresetsCommand:
    def test_presets_exits_zero(self) -> None:
        result = _run("presets")
        assert result.returncode == 0

    def test_presets_lists_at_least_one(self) -> None:
        result = _run("presets")
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(lines) >= 1, f"Expected at least one preset, got: {result.stdout!r}"


class TestAnalyzeCommand:
    def test_analyze_nonexistent_file_returns_nonzero(self) -> None:
        result = _run("analyze", "/nonexistent/path/to/audio.wav")
        assert result.returncode != 0

    def test_analyze_nonexistent_file_prints_error(self) -> None:
        result = _run("analyze", "/nonexistent/path/to/audio.wav")
        assert (
            "not found" in result.stderr.lower() or "no such" in result.stderr.lower()
        )


class TestServeHelp:
    def test_serve_help_exits_zero(self) -> None:
        result = _run("serve", "--help")
        assert result.returncode == 0

    def test_serve_help_mentions_host(self) -> None:
        result = _run("serve", "--help")
        assert "--host" in result.stdout
