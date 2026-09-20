"""Pytest configuration for the MelosViz backend test suite.

The CLI/i18n layer caches its resolved :data:`melosviz.i18n._current` locale in a
module-level global. Without an isolation hook, the i18n tests can leak Spanish
strings (or any other locale) into unrelated CLI tests that assert on English
output such as the ``_cmd_diff`` family in ``test_qgate_backfill.py``.

This conftest installs an :func:`autouse` fixture that resets the cached locale
before every test, so each test starts from the default behaviour driven only
by the ``MELOSVIZ_LOCALE`` environment variable.
"""

from __future__ import annotations

import pytest


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
