"""``live_stage`` conductor adapter — TouchDesigner runtime.

Registers as the ``live_stage`` scene-type adapter in the conductor's
adapter registry, replacing the stub that raised ``NotImplementedError``.

The adapter:
1. Calls :func:`~melosviz.runtime.touchdesigner.generator.generate_network`
   to produce the network-spec JSON + TD bootstrap script.
2. Optionally streams timeline events via the OSC/WS bridge when
   ``live_mode=True`` is requested.
3. Returns a :class:`TDRenderResult` describing the output files.

Conductor adapter protocol
--------------------------
The conductor calls ``adapter.render(render_spec, output_path, **kwargs)``.
The adapter MUST NOT raise ``NotImplementedError``.  It may raise
``TDRuntimeError`` for genuine failures (which the conductor logs and
routes to the next fallback — it does NOT swallow errors silently).

Usage::

    from melosviz.runtime.touchdesigner.adapter import TDAdapter

    adapter = TDAdapter()
    result  = adapter.render(spec, output_path=Path("/tmp/show"))
    print(result.network_spec_path)
    print(result.bootstrap_path)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec
    from melosviz.scene.models import ScannerSpec

logger = logging.getLogger(__name__)

__all__ = [
    "TDAdapter",
    "TDRenderResult",
    "TDRuntimeError",
]


# ---------------------------------------------------------------------------
# Result / error types
# ---------------------------------------------------------------------------


@dataclass
class TDRenderResult:
    """Output from a successful :meth:`TDAdapter.render` call.

    Attributes:
        network_spec_path: Path to the ``network_spec.json`` file.
        bootstrap_path: Path to the ``td_bootstrap.py`` file for TD.
        project_path: Path to the ``.toe.json`` stub.
        live_mode: Whether the bridge was started for live streaming.
    """

    network_spec_path: Path | None
    bootstrap_path: Path | None
    project_path: Path | None
    live_mode: bool = False


class TDRuntimeError(RuntimeError):
    """Raised when the TD adapter encounters a non-recoverable error."""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class TDAdapter:
    """TouchDesigner live-stage conductor adapter.

    Drop-in replacement for the ``live_stage`` stub in the adapter registry.
    Generates a TD network spec + bootstrap script from a RenderSpec v2, with
    an optional live bridge for real-time event streaming.

    Args:
        scanner_specs: Optional list of
            :class:`~melosviz.scene.models.ScannerSpec` objects.  When
            absent, two default disco-ball scanners are generated.
        bridge_config: :class:`~melosviz.runtime.touchdesigner.bridge.BridgeConfig`
            for live mode.  When None, a default config (localhost, ports
            7700/7701) is used if ``live_mode=True`` is requested.
    """

    #: Key used in the conductor adapter registry.
    scene_type: str = "live_stage"

    def __init__(
        self,
        scanner_specs: list[ScannerSpec] | None = None,
        bridge_config: Any | None = None,
    ) -> None:
        self._scanner_specs = scanner_specs
        self._bridge_config = bridge_config

    def render(
        self,
        render_spec: RenderSpec,
        *,
        output_path: Path | str,
        live_mode: bool = False,
        **_kwargs: Any,
    ) -> TDRenderResult:
        """Generate the TD runtime from a RenderSpec v2.

        Args:
            render_spec: A fully-populated RenderSpec v2 object.
            output_path: Directory where network_spec.json, td_bootstrap.py,
                and runtime.toe.json are written.
            live_mode: If True, instantiate and start the OSC/WS bridge
                (for festival live mode).  The bridge streams timeline events
                asynchronously and is NOT blocking.
            **_kwargs: Ignored extra kwargs (for conductor forward compat).

        Returns:
            :class:`TDRenderResult` describing the output files.

        Raises:
            TDRuntimeError: On any generation failure (never swallows silently).
        """
        from melosviz.runtime.touchdesigner.generator import generate_network

        output_dir = Path(output_path)

        logger.info(
            "TDAdapter.render: generating network spec → %s (live_mode=%s)",
            output_dir,
            live_mode,
        )

        try:
            result = generate_network(
                render_spec,
                scanner_specs=self._scanner_specs,
                output_dir=output_dir,
            )
        except Exception as exc:
            raise TDRuntimeError(
                f"TouchDesigner network generation failed: {exc}"
            ) from exc

        # Start the live bridge if requested
        started_live = False
        if live_mode:
            try:
                self._start_bridge(render_spec)
                started_live = True
            except Exception as exc:
                # Log but do NOT re-raise — generation succeeded; bridge is
                # best-effort in live mode (TD may not be running yet).
                logger.warning("Live bridge start failed (non-fatal): %s", exc)

        return TDRenderResult(
            network_spec_path=result.network_spec_path,
            bootstrap_path=result.bootstrap_path,
            project_path=result.project_path,
            live_mode=started_live,
        )

    def _start_bridge(self, render_spec: RenderSpec) -> None:
        """Start the OSC/WS bridge in a background thread."""
        import threading

        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        cfg = self._bridge_config
        if cfg is None:
            cfg = BridgeConfig()

        bridge = TDBridge(cfg)

        def _run() -> None:
            try:
                bridge.stream_render_spec(render_spec, realtime=True)
            except Exception as exc:
                logger.error("Bridge streaming error: %s", exc)
            finally:
                bridge.close()

        thread = threading.Thread(target=_run, daemon=True, name="melosviz-td-bridge")
        thread.start()
        logger.info("TD live bridge started on thread %s", thread.name)
