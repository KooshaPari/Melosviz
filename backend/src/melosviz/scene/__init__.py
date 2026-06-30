"""Hybrid scene representation-domain models and scanner evaluator.

P4 hybrid-scene MVP: a scene where representation DOMAINS switch/blend
over space+time, driven by a disco-ball SCANNER that is beat-locked.

Public API::

    from melosviz.scene.models import (
        SceneSpec, ScannerSpec, MaterialSpec, TransitionSpec,
        ScannerType, FalloffType, OcclusionMode, Domain,
    )
    from melosviz.scene.scanner import evaluate_scanner

See models.py for pydantic schema, scanner.py for the pure-Python evaluator,
and blender_scene.py for the Blender adapter wiring.
"""

from melosviz.scene.models import (
    Domain,
    FalloffType,
    MaterialSpec,
    OcclusionMode,
    ScannerSpec,
    ScannerType,
    SceneSpec,
    TransitionSpec,
)
from melosviz.scene.scanner import ScannerPose, ChannelMaskFrame, evaluate_scanner

__all__ = [
    "Domain",
    "FalloffType",
    "MaterialSpec",
    "OcclusionMode",
    "ScannerSpec",
    "ScannerType",
    "SceneSpec",
    "TransitionSpec",
    "ScannerPose",
    "ChannelMaskFrame",
    "evaluate_scanner",
]
