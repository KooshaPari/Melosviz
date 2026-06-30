"""TouchDesigner runtime generator for MelosViz.

This sub-package provides:

* :mod:`.generator` — builds a serialisable network-spec JSON (operator
  graph) from a :class:`~melosviz.analysis.models.RenderSpec` v2.
* :mod:`.bootstrap` — the TD-side Python bootstrap script rendered as a
  string; when pasted into a TD Text DAT and executed inside TouchDesigner
  it constructs the live node graph from the network-spec JSON.
* :mod:`.bridge` — async OSC/WebSocket bridge that streams RenderSpec
  :class:`~melosviz.analysis.models.TimelineEvent` objects to TD in
  real time (festival live mode).
* :mod:`.overrides` — round-trip helpers: export TD param edits to
  ``overrides.yaml`` (via :mod:`melosviz.conductor.overrides`) and
  re-apply them to a generated network spec.
* :mod:`.adapter` — the ``live_stage`` conductor adapter (replaces the
  stub that raises ``NotImplementedError``).

Quick usage::

    from melosviz.runtime.touchdesigner import generate_network, TDAdapter

    spec   = ...  # RenderSpec v2
    result = generate_network(spec, output_dir=Path("/tmp/show"))
    # result.network_spec_path  -> JSON describing the operator graph
    # result.bootstrap_path     -> TD-side Python bootstrap (.py)
    # result.project_path       -> .toe project stub JSON

    # Live mode
    adapter = TDAdapter()
    adapter.render(spec, output_path=Path("/tmp/preview.toe"))
"""

from melosviz.runtime.touchdesigner.adapter import TDAdapter, TDRenderResult
from melosviz.runtime.touchdesigner.generator import (
    NetworkSpec,
    OperatorGroup,
    OperatorNode,
    generate_network,
)

__all__ = [
    "TDAdapter",
    "TDRenderResult",
    "NetworkSpec",
    "OperatorGroup",
    "OperatorNode",
    "generate_network",
]
