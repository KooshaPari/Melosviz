"""Pytest configuration for the MelosViz backend test suite.

The CLI/i18n layer caches its resolved :data:`melosviz.i18n._current` locale in a
module-level global. Without an isolation hook, the i18n tests can leak Spanish
strings (or any other locale) into unrelated CLI tests that assert on English
output such as the ``_cmd_diff`` family in ``test_qgate_backfill.py``.

This conftest installs an :func:`autouse` fixture that resets the cached locale
before every test, so each test starts from the default behaviour driven only
by the ``MELOSVIZ_LOCALE`` environment variable.

It also exposes :func:`find_repo_root` for the tests that need to reach
repository-level files (docs, workflows, the Cargo workspace).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def find_repo_root(start: Path | str | None = None) -> Path:
    """Return the repository root, from any nesting depth.

    Tests that assert on repository-level files must not compute their location
    with a fixed ``parents[N]``. The depth is only correct when pytest happens
    to run from ``backend/``. mutmut copies the tree into ``backend/mutants/``
    and runs pytest from there, so ``tests/`` sits one level deeper and every
    such path silently shifts: ``parents[2]`` lands on ``backend/`` instead of
    the repo root, which produced ``backend/backend`` and broke
    ``test_e2e_3min_pipeline.py`` (run 36956679068).

    Instead walk up looking for a marker pair that only the repo root has:
    ``Cargo.toml`` (the Rust workspace root) together with ``backend/``. Using
    the Rust marker avoids ambiguity, since ``pyproject.toml`` exists under
    both the root and ``backend/``.
    """
    cur = (Path(start) if start is not None else Path(__file__)).resolve()
    for _ in range(8):  # bounded walk; CI can nest deeper than expected
        if (cur / "Cargo.toml").is_file() and (cur / "backend").is_dir():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    # Nothing matched (a shallow export without the Rust workspace). Fall back
    # to the backend directory itself, which keeps callers working with a stable
    # absolute path instead of raising at import time.
    return cur


@pytest.fixture(autouse=True)
def _reset_i18n_locale() -> None:
    """Reset ``melosviz.i18n._current`` before each test.

    Importing inside the fixture keeps this conftest importable on environments
    where ``melosviz`` hasn't been installed yet (e.g. when CI is running with
    ``--collect-only``).
    """
    try:
        from melosviz import i18n
    except Exception:
        return
    i18n._current = None
