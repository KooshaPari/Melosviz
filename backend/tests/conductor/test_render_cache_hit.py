"""Regression: a render-cache hit must be able to emit its done event.

``Orchestrator.render`` short-circuits a scene whose artifact is already in the
render cache and builds the ``done`` :class:`RenderEvent` inline. That inline
construction passed ``started_at`` and ``finished_at`` to ``RenderEvent``, which
declares neither field, and called ``_now_ms()``, which is not defined anywhere
in the module, so the branch could only raise.

The branch was also unreachable in practice, for a separate reason: the
orchestrator builds ``RenderCache(self._output_dir / "_render_cache")`` without
creating that directory, so every ``store`` fails with ``ENOENT`` into a
``logger.debug`` and the cache is never populated::

    DEBUG melosviz.conductor.orchestrator: render cache store skipped:
    [Errno 2] No such file or directory: '...\\out\\_render_cache\\<fp>.bin'

This test therefore pre-creates the cache directory so the branch is actually
exercised. Fixing the missing directory is deliberate follow-up work, not an
oversight: a cache hit currently returns a ``<fingerprint>.bin`` artifact path
and skips the provenance sidecar and outcome label entirely, so activating the
cache changes what downstream consumers and release acceptance observe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from melosviz.conductor import registry as registry_mod
from melosviz.conductor.orchestrator import Orchestrator


class _FileAdapter:
    """Adapter that writes a real clip and reports it, so `store` can cache it."""

    def render(self, render_spec: Any, **kwargs: Any) -> list[Path]:
        out = Path(str(kwargs["output_path"]))
        out.mkdir(parents=True, exist_ok=True)
        clip = out / "clip.mp4"
        clip.write_bytes(b"\x00" * 32)
        return [clip]


def _spec() -> dict[str, Any]:
    return {
        "scene_segments": [{"scene_index": 0, "scene_name": "s0", "scene_type": "comfyui_image"}]
    }


def _orchestrator(tmp_path: Path) -> Orchestrator:
    out = tmp_path / "out"
    # The orchestrator does not create this itself; see the module docstring.
    (out / "_render_cache").mkdir(parents=True, exist_ok=True)
    return Orchestrator(output_dir=out, skip_assembly=True, auto_offline=False)


def test_cache_hit_emits_done_event_without_raising(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(registry_mod.ADAPTER_REGISTRY, "comfyui_image", _FileAdapter)
    orch = _orchestrator(tmp_path)
    orch.render(_spec())

    result = orch.render(_spec())
    done = [e for e in result.events if getattr(e, "state", "") == "done"]
    assert done, (
        "second render produced no done event: "
        f"{[(getattr(e, 'state', None), getattr(e, 'error', '')) for e in result.events]!r}"
    )
    assert done[0].extras.get("from_cache") is True, (
        "expected the second render to be served from the cache, got "
        f"extras={done[0].extras!r} backend={done[0].backend!r}"
    )
    assert done[0].artifact_path, "cached done event must carry the cached artifact path"
    assert Path(done[0].artifact_path).exists(), (
        f"cached artifact does not exist: {done[0].artifact_path!r}"
    )
