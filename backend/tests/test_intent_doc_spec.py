"""Validator for the MelosViz intent document (MV-FR-52).

This test enforces the contract captured in
``docs/specs/intent_doc_spec.md`` (MV-FR-52). The intent document lives at
``<repo-root>/docs/intent/MelosViz.md`` and must:

  1. Exist on disk.
  2. Contain at least 50 non-empty lines of content (LOC threshold).
  3. Contain the 5 mandated section headings, in order, each prefixed by the
     corresponding section number (1-5).
  4. List all 5 named stakeholder roles in section 2.
  5. Enumerate at least 5 non-goals in section 3.
  6. Describe at least 3 failure modes in section 4.
  7. Name at least 3 KPIs in section 5.

The test is intentionally RED before ``docs/intent/MelosViz.md`` is created
and GREEN once the artifact satisfies the contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INTENT_DOC = REPO_ROOT / "docs" / "intent" / "MelosViz.md"
SPEC_DOC = REPO_ROOT / "docs" / "specs" / "intent_doc_spec.md"
MIN_LOC = 50

# (Section number, human-readable name, regex that the H2 must match)
REQUIRED_SECTIONS: list[tuple[int, str, re.Pattern[str]]] = [
    (1, "Project Intent", re.compile(r"^##\s*1\.\s*Project Intent\s*$", re.MULTILINE)),
    (2, "Stakeholders", re.compile(r"^##\s*2\.\s*Stakeholders\s*$", re.MULTILINE)),
    (3, "Non-Goals", re.compile(r"^##\s*3\.\s*Non-Goals\s*$", re.MULTILINE)),
    (4, "Failure Modes", re.compile(r"^##\s*4\.\s*Failure Modes\s*$", re.MULTILINE)),
    (5, "Success Metrics", re.compile(r"^##\s*5\.\s*Success Metrics\s*$", re.MULTILINE)),
]

REQUIRED_STAKEHOLDERS = [
    "Producer",
    "Audio Creator",
    "Visual Artist",
    "Developer",
    "Operator",
]


def _section_slice(text: str, section_num: int) -> str:
    """Return the body of section ``section_num`` (between its H2 and the next H2).

    Returns an empty string if the section heading is not found.
    """
    start_pattern = REQUIRED_SECTIONS[section_num - 1][2]
    match = start_pattern.search(text)
    if match is None:
        return ""
    start = match.end()
    # Find the next H2 (any level-2 heading) at or after ``start``.
    next_h2 = re.search(r"^##\s", text[start:], re.MULTILINE)
    end = start + next_h2.start() if next_h2 else len(text)
    return text[start:end]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def intent_text() -> str:
    """Read the intent document once per module; skip everything if it is missing."""
    if not INTENT_DOC.exists():
        pytest.skip(f"Intent document not yet created at {INTENT_DOC}")
    return INTENT_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def non_empty_lines(intent_text: str) -> list[str]:
    return [ln for ln in intent_text.splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# Tests — MV-FR-52 contract
# ---------------------------------------------------------------------------


def test_intent_doc_exists() -> None:
    """MV-FR-52 contract clause 1: file must exist."""
    assert INTENT_DOC.exists(), (
        f"Intent document missing at {INTENT_DOC}. "
        f"Author per docs/specs/intent_doc_spec.md (MV-FR-52)."
    )


def test_intent_doc_spec_exists() -> None:
    """Sanity: the spec this test enforces must itself be present."""
    assert SPEC_DOC.exists(), f"Spec missing at {SPEC_DOC} (MV-FR-52)"


def test_intent_doc_min_loc(non_empty_lines: list[str]) -> None:
    """MV-FR-52 contract clause 2: ≥ 50 non-empty lines."""
    assert len(non_empty_lines) >= MIN_LOC, (
        f"Intent doc has {len(non_empty_lines)} non-empty lines; "
        f"need at least {MIN_LOC} per docs/specs/intent_doc_spec.md."
    )


@pytest.mark.parametrize(
    "section_num,section_name,_pattern",
    REQUIRED_SECTIONS,
    ids=[f"section-{n}-{name.lower().replace(' ', '-')}" for n, name, _ in REQUIRED_SECTIONS],
)
def test_intent_doc_has_section(
    intent_text: str, section_num: int, section_name: str, _pattern: re.Pattern[str]
) -> None:
    """MV-FR-52 contract clause 3: each section H2 must be present and well-formed."""
    pattern = REQUIRED_SECTIONS[section_num - 1][2]
    assert pattern.search(intent_text), (
        f"Section {section_num} ('{section_name}') not found in {INTENT_DOC.name}. "
        f"Required heading regex: {pattern.pattern!r}"
    )


def test_intent_doc_sections_in_order(intent_text: str) -> None:
    """MV-FR-52 contract clause 3: sections must appear in the order 1, 2, 3, 4, 5."""
    positions: list[int] = []
    for _, _, pattern in REQUIRED_SECTIONS:
        m = pattern.search(intent_text)
        positions.append(m.start() if m else -1)
    assert all(p >= 0 for p in positions), (
        f"Missing section(s) in {INTENT_DOC.name}: positions={positions}"
    )
    assert positions == sorted(positions), (
        f"Sections out of order in {INTENT_DOC.name}: positions={positions}"
    )


def test_intent_doc_lists_all_stakeholders(intent_text: str) -> None:
    """MV-FR-52 contract clause 4: section 2 must list all 5 named stakeholders."""
    body = _section_slice(intent_text, 2)
    missing = [name for name in REQUIRED_STAKEHOLDERS if name not in body]
    assert not missing, (
        f"Stakeholder(s) missing from §2 of {INTENT_DOC.name}: {missing}. "
        f"Required: {REQUIRED_STAKEHOLDERS}."
    )


def test_intent_doc_has_at_least_5_non_goals(intent_text: str) -> None:
    """MV-FR-52 contract clause 5: section 3 must enumerate ≥ 5 non-goals."""
    body = _section_slice(intent_text, 3)
    # Accept Markdown list bullets ("- " or "1. ", "2. ", ...) — count either.
    bullets = re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S", body, re.MULTILINE)
    assert len(bullets) >= 5, (
        f"Section 3 has {len(bullets)} non-goal bullet(s); need ≥ 5. "
        f"See docs/specs/intent_doc_spec.md (MV-FR-52)."
    )


def test_intent_doc_has_at_least_3_failure_modes(intent_text: str) -> None:
    """MV-FR-52 contract clause 6: section 4 must describe ≥ 3 failure modes."""
    body = _section_slice(intent_text, 4)
    bullets = re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S", body, re.MULTILINE)
    assert len(bullets) >= 3, (
        f"Section 4 has {len(bullets)} failure-mode bullet(s); need ≥ 3. "
        f"See docs/specs/intent_doc_spec.md (MV-FR-52)."
    )


def test_intent_doc_has_at_least_3_kpis(intent_text: str) -> None:
    """MV-FR-52 contract clause 7: section 5 must name ≥ 3 KPIs."""
    body = _section_slice(intent_text, 5)
    bullets = re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S", body, re.MULTILINE)
    assert len(bullets) >= 3, (
        f"Section 5 has {len(bullets)} KPI bullet(s); need ≥ 3. "
        f"See docs/specs/intent_doc_spec.md (MV-FR-52)."
    )


def test_intent_doc_references_mv_fr_52(intent_text: str) -> None:
    """The intent doc should declare its traceability ID at least once."""
    assert "MV-FR-52" in intent_text, (
        f"{INTENT_DOC.name} must reference its traceability ID 'MV-FR-52' at least once."
    )