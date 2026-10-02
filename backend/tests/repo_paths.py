"""Repository-root discovery for tests that assert on repo-level files.

This lives in its own module rather than in ``conftest.py`` for one reason:
importability. ``from conftest import find_repo_root`` resolves only under
pytest's default ``prepend`` import mode, and only because ``backend/tests/``
has no ``__init__.py`` so pytest inserts that directory on ``sys.path`` and
imports the file as top-level module ``conftest``. Two routine changes break
all seven call sites at collection time, and break them together:

  * adding ``backend/tests/__init__.py``, after which pytest imports this
    directory's modules as ``tests.conftest`` and the bare name disappears;
  * running with ``--import-mode=importlib``, which performs no ``sys.path``
    insertion at all.

The failure mode is a collection error across seven modules simultaneously,
which surfaces in CI rather than locally, and it lands on exactly the commit
that centralised every repo-level path lookup on this one symbol.

``backend/pyproject.toml`` declares ``pythonpath = ["src", "tests"]`` under
``[tool.pytest.ini_options]``. That ini option inserts into ``sys.path``
regardless of import mode, so ``from repo_paths import find_repo_root`` resolves
under ``prepend``, ``importlib`` and ``append`` alike, and survives adding
``tests/__init__.py``. ``conftest.py`` re-exports the symbol for compatibility
with anything that already reaches for it there.

Putting ``tests`` on ``pythonpath`` is not new exposure: under the default
``prepend`` mode pytest already inserts this directory at ``sys.path[0]`` for
every test module that lives directly in it. The sibling package names here
(``cli``, ``render``, ``llm``, ``fixtures``, ...) are exactly the ones that
could shadow, and they are already shadowing today by that mechanism. Making it
explicit and mode-independent changes nothing about which name wins; it only
stops the answer depending on the import mode.

mutmut copies this file along with the rest of the tree (``also_copy`` unions
``tests/`` by default), so mutant runs resolve it the same way baseline runs do.
"""

from __future__ import annotations

from pathlib import Path

#: Markers that only the repository root carries, as a pair. ``Cargo.toml`` is
#: the Rust workspace root; ``backend/`` is this package. Both are needed
#: because ``pyproject.toml`` alone is ambiguous -- it exists at the repo root
#: AND under ``backend/``.
_ROOT_MARKERS = ("Cargo.toml", "backend")

#: How far up to walk before giving up. Bounded on purpose: an unbounded walk
#: on a pathologically symlinked tree would keep climbing, and CI does nest
#: deeper than a human would guess.
_MAX_WALK_DEPTH = 8


def find_repo_root(start: Path | str | None = None) -> Path:
    """Return the repository root, from any nesting depth.

    Tests that assert on repository-level files must not compute their location
    with a fixed ``parents[N]``. The depth is only correct when pytest happens
    to run from ``backend/``. mutmut copies the tree into ``backend/mutants/``
    and runs pytest from there, so ``tests/`` sits one level deeper and every
    such path silently shifts: ``parents[2]`` lands on ``backend/`` instead of
    the repo root, which produced ``backend/backend`` and broke
    ``test_e2e_3min_pipeline.py`` (run 36956679068).

    Instead walk up looking for the marker pair described at module level.

    Args:
        start: Directory or file to start from. Defaults to this file, so a
            caller that does not care can call it with no arguments. Accepts
            the caller's ``__file__`` unchanged; a file path is fine because
            only the containing directory is inspected.

    Raises:
        RuntimeError: When no ancestor of ``start`` carries both markers.
            Returning a fallback would be worse than failing: by the time the
            walk gives up, ``cur`` is the last ancestor reached, normally ``/``
            or one of its ancestors rather than the backend directory, so every
            caller would build repository-level paths (``REPO_ROOT / "docs" /
            "intent" / "MelosViz.md"``, ``REPO_ROOT / ".github" /
            "workflows"``, ``BACKEND / "src"``) from a root that has none of
            them, and a missing marker would surface as a confusing
            ``FileNotFoundError`` instead of the structural error it is.
    """
    cur = (Path(start) if start is not None else Path(__file__)).resolve()
    if cur.is_file():
        cur = cur.parent
    for _ in range(_MAX_WALK_DEPTH):
        if all((cur / marker).exists() for marker in _ROOT_MARKERS):
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    raise RuntimeError(
        f"repo root not found: no ancestor of {cur!r} has both "
        f"{' and '.join(_ROOT_MARKERS)} (walked up to "
        f"{_MAX_WALK_DEPTH} levels)"
    )