"""Regression: provenance sidecars must never escape the render output dir.

Incident (commit ``6539d2b``): two sidecars were committed with names taken
from a MagicMock repr::

    backend/<MagicMock name='mock().render().files.__getitem__()' id='4477427152'>.provenance.json

``<``, ``>`` and ``:`` are illegal in Windows paths, so ``git clone`` on
Windows aborts with ``fatal: unable to checkout working tree`` and leaves the
whole worktree 672 files short (fixed forward in ``d501aa2``).

Two mechanisms produced that name, and both are pinned here:

1. ``Orchestrator.render`` extracted the artifact with
   ``hasattr(result, "files")``, which is true for *any* ``Mock``, and then
   stringified it. A repr is not a path.
2. The extracted value had no directory component, so
   :func:`~melosviz.conductor.provenance.provenance_path_for` resolved it
   against the process CWD and wrote test output into the repository itself.

Acceptance: only real path-like adapter results become ``artifact_path``, and
every sidecar lands inside the render output directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.orchestrator import Orchestrator
from melosviz.conductor.provenance import provenance_path_for

MAGICMOCK_NAME = "<MagicMock name='mock().render().files.__getitem__()' id='4477427152'>"


def _spec() -> dict[str, Any]:
    return {
        "scene_segments": [
            {"scene_index": 0, "scene_name": "s0", "scene_type": "video_export"},
        ]
    }


def _orch(tmp_path: Path) -> Orchestrator:
    return Orchestrator(
        output_dir=tmp_path / "out",
        skip_assembly=True,
        auto_offline=False,
    )


def _mock_adapter_cls(render_return: Any) -> MagicMock:
    """Adapter class double whose render() returns `render_return`."""
    cls = MagicMock()
    cls.__name__ = "MockVideoExport"
    cls.__module__ = "tests.conductor.test_provenance_containment"
    instance = MagicMock()
    instance.render.return_value = render_return
    cls.return_value = instance
    return cls


class _RelativePathAdapter:
    """Adapter that reports a relative artifact path (no directory part)."""

    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        return [Path("clip.mp4")]


def _cwd_sidecars() -> list[str]:
    return sorted(p.name for p in Path.cwd().glob("*.provenance.json"))


def test_mock_result_writes_no_sidecar_into_cwd(tmp_path: Path, monkeypatch) -> None:
    """A Mock repr must not become a filename in the process CWD."""
    monkeypatch.setitem(
        registry_mod.ADAPTER_REGISTRY,
        "video_export",
        _mock_adapter_cls(MagicMock()),
    )
    before = _cwd_sidecars()
    _orch(tmp_path).render(_spec())
    assert _cwd_sidecars() == before, (
        "render wrote provenance sidecars into the process CWD "
        f"(this is how test output reached the repo root): {_cwd_sidecars()}"
    )


def test_mock_result_sidecar_is_contained_in_output_dir(tmp_path: Path, monkeypatch) -> None:
    """The traceability sidecar still gets written, but inside the output dir."""
    monkeypatch.setitem(
        registry_mod.ADAPTER_REGISTRY,
        "video_export",
        _mock_adapter_cls(MagicMock()),
    )
    _orch(tmp_path).render(_spec())
    sidecars = sorted((tmp_path / "out").rglob("*.provenance.json"))
    assert len(sidecars) == 1, f"expected exactly one contained sidecar, got {sidecars}"


def test_relative_artifact_is_resolved_inside_output_dir(tmp_path: Path, monkeypatch) -> None:
    """`clip.mp4` must not resolve to `<cwd>/clip.mp4.provenance.json`."""
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "video_export", _RelativePathAdapter)
    _orch(tmp_path).render(_spec())
    stray = Path.cwd() / "clip.mp4.provenance.json"
    assert not stray.exists(), f"sidecar escaped to {stray}"
    contained = sorted((tmp_path / "out").rglob("clip.mp4.provenance.json"))
    assert len(contained) == 1, f"expected a contained sidecar, got {contained}"


def test_pathless_result_is_labelled_unavailable(tmp_path: Path, monkeypatch) -> None:
    """No usable artifact path is an explicit outcome, not a fabricated path."""
    monkeypatch.setitem(
        registry_mod.ADAPTER_REGISTRY,
        "video_export",
        _mock_adapter_cls(MagicMock()),
    )
    result = _orch(tmp_path).render(_spec())
    done = [e for e in result.events if getattr(e, "state", "") == "done"]
    assert done, "expected a done event"
    assert done[0].artifact_path == "", (
        f"a Mock repr was surfaced as an artifact path: {done[0].artifact_path!r}"
    )
    sidecar = next((tmp_path / "out").rglob("*.provenance.json"))
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["extra"]["outcome"] == "unavailable", (
        f"unexpected outcome label: {payload['extra']!r}"
    )


@pytest.mark.parametrize(
    "name",
    [
        MAGICMOCK_NAME + ".provenance.json",
        "a:b.png",
        "a|b.png",
        "a?b.png",
        "a*b.png",
        'a"b.png',
    ],
)
def test_provenance_path_for_rejects_non_portable_names(name: str) -> None:
    """A name that cannot exist on Windows must fail loudly, not be written."""
    with pytest.raises(ValueError):
        provenance_path_for(name)


def test_provenance_path_for_still_accepts_normal_names(tmp_path: Path) -> None:
    assert provenance_path_for(tmp_path / "scene_0000.png").name == (
        "scene_0000.png.provenance.json"
    )
    assert provenance_path_for("/some/dir/scene.mp4").name == ("scene.mp4.provenance.json")
