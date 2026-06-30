"""Pydantic models for the hybrid-scene representation-domain system.

These models are the SOURCE-OF-TRUTH spec for P4.  They describe:

* :class:`SceneSpec` — what assets exist and which domains each supports.
* :class:`ScannerSpec` — the disco-ball / volumetric mask generator.
* :class:`MaterialSpec` — per-domain look families.
* :class:`TransitionSpec` — declarative mask→domain opacity/material mappings.

YAML shapes are taken directly from the operator exploration
(ChatGPT-Programmable Music Visualizers.md §"Representation model",
§"Scanner model", §"Material system").

Design
------
* No renderer import here — models are renderer-agnostic.
* All fields have sane defaults so callers can construct minimal specs.
* Pydantic v2 compatible (uses ``model_config`` + ``Field``).
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Domain(str, Enum):
    """Representation domains the scene can switch/blend between."""

    PHOTO = "photo"          # equirect 360 / projected video
    MESH = "mesh"            # triangle mesh / wireframe / depth shell
    SPLAT = "splat"          # Gaussian splat / point-cloud proxy
    PERFORMER = "performer"  # roto-isolated subject passes
    FX = "fx"               # particles / edge maps / stylized shader


class ScannerType(str, Enum):
    """Scanner geometry type."""

    ROTATING_CONE = "rotating_cone"
    SPHERE = "sphere"
    SPLINE = "spline"


class FalloffType(str, Enum):
    """Edge falloff shape for the scanner mask."""

    LINEAR = "linear"
    SMOOTHSTEP = "smoothstep"
    COSINE = "cosine"


class OcclusionMode(str, Enum):
    """How the scanner handles scene depth/occlusion."""

    NONE = "none"             # no occlusion — mask ignores depth
    SCENE_DEPTH = "scene_depth"  # use scene depth map to attenuate behind objects
    PROXY = "proxy"           # use a simplified proxy mesh


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ScannerRotation(BaseModel):
    """BPM-locked rotation parameters."""

    bpm_locked: bool = True
    beats_per_rotation: float = Field(default=8.0, gt=0.0)
    phase_offset: float = Field(default=0.0, ge=0.0, lt=1.0)


class ScannerNoise(BaseModel):
    """Noise applied to scanner edges and beat pulses."""

    edge_wobble: float = Field(default=0.08, ge=0.0, le=1.0)
    beat_pulse_gain: float = Field(default=0.35, ge=0.0, le=2.0)


class ScannerSpec(BaseModel):
    """A moving volumetric mask generator (the 'disco-ball scanner').

    The scanner emits write-channel values into spatial masks over time.
    Those channels are consumed by :class:`TransitionSpec` to select and
    blend representation domains.

    YAML example::

        scanner_id: disco_main
        type: rotating_cone
        origin:
          anchor: scene.discoball_01
        shape:
          cone_angle_deg: 18
          falloff: smoothstep
          max_distance: 22.0
        rotation:
          bpm_locked: true
          beats_per_rotation: 8
          phase_offset: 0.15
        noise:
          edge_wobble: 0.08
          beat_pulse_gain: 0.35
        occlusion_mode: scene_depth
        write_channels:
          - reveal_splat
          - hide_photo
          - boost_wireframe
          - edge_emission
    """

    scanner_id: str = "disco_main"
    type: ScannerType = ScannerType.ROTATING_CONE

    # Origin / anchor in the scene (free-form name, resolved by renderer)
    anchor: str = "scene.discoball_01"

    # Cone / sphere shape
    cone_angle_deg: float = Field(default=18.0, gt=0.0, le=180.0)
    falloff: FalloffType = FalloffType.SMOOTHSTEP
    max_distance: float = Field(default=22.0, gt=0.0)

    # Rotation drive
    rotation: ScannerRotation = Field(default_factory=ScannerRotation)

    # Edge noise / beat pulse
    noise: ScannerNoise = Field(default_factory=ScannerNoise)

    occlusion_mode: OcclusionMode = OcclusionMode.SCENE_DEPTH

    # Write-channel names this scanner emits.  Each name is a free-form key
    # referenced in TransitionSpec conditions.
    write_channels: list[str] = Field(
        default_factory=lambda: [
            "reveal_splat",
            "hide_photo",
            "boost_wireframe",
            "edge_emission",
        ]
    )


class AssetDomains(BaseModel):
    """Records which representation domains a scene asset supports."""

    photo: bool = False
    mesh: bool = False
    splat: bool = False
    performer: bool = False
    fx: bool = True


class SceneAsset(BaseModel):
    """A single asset in the scene (e.g. a club environment capture)."""

    asset_id: str
    label: str = ""
    domains: AssetDomains = Field(default_factory=AssetDomains)
    # Free-form metadata (paths, capture type, roto refs, etc.)
    meta: dict[str, Any] = Field(default_factory=dict)


class SceneSpec(BaseModel):
    """Top-level scene spec — assets + which domains each supports.

    YAML example::

        scene_id: club_scan_01
        assets:
          - asset_id: env_360
            label: DJ club 360 capture
            domains:
              photo: true
              mesh: true
              splat: true
        scanners:
          - scanner_id: disco_main
            ...
    """

    scene_id: str = "hybrid_scene"
    assets: list[SceneAsset] = Field(default_factory=list)
    scanners: list[ScannerSpec] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Material look families
# ---------------------------------------------------------------------------


class DomainMaterialLook(str, Enum):
    """Named material look families for each domain.

    These map to shader presets in the Blender adapter.
    """

    # mesh_domain looks
    CLEAN_PBR = "clean_pbr"
    CHROME = "chrome"
    GLASS = "glass"
    WIREFRAME_EMISSIVE = "wireframe_emissive"
    CONTOUR_ONLY = "contour_only"
    VOXELIZED = "voxelized"

    # splat_domain looks
    FULL_RADIANCE = "full_radiance"
    POINT_HALO = "point_halo"
    DENSITY_ONLY = "density_only"
    MONO_CLOUD = "mono_cloud"
    STROBE_QUANTIZED = "strobe_quantized"

    # photo_domain looks
    RAW = "raw"
    HIGH_CONTRAST_MONO = "high_contrast_mono"
    POSTERIZED = "posterized"
    EDGE_EXTRACTED = "edge_extracted"
    CRT_DAMAGED = "crt_damaged"

    # performer_domain looks
    PHOTOREAL = "photoreal"
    SILHOUETTE = "silhouette"
    PERFORMER_WIREFRAME = "performer_wireframe"

    # fx_domain looks
    PARTICLES = "particles"
    EDGE_GLOW = "edge_glow"
    CHROMATIC = "chromatic"


class MaterialSpec(BaseModel):
    """Per-domain material look assignment.

    Specifies the default look family for each domain, plus audio-driven
    overrides when certain write-channel conditions hold.

    YAML example::

        domain: mesh
        default_look: wireframe_emissive
        beat_pulse_look: chrome
        drop_look: voxelized
    """

    domain: Domain = Domain.MESH
    default_look: DomainMaterialLook = DomainMaterialLook.CLEAN_PBR
    # Optional look activated on beat events
    beat_pulse_look: DomainMaterialLook | None = None
    # Optional look activated in "drop" sections
    drop_look: DomainMaterialLook | None = None
    # Emission colour tint (RGB 0-1 each)
    emission_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    emission_strength: float = Field(default=1.0, ge=0.0)


# ---------------------------------------------------------------------------
# Transition / domain-opacity mappings
# ---------------------------------------------------------------------------


class ChannelCondition(BaseModel):
    """A simple threshold condition on a write channel.

    Evaluates as: ``channel_values[channel] > threshold``.
    """

    channel: str
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class DomainOpacityRule(BaseModel):
    """Maps a write-channel mask value to a domain opacity expression.

    The expression is intentionally simple: a linear mix driven by one
    channel value.  This keeps it evaluable in pure Python without an
    expression language.

    Semantics::

        domain.opacity = base + scale * channel_values[channel]
    """

    domain: Domain
    channel: str
    base: float = Field(default=0.0, ge=0.0, le=1.0)
    scale: float = Field(default=1.0, ge=-1.0, le=1.0)


class TransitionSpec(BaseModel):
    """Declarative mask→domain mappings.

    Describes how write-channel values produced by the scanner(s) map to
    domain opacities, material overrides, and FX.

    YAML example (matches exploration §"Material system")::

        when:
          channel: reveal_splat
          threshold: 0.5
        do:
          opacity_rules:
            - domain: photo
              channel: reveal_splat
              base: 1.0
              scale: -1.0
            - domain: splat
              channel: reveal_splat
              base: 0.0
              scale: 1.0
          fx_edge_channel: edge_emission
          fx_edge_gain: 1.4
    """

    transition_id: str = "default"

    # Activation condition (all conditions must hold simultaneously)
    conditions: list[ChannelCondition] = Field(default_factory=list)

    # Per-domain opacity rules
    opacity_rules: list[DomainOpacityRule] = Field(default_factory=list)

    # FX edge emission: multiply edge_energy write-channel by this gain
    fx_edge_channel: str = "edge_emission"
    fx_edge_gain: float = Field(default=1.0, ge=0.0)

    # Optional material override while conditions are active
    material_override: DomainMaterialLook | None = None
    material_override_domain: Domain | None = None

    def evaluate_opacities(
        self, channel_values: dict[str, float]
    ) -> dict[Domain, float]:
        """Compute per-domain opacities given current write-channel values.

        Args:
            channel_values: Current mask values, keyed by channel name.
                Missing channels default to 0.0.

        Returns:
            Mapping of domain → opacity in [0.0, 1.0].
        """
        opacities: dict[Domain, float] = {}
        for rule in self.opacity_rules:
            ch_val = channel_values.get(rule.channel, 0.0)
            raw = rule.base + rule.scale * ch_val
            opacities[rule.domain] = max(0.0, min(1.0, raw))
        return opacities

    def conditions_active(self, channel_values: dict[str, float]) -> bool:
        """Return True if all conditions are satisfied."""
        if not self.conditions:
            return True
        return all(
            channel_values.get(c.channel, 0.0) > c.threshold
            for c in self.conditions
        )
