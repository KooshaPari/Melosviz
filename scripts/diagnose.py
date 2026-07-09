"""Self-diagnose script for MelosViz environment prerequisites (MV-FR-50).

Public surface (consumed by ``backend/tests/test_diagnose_bdd.py`` and the
``make diagnose`` Makefile target):

* ``run_diagnose(overrides=None) -> DiagnoseReport`` — run all checks
* ``CheckResult`` — a single row in the report (attrs: ``name``, ``status``,
  ``detail``, ``required``)
* ``DiagnoseReport`` — aggregate (attrs: ``checks`` list, ``required_passed``
  bool, ``exit_code`` int)
* ``format_table(report) -> str`` — render the report as an ASCII table with
  columns ``Check`` / ``Status`` / ``Detail``
* ``main()`` — CLI entry-point that prints the table and returns ``exit_code``

The script runs zero required dependencies outside the Python standard
library. All checks are designed to complete in well under a second on a
fresh laptop.

Spec source: ``docs/specs/SPEC.md`` § FR-50 and
``docs/specs/acceptance/diagnose.feature``.
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CheckResult:
    """One row of the diagnose report.

    Attributes:
        name: short identifier (e.g. "ffmpeg", "blender").
        status: one of "PASS", "WARN", "FAIL".
        detail: human-readable one-line description of the result.
        required: True if a failure here should bump ``exit_code`` to 1.
    """

    name: str
    status: str
    detail: str
    required: bool = True


@dataclass
class DiagnoseReport:
    """Aggregate of every check the diagnose script ran."""

    checks: List[CheckResult] = field(default_factory=list)

    @property
    def required_passed(self) -> bool:
        """True iff every check with ``required=True`` is in PASS status."""
        return all(c.status == "PASS" for c in self.checks if c.required)

    @property
    def exit_code(self) -> int:
        """0 on all-pass; 1 if any required check is not PASS."""
        return 0 if self.required_passed else 1


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
def _check_python() -> CheckResult:
    """Python version check (required, >= 3.10)."""
    vi = sys.version_info
    if (vi.major, vi.minor) >= (3, 10):
        return CheckResult(
            name="python",
            status="PASS",
            detail=f"Python {vi.major}.{vi.minor}.{vi.micro}",
            required=True,
        )
    return CheckResult(
        name="python",
        status="FAIL",
        detail=f"Python {vi.major}.{vi.minor} < 3.10 (required)",
        required=True,
    )


def _check_ffmpeg(override: Optional[str]) -> CheckResult:
    """ffmpeg check (required). Resolves via PATH or ``MELOSVIZ_FFMPEG_BIN``."""
    if override is not None:
        return CheckResult(
            name="ffmpeg",
            status="PASS",
            detail=f"override: {override}",
            required=True,
        )
    env_bin = os.environ.get("MELOSVIZ_FFMPEG_BIN")
    if env_bin:
        if os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
            return CheckResult(
                name="ffmpeg",
                status="PASS",
                detail=f"MELOSVIZ_FFMPEG_BIN={env_bin}",
                required=True,
            )
        return CheckResult(
            name="ffmpeg",
            status="FAIL",
            detail=f"MELOSVIZ_FFMPEG_BIN={env_bin!r} not executable",
            required=True,
        )
    which = shutil.which("ffmpeg")
    if which:
        return CheckResult(
            name="ffmpeg",
            status="PASS",
            detail=f"on PATH: {which}",
            required=True,
        )
    return CheckResult(
        name="ffmpeg",
        status="FAIL",
        detail="not on PATH and MELOSVIZ_FFMPEG_BIN unset",
        required=True,
    )


def _check_optional_module(name: str, import_name: str) -> CheckResult:
    """Optional-module check (not required). Maps ``bpy`` → blender row."""
    try:
        importlib.import_module(import_name)
        return CheckResult(
            name=name,
            status="PASS",
            detail=f"{import_name} importable",
            required=False,
        )
    except Exception:  # noqa: BLE001 — intentionally broad
        return CheckResult(
            name=name,
            status="WARN",
            detail=f"{import_name} not importable (optional)",
            required=False,
        )


def _check_wgpu() -> CheckResult:
    """GPU / wgpu probe (optional). Reports WARN when no GPU is enumerable.

    We deliberately do not call ``wgpu`` here: wgpu imports vary by platform
    and we want the probe to be safe to run on any machine. We treat the
    absence of a known GPU vendor env var or wgpu probe failure as WARN.
    """
    try:
        # Cheap probe — try importing wgpu; if not installed, WARN.
        importlib.import_module("wgpu")
        return CheckResult(
            name="gpu-wgpu",
            status="PASS",
            detail="wgpu module importable",
            required=False,
        )
    except Exception:  # noqa: BLE001
        return CheckResult(
            name="gpu-wgpu",
            status="WARN",
            detail="wgpu not installed (optional; wgpu backend disabled)",
            required=False,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_diagnose(overrides: Optional[Dict[str, Any]] = None) -> DiagnoseReport:
    """Run the diagnose checks and return a ``DiagnoseReport``.

    Args:
        overrides: Optional dict mapping check-name to a synthetic result.
            Recognised keys:
              * ``"python"`` (bool) — force python PASS/FAIL
              * ``"ffmpeg"`` (str | None) — override ffmpeg resolver
              * ``"bpy"``, ``"demucs"``, ``"librosa"`` (bool) — force optional
                module present (True) or absent (False)
              * ``"wgpu"`` (bool) — force wgpu present/absent

            Any other key is ignored. If a key is omitted, the corresponding
            real check is performed.
    """
    ov = dict(overrides or {})

    checks: List[CheckResult] = []

    # python (required)
    if "python" in ov:
        ok = bool(ov["python"])
        checks.append(
            CheckResult(
                name="python",
                status="PASS" if ok else "FAIL",
                detail=f"override: {'PASS' if ok else 'FAIL'}",
                required=True,
            )
        )
    else:
        checks.append(_check_python())

    # ffmpeg (required)
    if "ffmpeg" in ov:
        if ov["ffmpeg"] is None:
            checks.append(
                CheckResult(
                    name="ffmpeg",
                    status="FAIL",
                    detail="override: missing",
                    required=True,
                )
            )
        else:
            checks.append(_check_ffmpeg(ov["ffmpeg"]))
    else:
        checks.append(_check_ffmpeg(None))

    # optional modules
    if ov.get("bpy") is True:
        checks.append(_check_optional_module("blender", "bpy"))
    elif ov.get("bpy") is False:
        checks.append(
            CheckResult(
                name="blender",
                status="WARN",
                detail="bpy not importable (optional; override)",
                required=False,
            )
        )
    else:
        checks.append(_check_optional_module("blender", "bpy"))

    if ov.get("demucs") is True:
        checks.append(_check_optional_module("demucs", "demucs"))
    elif ov.get("demucs") is False:
        checks.append(
            CheckResult(
                name="demucs",
                status="WARN",
                detail="demucs not importable (optional; override)",
                required=False,
            )
        )
    else:
        checks.append(_check_optional_module("demucs", "demucs"))

    if ov.get("librosa") is True:
        checks.append(_check_optional_module("librosa", "librosa"))
    elif ov.get("librosa") is False:
        checks.append(
            CheckResult(
                name="librosa",
                status="WARN",
                detail="librosa not importable (optional; override)",
                required=False,
            )
        )
    else:
        checks.append(_check_optional_module("librosa", "librosa"))

    # wgpu
    if ov.get("wgpu") is False:
        checks.append(
            CheckResult(
                name="gpu-wgpu",
                status="WARN",
                detail="wgpu not enumerable (optional; override)",
                required=False,
            )
        )
    elif ov.get("wgpu") is True:
        checks.append(
            CheckResult(
                name="gpu-wgpu",
                status="PASS",
                detail="override: present",
                required=False,
            )
        )
    else:
        checks.append(_check_wgpu())

    return DiagnoseReport(checks=checks)


def format_table(report: DiagnoseReport) -> str:
    """Render the report as an ASCII table with columns Check / Status / Detail.

    The column separator is two-or-more spaces. Status column is one of
    ``PASS``, ``WARN``, ``FAIL``.
    """
    rows = [("Check", "Status", "Detail")]
    for c in report.checks:
        rows.append((c.name, c.status, c.detail))

    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    lines = []
    for idx, row in enumerate(rows):
        line = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        lines.append(line.rstrip())
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry-point: prints the table and returns ``report.exit_code``."""
    parser = argparse.ArgumentParser(
        prog="diagnose",
        description="Report MelosViz environment prerequisites.",
    )
    parser.parse_args(argv)
    report = run_diagnose()
    print(format_table(report))
    return report.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())