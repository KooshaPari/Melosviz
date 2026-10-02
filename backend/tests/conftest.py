"""Pytest configuration for the MelosViz backend test suite.

The CLI/i18n layer caches its resolved :data:`melosviz.i18n._current` locale in a
module-level global. Without an isolation hook, the i18n tests can leak Spanish
strings (or any other locale) into unrelated CLI tests that assert on English
output such as the ``_cmd_diff`` family in ``test_qgate_backfill.py``.

This conftest installs an :func:`autouse` fixture that resets the cached locale
before every test, so each test starts from the default behaviour driven only
by the ``MELOSVIZ_LOCALE`` environment variable.

It also re-exports :func:`find_repo_root` for tests that need to reach
repository-level files (docs, workflows, the Cargo workspace). The
implementation lives in ``tests/repo_paths.py`` rather than here: ``from
conftest import ...`` resolves only under pytest's default ``prepend`` import
mode, so binding seven modules to this file would break them together if
``tests/__init__.py`` were ever added or ``--import-mode=importlib`` used. The
re-export stays so existing call sites keep working.
"""

from __future__ import annotations

import pytest

from repo_paths import find_repo_root

__all__ = ["find_repo_root"]


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
