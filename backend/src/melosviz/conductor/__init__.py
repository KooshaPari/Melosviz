"""Conductor — multi-tool render orchestrator.

The conductor routes a :class:`~melosviz.analysis.models.RenderSpec` v2 to
the correct pro-tool adapter based on the scene type of each
:class:`~melosviz.analysis.models.SceneSegment`.

Adapter registry
----------------
``ADAPTER_REGISTRY`` maps scene-type strings to adapter *classes*
(not instances), following the same pattern as the TD adapter.

Scene types
-----------

+------------------------------+------------------------+-----------+
| Scene type key               | Adapter                | Tier      |
+==============================+========================+===========+
| ``generative_asset``         | FireflyAdapter         | GOLD      |
+------------------------------+------------------------+-----------+
| ``motion_graphics_beat_sync``| AEAdapter              | GOLD      |
+------------------------------+------------------------+-----------+
| ``assembly_encode``          | MEAdapter              | GOLD      |
+------------------------------+------------------------+-----------+
| ``procedural_3d_animation``  | BlenderExporter (wrap) | GOLD      |
+------------------------------+------------------------+-----------+
| ``live_stage``               | TDAdapter              | GOLD      |
+------------------------------+------------------------+-----------+
| ``video_export``             | VideoExportAdapter     | SILVER    |
+------------------------------+------------------------+-----------+

The orchestrator calls ``adapter.render(spec, output_path=...)`` for each
scene type present in the spec.  The final assembly step (``assembly_encode``)
is always triggered last, after all per-segment renders complete.
"""

from __future__ import annotations

from .orchestrator import Orchestrator
from .registry import ADAPTER_REGISTRY

__all__ = ["ADAPTER_REGISTRY", "Orchestrator"]
