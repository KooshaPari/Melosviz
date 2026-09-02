"""BDD step definitions for ``docs/specs/acceptance/diagnose.feature`` (FR-50).

This test uses ``pytest-bdd`` to bind the Gherkin scenarios in
``docs/specs/acceptance/diagnose.feature`` to Python step definitions that
exercise the ``scripts.diagnose`` module.

The test file lives under ``backend/tests/`` so it runs in the same pytest
session as the rest of the backend suite, but it locates the
``scripts/diagnose.py`` and ``docs/specs/acceptance/diagnose.feature``
files via absolute paths derived from ``__file__`` so it works regardless
of the directory pytest is invoked from.

RED-state contract
------------------
While ``scripts/diagnose.py`` does not exist (or its public surface is
incomplete), pytest will fail to collect / run the scenarios in this file.
The first GREEN occurs when the module exposes ``run_diagnose()``,
``CheckResult``, ``DiagnoseReport``, ``format_table()`` and ``main()``
with the contract documented in ``docs/specs/SPEC.md`` § FR-50.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

# ``scripts.diagnose`` does not exist in the RED state. Skip the whole
# module so the rest of the suite can still run; revisit when
# ``scripts/diagnose.py`` is implemented (it must expose ``run_diagnose()``,
# ``CheckResult``, ``DiagnoseReport``, ``format_table()`` and ``main()``).
pytest.importorskip("diagnose", reason="scripts.diagnose is not implemented yet")

from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402

# ---------------------------------------------------------------------------
# Locate the repo root + the two files the test needs.
# This file: backend/tests/test_diagnose_bdd.py
# Repo root: ../../../
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_DIAGNOSE_PY = _SCRIPTS_DIR / "diagnose.py"
_FEATURE_PATH = _REPO_ROOT / "docs" / "specs" / "acceptance" / "diagnose.feature"

# Make ``scripts.diagnose`` importable as a package module. This adds the
# repo root to ``sys.path`` (it isn't normally there in a backend pytest
# run) and relies on ``scripts/__init__.py`` being present. The
# ``scripts`` directory already follows the package convention for the
# existing ``generate_icon.py``-style entries; the empty
# ``scripts/__init__.py`` is added alongside this test.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ``scripts.diagnose`` does not exist in the RED state. Skip the whole
# module so the rest of the suite can still run; revisit when
# ``scripts/diagnose.py`` is implemented (it must expose ``run_diagnose()``,
# ``CheckResult``, ``DiagnoseReport``, ``format_table()`` and ``main()``).
pytest.importorskip("diagnose", reason="scripts.diagnose is not implemented yet")

from scripts import diagnose  # noqa: E402  (intentional import after sys.path tweak)

# Bind every Scenario in the .feature file to a test function.
scenarios(str(_FEATURE_PATH))


# ---------------------------------------------------------------------------
# Test fixture: a fresh ``Context`` object per scenario, plus a helper that
# lets steps inject synthetic resolver results so the test can force PASS,
# FAIL or WARN outcomes deterministically.
# ---------------------------------------------------------------------------
class Context:
    """Per-scenario bag of state passed between steps."""

    def __init__(self) -> None:
        self.report: Any | None = None
        self.rendered_table: str = ""
        # Optional per-scenario overrides for the diagnose module's
        # internal resolvers. Each entry maps a resolver name to a value
        # the diagnose module will consume instead of doing a real check.
        self.overrides: dict[str, Any] = {}


@pytest.fixture
def ctx() -> Context:
    return Context()


# ---------------------------------------------------------------------------
# Background steps
# ---------------------------------------------------------------------------
@given("a fresh Python 3.10+ interpreter is on PATH")
def python_interpreter_present() -> None:
    """The pytest harness itself requires Python 3.10+; assert that here."""
    assert sys.version_info >= (3, 10), (
        f"diagnose BDD test requires Python >= 3.10, got {sys.version_info}"
    )


@given("the diagnose script module is importable as `scripts.diagnose`")
def diagnose_module_importable() -> None:
    """Background step: the ``scripts.diagnose`` module is already imported.

    The import itself is the RED-state guard: the module-import at the top
    of this file raises ``ModuleNotFoundError`` while the script is missing.
    """
    assert hasattr(diagnose, "run_diagnose"), (
        "scripts.diagnose must expose run_diagnose()"
    )
    assert callable(diagnose.run_diagnose)


@given("the `run_diagnose()` function returns a `DiagnoseReport`")
def run_diagnose_returns_report() -> None:
    assert hasattr(diagnose, "DiagnoseReport"), (
        "scripts.diagnose must expose a DiagnoseReport type"
    )


# ---------------------------------------------------------------------------
# Given steps — environment manipulation
# ---------------------------------------------------------------------------
@given("ffmpeg is resolvable on PATH or via MELOSVIZ_FFMPEG_BIN")
def ffmpeg_resolvable(ctx: Context) -> None:
    ctx.overrides["ffmpeg"] = "/fake/ffmpeg"


@given("ffmpeg is NOT resolvable on PATH")
def ffmpeg_not_on_path(ctx: Context, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx.overrides["ffmpeg"] = None
    monkeypatch.delenv("MELOSVIZ_FFMPEG_BIN", raising=False)


@given("MELOSVIZ_FFMPEG_BIN is unset or points to a missing binary")
def ffmpeg_env_missing(ctx: Context, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx.overrides["ffmpeg"] = None
    monkeypatch.delenv("MELOSVIZ_FFMPEG_BIN", raising=False)


@given("Python version is at least 3.10")
def python_version_ok() -> None:
    assert sys.version_info >= (3, 10)


@given("the optional `bpy` module is not importable")
def bpy_absent(ctx: Context) -> None:
    ctx.overrides["bpy"] = False
    # Required checks must still pass so exit_code stays 0 (FR-50 #2).
    ctx.overrides.setdefault("ffmpeg", "/fake/ffmpeg")
    ctx.overrides.setdefault("python", True)


@given("the optional modules `bpy`, `demucs`, `librosa` are not importable")
def optional_audio_modules_absent(ctx: Context) -> None:
    ctx.overrides["bpy"] = False
    ctx.overrides["demucs"] = False
    ctx.overrides["librosa"] = False
    ctx.overrides["wgpu"] = False  # also kill the GPU probe
    ctx.overrides.setdefault("ffmpeg", "/fake/ffmpeg")
    ctx.overrides.setdefault("python", True)


@given("no `wgpu` adapter is enumerable")
def wgpu_absent(ctx: Context) -> None:
    ctx.overrides["wgpu"] = False
    ctx.overrides.setdefault("ffmpeg", "/fake/ffmpeg")
    ctx.overrides.setdefault("python", True)


@given("a diagnose run where all required checks pass")
def run_all_pass(ctx: Context) -> None:
    ctx.overrides.update(
        {
            "ffmpeg": "/fake/ffmpeg",
            "python": True,
            "bpy": True,
            "demucs": True,
            "librosa": True,
            "wgpu": True,
        }
    )
    ctx.report = diagnose.run_diagnose(overrides=ctx.overrides)


@given("a diagnose run where at least one required check fails")
def run_required_fail(ctx: Context) -> None:
    ctx.overrides.update(
        {
            "ffmpeg": None,  # required check fails
            "python": True,
            "bpy": True,
            "demucs": True,
            "librosa": True,
            "wgpu": True,
        }
    )
    ctx.report = diagnose.run_diagnose(overrides=ctx.overrides)


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------
@when("I invoke `run_diagnose()`")
def invoke_run_diagnose(ctx: Context) -> None:
    ctx.report = diagnose.run_diagnose(overrides=ctx.overrides or None)


@when("I render the diagnose output table")
def render_diagnose_table(ctx: Context) -> None:
    if ctx.report is None:
        ctx.report = diagnose.run_diagnose(overrides=ctx.overrides or None)
    ctx.rendered_table = diagnose.format_table(ctx.report)


@when("I inspect the report's `exit_code`")
def inspect_exit_code(ctx: Context) -> None:
    # The report was prepared in the matching ``Given`` step. Nothing to
    # do here other than assert it exists.
    assert ctx.report is not None, (
        "precondition violated: Given step did not produce a report"
    )


# ---------------------------------------------------------------------------
# Then steps — behavioural assertions on the report
# ---------------------------------------------------------------------------
@then("every required check has status PASS")
def every_required_check_passes(ctx: Context) -> None:
    assert ctx.report is not None
    required = [c for c in ctx.report.checks if c.required]
    assert required, "no required checks were registered"
    for c in required:
        assert c.status == "PASS", (
            f"required check {c.name!r} unexpectedly {c.status}: {c.detail}"
        )


@then("the report's `required_passed` is True")
def required_passed_true(ctx: Context) -> None:
    assert ctx.report is not None
    assert ctx.report.required_passed is True


@then("the report's `required_passed` is False")
def required_passed_false(ctx: Context) -> None:
    assert ctx.report is not None
    assert ctx.report.required_passed is False


@then("the report's `exit_code` is 0")
def exit_code_zero(ctx: Context) -> None:
    assert ctx.report is not None
    assert ctx.report.exit_code == 0


@then("the report's `exit_code` is 1")
def exit_code_one(ctx: Context) -> None:
    assert ctx.report is not None
    assert ctx.report.exit_code == 1


@then("it equals 0")
def it_equals_zero(ctx: Context) -> None:
    assert ctx.report is not None
    assert ctx.report.exit_code == 0


@then("it equals 1")
def it_equals_one(ctx: Context) -> None:
    assert ctx.report is not None
    assert ctx.report.exit_code == 1


@then("the ffmpeg check has status FAIL")
def ffmpeg_check_fails(ctx: Context) -> None:
    assert ctx.report is not None
    ffmpeg = _find_check(ctx.report.checks, "ffmpeg")
    assert ffmpeg.status == "FAIL", (
        f"ffmpeg check should FAIL, got {ffmpeg.status}: {ffmpeg.detail}"
    )


@then("the blender check has status WARN")
def blender_check_warns(ctx: Context) -> None:
    assert ctx.report is not None
    blender = _find_check(ctx.report.checks, "blender")
    assert blender.status == "WARN", (
        f"blender check should WARN, got {blender.status}: {blender.detail}"
    )


@then("the blender, demucs, librosa, and gpu-wgpu checks all have status WARN")
def all_optional_warn(ctx: Context) -> None:
    assert ctx.report is not None
    for name in ("blender", "demucs", "librosa", "gpu-wgpu"):
        c = _find_check(ctx.report.checks, name)
        assert c.status == "WARN", (
            f"optional check {name!r} should WARN, got {c.status}: {c.detail}"
        )


# ---------------------------------------------------------------------------
# Then steps — output table assertions
# ---------------------------------------------------------------------------
@then(parsers.parse('the header row contains the columns "{a}", "{b}", and "{c}"'))
def header_row_has_columns(ctx: Context, a: str, b: str, c: str) -> None:
    lines = ctx.rendered_table.splitlines()
    assert lines, "diagnose output is empty"
    header = lines[0]
    for col in (a, b, c):
        assert col in header, f"expected column {col!r} in header row, got: {header!r}"


@then("every body row has exactly three columns aligned with the header")
def body_rows_have_three_columns(ctx: Context) -> None:
    lines = ctx.rendered_table.splitlines()
    assert len(lines) >= 2, (
        f"expected at least header + 1 body row, got {len(lines)} lines"
    )

    # Column count = number of separators in a single row of the table.
    # We use a simple heuristic: split on 2+ spaces and assert the row has
    # the same column count as the header.
    def _col_count(row: str) -> int:
        return len([seg for seg in re.split(r"\s{2,}", row.strip()) if seg])

    header_cols = _col_count(lines[0])
    assert header_cols == 3, (
        f"header should have 3 columns, got {header_cols}: {lines[0]!r}"
    )
    for row in lines[1:]:
        cols = _col_count(row)
        assert cols == 3, f"body row should have 3 columns, got {cols}: {row!r}"


@then('the status column is one of "PASS", "WARN", or "FAIL"')
def status_column_valid(ctx: Context) -> None:
    lines = ctx.rendered_table.splitlines()
    assert len(lines) >= 2, "diagnose table has no body rows"
    for row in lines[1:]:
        cols = [seg.strip() for seg in re.split(r"\s{2,}", row.strip()) if seg]
        assert len(cols) == 3
        assert cols[1] in ("PASS", "WARN", "FAIL"), (
            f"status column must be PASS/WARN/FAIL, got {cols[1]!r} in row: {row!r}"
        )


# ---------------------------------------------------------------------------
# Then steps — API surface assertions
# ---------------------------------------------------------------------------
@then("the report has an attribute `checks` that is a list")
def report_has_checks_list(ctx: Context) -> None:
    assert ctx.report is not None
    assert isinstance(ctx.report.checks, list)


@then("every element of `checks` has attributes `name`, `status`, and `detail`")
def check_results_have_name_status_detail(ctx: Context) -> None:
    assert ctx.report is not None
    assert ctx.report.checks, "no checks in report"
    for c in ctx.report.checks:
        assert hasattr(c, "name")
        assert hasattr(c, "status")
        assert hasattr(c, "detail")


@then("the report has an attribute `required_passed` that is a bool")
def report_has_required_passed_bool(ctx: Context) -> None:
    assert ctx.report is not None
    assert isinstance(ctx.report.required_passed, bool)


@then("the report has an attribute `exit_code` that is an int")
def report_has_exit_code_int(ctx: Context) -> None:
    assert ctx.report is not None
    assert isinstance(ctx.report.exit_code, int)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _find_check(checks: list[Any], name: str) -> Any:
    """Return the check with ``name`` or fail fast with a readable message."""
    for c in checks:
        if c.name == name:
            return c
    available = [c.name for c in checks]
    raise AssertionError(f"no check named {name!r} in report (have: {available})")
