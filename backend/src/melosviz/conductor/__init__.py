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

from .events import (
    ALL_STATES,
    RenderEvent,
    RenderEventBus,
    STATE_DONE,
    STATE_ERROR,
    STATE_QUEUED,
    STATE_RENDERING,
    STATE_SKIPPED,
    get_bus,
    reset_bus,
)
from .orchestrator import Orchestrator
from .provenance import (
    PROVENANCE_SCHEMA_VERSION,
    ClipProvenance,
    collect_manifest_from_dir,
    provenance_path_for,
    write_provenance,
)
from .render_cache import (
    CACHE_ROOT_DIRNAME,
    RenderCache,
    SceneCacheKey,
)
from .registry import ADAPTER_REGISTRY
from .validate import (
    ALLOWED_CAMERAS,
    ALLOWED_SCENE_TYPES,
    Issue,
    SUPPORTED_SCHEMA_VERSIONS,
    ValidationReport,
    validate_storyboard,
    validate_storyboard_file,
    write_report,
)

__all__ = [
    "ADAPTER_REGISTRY",
    "ALLOWED_CAMERAS",
    "ALLOWED_SCENE_TYPES",
    "ALL_STATES",
    "CACHE_ROOT_DIRNAME",
    "ClipProvenance",
    "Issue",
    "Orchestrator",
    "PROVENANCE_SCHEMA_VERSION",
    "RenderCache",
    "RenderEvent",
    "RenderEventBus",
    "SceneCacheKey",
    "STATE_DONE",
    "STATE_ERROR",
    "STATE_QUEUED",
    "STATE_RENDERING",
    "STATE_SKIPPED",
    "SUPPORTED_SCHEMA_VERSIONS",
    "ValidationReport",
    "collect_manifest_from_dir",
    "get_bus",
    "provenance_path_for",
    "reset_bus",
    "validate_storyboard",
    "validate_storyboard_file",
    "write_provenance",
    "write_report",
]
