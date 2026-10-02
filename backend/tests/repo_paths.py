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

The function is called at module scope by all seven call sites, so a checkout
missing the markers raises during collection rather than at test time. That is
intended -- see the note on ``find_repo_root`` -- and is why the raise names the
types it checked.

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
#:
#: The pair is type-specific, not merely present, and that is the whole point of
#: matching on both. A previous revision used ``all(... .exists() ...)``, which
#: accepts a *directory* named ``Cargo.toml`` or a *file* named ``backend`` and
#: so stops matching the thing this docstring describes. Those two shapes do not
#: occur in this repo, but a checkout of the wrong directory, a partial export, or
#: a stray ``backend`` file sitting next to some unrelated ``Cargo.toml`` would
#: satisfy the loose check and hand every caller a root that has neither the Rust
#: workspace nor this package -- the silent-wrong-directory failure this function
#: exists to rule out.
_ROOT_MARKERS = (("Cargo.toml", "is_file"), ("backend", "is_dir"))

#: How far up to walk before giving up. Bounded on purpose: an unbounded walk
#: on a pathologically symlinked tree would keep climbing, and CI does nest
#: deeper than a human would guess.
_MAX_WALK_DEPTH = 8


def _has_root_markers(directory: Path) -> bool:
    """Whether ``directory`` carries the full marker pair, with correct types."""
    return all(getattr(directory / name, kind)() for name, kind in _ROOT_MARKERS)


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

    Note:
        This raises at *import* time for every caller, because all seven call
        sites evaluate ``find_repo_root(__file__)`` at module scope rather than
        inside a fixture. That is deliberate and it is the point: a repo-root
        lookup is a precondition for the module defining its constants
        (``REPO`` / ``REPO_ROOT``), so it cannot be deferred to test time without
        making those constants lazy.

        The consequence to be aware of: on a shallow export or a stray checkout
        that lacks ``Cargo.toml``, importing any of those seven modules raises
        ``RuntimeError`` during collection, which pytest reports as one
        collection error per module rather than a single clear failure. That is
        the trade for a module whose import succeeds anywhere the repository
        layout is intact, under any pytest import mode -- see the module
        docstring. It is a loud, early, structural error, which is the intended
        behaviour; it is just reported seven times over.
    """
    cur = (Path(start) if start is not None else Path(__file__)).resolve()
    if cur.is_file():
        cur = cur.parent
    for _ in range(_MAX_WALK_DEPTH):
        if _has_root_markers(cur):
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    raise RuntimeError(
        f"repo root not found: no ancestor of {cur!r} has both "
        f"{' and '.join(name for name, _ in _ROOT_MARKERS)} "
        f"(Cargo.toml as a file, backend/ as a directory; walked up to "
        f"{_MAX_WALK_DEPTH} levels)"
    )
