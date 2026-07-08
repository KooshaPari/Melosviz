"""MV-FR-54 — validator test for the top-level SPEC.md.

This test enforces the spec at ``docs/specs/top_level_spec_md_spec.md``.
It is the contract between the spec author (this file's siblings) and the
implementer (the top-level ``<repo-root>/SPEC.md``).

Failure mode
============
Before the top-level SPEC.md is authored, every assertion in this file
fails (RED). After authoring, every assertion passes (GREEN).

Why both files exist
====================
There are TWO SPEC.md files in this repository:

* ``docs/specs/SPEC.md`` — inner FR-N spec (presets + video exporter).
  Owned by the inner acceptance team. NOT the target of MV-FR-54.
* ``<repo-root>/SPEC.md`` — top-level product spec.
  New in MV-FR-54. This is the file this test enforces.

If the two files were collapsed, we would lose the inner FR-N traceability
matrix. They are intentionally separate.

Run::

    cd backend && pytest tests/test_top_level_spec_md_spec.py -v

Or via the project root::

    python -m pytest backend/tests/test_top_level_spec_md_spec.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution — robust to both repo-root and backend/ working dirs.
# ---------------------------------------------------------------------------


def _find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` until we find a directory containing ``Cargo.toml``.

    The repository root is the only directory that is both a Python package
    source root (``backend/src``) and a Rust workspace root (``Cargo.toml``).
    We use the Rust marker because it is a single canonical file, whereas the
    Python marker (pyproject.toml) exists under both the root and ``backend/``.
    """
    cur = start.resolve()
    for _ in range(8):  # bounded walk; CI environments can be deeply nested
        if (cur / "Cargo.toml").is_file() and (cur / "backend").is_dir():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    # Fall back to the CWD's ancestor if the marker walk failed (e.g. a
    # monorepo where Cargo.toml is one level up). This still gives a stable,
    # absolute path the rest of the suite can rely on.
    return Path(__file__).resolve().parents[3]


REPO_ROOT = _find_repo_root(Path(__file__))

TOP_LEVEL_SPEC = REPO_ROOT / "SPEC.md"
INNER_SPEC = REPO_ROOT / "docs" / "specs" / "SPEC.md"
SPEC_FOR_MV_FR_54 = REPO_ROOT / "docs" / "specs" / "top_level_spec_md_spec.md"

# ---------------------------------------------------------------------------
# Required headings — kept in lock-step with docs/specs/top_level_spec_md_spec.md § 3.
# ---------------------------------------------------------------------------

REQUIRED_HEADINGS: tuple[str, ...] = (
    "## 1. Architecture",
    "## 2. Domain Model",
    "## 3. Adapter Contract",
    "## 4. Spec Format v2 (RenderSpec JSON Schema)",
    "## 5. Render Pipeline",
    "## 6. Failure Modes",
    "## 7. Cross-Surface Boundaries",
    "## 8. Test Strategy",
    "## 9. Distribution",
    "## 10. Revision History",
)

MIN_LINES = 300
MIN_FAILURE_MODES = 8


# ---------------------------------------------------------------------------
# Sanity — the test file's own siblings must exist before we can run.
# ---------------------------------------------------------------------------


def test_test_file_can_resolve_repo_root() -> None:
    """The validator must be able to locate the repository root.

    If this fails, the path-resolution helper is broken and every other
    assertion is meaningless.
    """
    assert REPO_ROOT.is_dir(), f"Could not resolve REPO_ROOT (got {REPO_ROOT!r})"
    assert (REPO_ROOT / "backend").is_dir(), (
        f"REPO_ROOT ({REPO_ROOT}) does not contain a backend/ directory; "
        "this test is being run from the wrong tree."
    )
    assert (REPO_ROOT / "Cargo.toml").is_file(), (
        f"REPO_ROOT ({REPO_ROOT}) does not contain Cargo.toml; "
        "this test is being run from the wrong tree."
    )


# ---------------------------------------------------------------------------
# File-existence and identity tests — disambiguate the two SPEC.md files.
# ---------------------------------------------------------------------------


def test_top_level_spec_md_exists_at_repo_root() -> None:
    """MV-FR-54 deliverable: a SPEC.md at the repository root."""
    assert TOP_LEVEL_SPEC.is_file(), (
        f"Top-level SPEC.md missing at {TOP_LEVEL_SPEC}. "
        "MV-FR-54 requires this file at <repo-root>/SPEC.md "
        "(NOT docs/specs/SPEC.md — that file already exists and is preserved)."
    )


def test_inner_spec_md_is_preserved() -> None:
    """The inner docs/specs/SPEC.md must NOT be replaced by MV-FR-54."""
    assert INNER_SPEC.is_file(), (
        f"Inner SPEC.md missing at {INNER_SPEC}. "
        "MV-FR-54 must not delete or move the existing inner spec; it "
        "documents the preset library + video exporter FRs and is still canonical."
    )


def test_top_level_and_inner_spec_are_different_files() -> None:
    """Sanity: the two SPEC.md files MUST NOT be the same file.

    A previous contributor accidentally pointed a symlink at the inner spec;
    this guard prevents regression.
    """
    if not (TOP_LEVEL_SPEC.is_file() and INNER_SPEC.is_file()):
        pytest.skip("One or both SPEC.md files missing; see other tests.")
    assert TOP_LEVEL_SPEC.resolve() != INNER_SPEC.resolve(), (
        f"Top-level SPEC.md ({TOP_LEVEL_SPEC}) and inner SPEC.md ({INNER_SPEC}) "
        "resolve to the same file. They must be distinct."
    )


def test_spec_for_mv_fr_54_exists() -> None:
    """The spec doc that defines MV-FR-54 must also exist (this test enforces it)."""
    assert SPEC_FOR_MV_FR_54.is_file(), (
        f"Spec for MV-FR-54 missing at {SPEC_FOR_MV_FR_54}. "
        "Without it, MV-FR-54 has no definition."
    )


# ---------------------------------------------------------------------------
# Length floor — the spec mandates ≥ 300 lines.
# ---------------------------------------------------------------------------


def test_top_level_spec_md_has_minimum_length() -> None:
    """MV-FR-54 § 4 mandates ≥ 300 LOC."""
    if not TOP_LEVEL_SPEC.is_file():
        pytest.skip(
            "Top-level SPEC.md missing; see test_top_level_spec_md_exists_at_repo_root."
        )
    line_count = sum(1 for _ in TOP_LEVEL_SPEC.read_text(encoding="utf-8").splitlines())
    assert line_count >= MIN_LINES, (
        f"Top-level SPEC.md has {line_count} lines; minimum is {MIN_LINES}. "
        "See docs/specs/top_level_spec_md_spec.md § 4."
    )


# ---------------------------------------------------------------------------
# Section coverage — the spec mandates 10 specific headings.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("heading", REQUIRED_HEADINGS)
def test_top_level_spec_md_has_required_heading(heading: str) -> None:
    """Each of the 10 mandated sections must appear as a heading in the top-level SPEC.md."""
    if not TOP_LEVEL_SPEC.is_file():
        pytest.skip(
            "Top-level SPEC.md missing; see test_top_level_spec_md_exists_at_repo_root."
        )
    text = TOP_LEVEL_SPEC.read_text(encoding="utf-8")
    assert heading in text, (
        f"Required heading {heading!r} not found in {TOP_LEVEL_SPEC}. "
        "See docs/specs/top_level_spec_md_spec.md § 3 for the full list."
    )


# ---------------------------------------------------------------------------
# Failure-mode count — spec mandates ≥ 8 distinct failure modes.
# ---------------------------------------------------------------------------


def test_failure_modes_section_has_at_least_eight_items() -> None:
    """MV-FR-54 § 3 row 6 mandates ≥ 8 failure modes.

    Each failure mode is introduced by a level-3 ``### `` heading inside the
    ``## 6. Failure Modes`` section. We count those headings.
    """
    if not TOP_LEVEL_SPEC.is_file():
        pytest.skip(
            "Top-level SPEC.md missing; see test_top_level_spec_md_exists_at_repo_root."
        )
    text = TOP_LEVEL_SPEC.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the boundaries of section 6.
    start: int | None = None
    end: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == "## 6. Failure Modes":
            start = idx + 1
        elif (
            start is not None
            and line.startswith("## ")
            and line.strip() != "## 6. Failure Modes"
        ):
            end = idx
            break
    if start is None:
        pytest.fail("Section '## 6. Failure Modes' not found.")
    if end is None:
        end = len(lines)

    section_lines = lines[start:end]
    failure_mode_headings = [
        ln.strip() for ln in section_lines if ln.startswith("### ")
    ]
    assert len(failure_mode_headings) >= MIN_FAILURE_MODES, (
        f"Section 6 has {len(failure_mode_headings)} failure-mode headings "
        f"({failure_mode_headings}); minimum is {MIN_FAILURE_MODES}. "
        "See docs/specs/top_level_spec_md_spec.md § 3 row 6."
    )


# ---------------------------------------------------------------------------
# Anti-fabrication: distribution claims must match release.yml.
# ---------------------------------------------------------------------------


def test_distribution_section_does_not_claim_unshipped_channels_as_shipped() -> None:
    """MV-FR-54 § 5 row 3 forbids documenting channels the release workflow does not build.

    The release workflow currently ships:
      * macOS DMG (release.yml job ``macos-desktop``)
      * Linux CLI tarball of Rust binaries (release.yml job ``linux-cli``)

    It does NOT build OCI, MSI, AppImage, deb, rpm, brew, winget, or scoop.
    If any of those terms appears in the Distribution section as a SHIPPED
    channel (without an explicit non-shipped caveat), this test fails.
    """
    if not TOP_LEVEL_SPEC.is_file():
        pytest.skip(
            "Top-level SPEC.md missing; see test_top_level_spec_md_exists_at_repo_root."
        )
    text = TOP_LEVEL_SPEC.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Extract section 9.
    start: int | None = None
    end: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == "## 9. Distribution":
            start = idx + 1
        elif (
            start is not None
            and line.startswith("## ")
            and line.strip() != "## 9. Distribution"
        ):
            end = idx
            break
    if start is None:
        pytest.fail("Section '## 9. Distribution' not found.")
    if end is None:
        end = len(lines)

    section_text = "\n".join(lines[start:end]).lower()
    forbidden_terms = (
        "msi installer",
        "appimage",
        ".deb package",
        ".rpm package",
        "winget",
        "scoop",
        "oci image",
        "brew tap",
        "homebrew formula",
    )
    found = [t for t in forbidden_terms if t in section_text]
    assert not found, (
        f"Distribution section references unshipped channels as if shipped: {found}. "
        "MV-FR-54 § 5 row 3 requires that only channels actually built by "
        ".github/workflows/release.yml be documented as shipped. Either remove "
        "the claim or move it under an explicit 'aspirational / not yet shipped' "
        "subsection."
    )


# ---------------------------------------------------------------------------
# Diagnostic helper — print LOC + section list when running with -v.
# ---------------------------------------------------------------------------


def test_diagnostic_report_loc_and_sections() -> None:
    """Diagnostic: print LOC and detected headings when this test runs.

    Always passes; useful for confirming at a glance that the file matches
    the spec without manually re-reading it.
    """
    if not TOP_LEVEL_SPEC.is_file():
        pytest.skip(
            "Top-level SPEC.md missing; see test_top_level_spec_md_exists_at_repo_root."
        )
    text = TOP_LEVEL_SPEC.read_text(encoding="utf-8")
    lines = text.splitlines()
    headings = [ln.strip() for ln in lines if ln.startswith("## ")]
    print(f"\n[MEROSVIZ-MV-FR-54] {TOP_LEVEL_SPEC}")
    print(f"[MEROSVIZ-MV-FR-54] lines: {len(lines)} (floor: {MIN_LINES})")
    print(f"[MEROSVIZ-MV-FR-54] level-2 headings ({len(headings)}):")
    for h in headings:
        print(f"  - {h}")
