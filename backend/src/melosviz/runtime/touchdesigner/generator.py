"""TouchDesigner network-spec generator.

Converts a :class:`~melosviz.analysis.models.RenderSpec` v2 (+ optional
scene/scanner specs) into a **serialisable network-spec JSON** that describes
the complete TouchDesigner operator graph without requiring TD to be installed.

The spec follows the node-graph blueprint from the operator exploration
(ChatGPT-Programmable Music Visualizers.md §"TouchDesigner runtime layout"):

``/project1``
  * ``/io``         — OSC_In, WebSocket_In, File_Watch
  * ``/timeline``   — Audio_Clock CHOP, Beat_CHOPs, Section_DAT, Event_Router
  * ``/scene``      — Mesh/Splat/Photo/Performer loaders (TOP/SOP/MAT)
  * ``/fields``     — Scanner_1/2 (disco-ball volumetric mask), global noise,
                     mask composer
  * ``/materials``  — per-domain material networks (MAT/GLSL)
  * ``/mix``        — domain blend (Composite TOP), edge FX, particles,
                     bloom/grade
  * ``/camera``     — Camera COMP, shot controller Script CHOP
  * ``/ui``         — review panel, overrides panel, debug views
  * ``/output``     — Preview_Out, Render_Out, Movie_File_Out

The generated JSON is **testable and version-controllable** without TD —
tests assert on the graph structure (groups present, operators wired correctly,
param mappings accurate) without running TD.

When executed *inside* TouchDesigner via the companion bootstrap script
(:mod:`melosviz.runtime.touchdesigner.bootstrap`), the same JSON drives
``td.op()`` calls to construct the live network.

RenderSpec v2 → TD operator param mapping
------------------------------------------
| RenderSpec field          | TD operator / param                              |
|---------------------------|--------------------------------------------------|
| metadata.estimated_bpm    | timeline/audio_clock : BPM_value                 |
| dense_keyframes[*].energy | fields/scanner_1 : pulse_gain (per-frame CHOP)   |
| dense_keyframes[*].beats  | timeline/beat_chops : beat_strength channel      |
| dense_keyframes[*].stems  | mix/particles : emit_rate (drums), bass_scale    |
| scene_segments            | timeline/section_dat : section rows              |
| scanner specs             | fields/scanner_1..N : all ScannerSpec params     |
| domain opacities          | mix/domain_blend : layer opacities (Composite)   |
| palette                   | materials/*_materials : base_color tint          |
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec
    from melosviz.scene.models import ScannerSpec

logger = logging.getLogger(__name__)

__all__ = [
    "OperatorNode",
    "OperatorGroup",
    "NetworkSpec",
    "GenerateResult",
    "generate_network",
    "render_spec_to_network",
]

# ---------------------------------------------------------------------------
# Data models — the serialisable operator graph
# ---------------------------------------------------------------------------


@dataclass
class OperatorNode:
    """A single TouchDesigner operator node.

    Attributes:
        op_type: TD operator class (e.g. ``audioin``, ``chopexec``, ``composite``).
        name: Instance name inside the group container.
        params: Dict of ``param_name → value``.
        wires_from: List of ``"group/op_name"`` strings this node receives data from.
        comment: Optional human-readable annotation.
    """

    op_type: str
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    wires_from: list[str] = field(default_factory=list)
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "op_type": self.op_type,
            "name": self.name,
            "params": self.params,
            "wires_from": self.wires_from,
            "comment": self.comment,
        }


@dataclass
class OperatorGroup:
    """A COMP container holding a set of related operators.

    Attributes:
        name: Container name (e.g. ``io``, ``timeline``, ``scene``).
        operators: Ordered list of :class:`OperatorNode` inside this container.
    """

    name: str
    operators: list[OperatorNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "operators": [op.to_dict() for op in self.operators],
        }

    def op_names(self) -> list[str]:
        """Return list of operator names in this group."""
        return [op.name for op in self.operators]


@dataclass
class NetworkSpec:
    """Complete serialisable description of the TouchDesigner node graph.

    Attributes:
        version: Schema version string.
        project_name: TD project root name.
        groups: Ordered list of :class:`OperatorGroup` containers.
        meta: Freeform metadata dict (bpm, duration, etc.).
    """

    version: str = "1.0"
    project_name: str = "melosviz_runtime"
    groups: list[OperatorGroup] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project_name": self.project_name,
            "groups": [g.to_dict() for g in self.groups],
            "meta": self.meta,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def group_names(self) -> list[str]:
        return [g.name for g in self.groups]

    def find_group(self, name: str) -> OperatorGroup | None:
        for g in self.groups:
            if g.name == name:
                return g
        return None


@dataclass
class GenerateResult:
    """Outputs from :func:`generate_network`.

    Attributes:
        network_spec: In-memory :class:`NetworkSpec`.
        network_spec_path: Path to written JSON file (may be None if
            ``output_dir`` was not provided).
        bootstrap_path: Path to the written TD-side bootstrap ``.py`` file.
        project_path: Path to a minimal ``.toe`` JSON stub (metadata-only).
    """

    network_spec: NetworkSpec
    network_spec_path: Path | None = None
    bootstrap_path: Path | None = None
    project_path: Path | None = None


# ---------------------------------------------------------------------------
# Required top-level group names (tested by assertions)
# ---------------------------------------------------------------------------

REQUIRED_GROUP_NAMES: tuple[str, ...] = (
    "io",
    "timeline",
    "scene",
    "fields",
    "materials",
    "mix",
    "camera",
    "ui",
    "output",
)


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def _build_io_group() -> OperatorGroup:
    """Build the /io container: OSC, WebSocket, and file-watch operators."""
    return OperatorGroup(
        name="io",
        operators=[
            OperatorNode(
                op_type="oscinDAT",
                name="osc_in",
                params={"port": 7700, "active": True},
                comment="Receives OSC events from the Python bridge (timeline events)",
            ),
            OperatorNode(
                op_type="webserverDAT",
                name="ws_in",
                params={"port": 7701, "active": True, "protocol": "websocket"},
                comment="WebSocket alternative transport for timeline events",
            ),
            OperatorNode(
                op_type="filewatchDAT",
                name="file_watch",
                params={"file": "overrides.yaml", "active": True},
                comment="Watches overrides.yaml; triggers reload on change",
            ),
        ],
    )


def _build_timeline_group(render_spec: RenderSpec) -> OperatorGroup:
    """Build /timeline: BPM clock, beat CHOPs, section DAT, event router."""
    bpm = render_spec.metadata.get("estimated_bpm", 120.0) if render_spec.metadata else 120.0

    # Build section rows from scene_segments
    section_rows: list[dict[str, Any]] = []
    for seg in (render_spec.scene_segments or []):
        section_rows.append({
            "label": getattr(seg, "label", str(getattr(seg, "index", ""))),
            "start": getattr(seg, "start", 0.0),
            "end": getattr(seg, "end", 0.0),
            "mood": getattr(seg, "mood", ""),
            "dominant_stem": getattr(seg, "dominant_stem", ""),
        })

    # Build beat channel from timeline_events
    beat_times: list[float] = []
    onset_times: list[float] = []
    for ev in (render_spec.timeline_events or []):
        ev_type = getattr(ev, "type", None) or ev.get("type", "") if isinstance(ev, dict) else ""
        ev_t = getattr(ev, "t", None) if not isinstance(ev, dict) else ev.get("t", 0.0)
        if ev_type == "beat":
            beat_times.append(float(ev_t or 0.0))
        elif ev_type == "onset":
            onset_times.append(float(ev_t or 0.0))

    return OperatorGroup(
        name="timeline",
        operators=[
            OperatorNode(
                op_type="audiodevinCHOP",
                name="audio_clock",
                params={
                    "BPM_value": bpm,
                    "active": True,
                },
                comment="Master BPM clock; drives beat_chops",
            ),
            OperatorNode(
                op_type="beatCHOP",
                name="beat_chops",
                params={
                    "BPM_value": bpm,
                    "beat_times": beat_times,
                    "onset_times": onset_times,
                },
                wires_from=["timeline/audio_clock"],
                comment="Beat + onset channel array (one sample per beat event)",
            ),
            OperatorNode(
                op_type="tableDAT",
                name="section_dat",
                params={"rows": section_rows},
                comment="Scene segment table: label/start/end/mood/dominant_stem",
            ),
            OperatorNode(
                op_type="scriptCHOP",
                name="event_router",
                params={},
                wires_from=["io/osc_in", "io/ws_in", "timeline/beat_chops"],
                comment="Routes incoming OSC/WS events + beat pulses to downstream groups",
            ),
        ],
    )


def _build_scene_group(render_spec: RenderSpec) -> OperatorGroup:
    """Build /scene: mesh/splat/photo/performer asset loaders."""
    palette = render_spec.palette or []
    base_color = palette[0] if palette else "#ffffff"

    return OperatorGroup(
        name="scene",
        operators=[
            OperatorNode(
                op_type="moviefileinTOP",
                name="photo_loader",
                params={"file": "", "base_color_hint": base_color},
                comment="Equirect 360 / projected video photo domain asset",
            ),
            OperatorNode(
                op_type="sopCOMP",
                name="mesh_loader",
                params={"file": ""},
                comment="Triangle mesh / wireframe / depth shell asset",
            ),
            OperatorNode(
                op_type="scriptSOP",
                name="splat_loader",
                params={"file": "", "point_size": 2.0},
                comment="Gaussian-splat / point-cloud proxy loader",
            ),
            OperatorNode(
                op_type="moviefileinTOP",
                name="performer_loader",
                params={"file": "", "chroma_key": False},
                comment="Roto-isolated performer pass (Roto Brush 3 output)",
            ),
        ],
    )


def _build_fields_group(
    render_spec: RenderSpec,
    scanner_specs: list[ScannerSpec] | None,
) -> OperatorGroup:
    """Build /fields: scanner nodes, global noise, mask composer."""
    operators: list[OperatorNode] = []

    # One node per scanner spec, or two default disco-ball scanners
    if scanner_specs:
        for i, sc in enumerate(scanner_specs, start=1):
            cone_angle = getattr(sc, "shape", None)
            cone_deg = getattr(cone_angle, "cone_angle_deg", 22.0) if cone_angle else 22.0
            rot = getattr(sc, "rotation", None)
            bpr = getattr(rot, "beats_per_rotation", 8.0) if rot else 8.0
            noise = getattr(sc, "noise", None)
            pulse_gain = getattr(noise, "beat_pulse_gain", 0.35) if noise else 0.35
            bpm = render_spec.metadata.get("estimated_bpm", 120.0) if render_spec.metadata else 120.0
            operators.append(
                OperatorNode(
                    op_type="scriptCHOP",
                    name=f"scanner_{i}",
                    params={
                        "scanner_id": getattr(sc, "scanner_id", f"scanner_{i}"),
                        "scanner_type": getattr(sc, "type", "rotating_cone"),
                        "cone_angle_deg": cone_deg,
                        "beats_per_rotation": bpr,
                        "beat_pulse_gain": pulse_gain,
                        "bpm": bpm,
                        "write_channels": getattr(sc, "write_channels", [
                            "reveal_splat", "hide_photo", "boost_wireframe", "edge_emission",
                        ]),
                    },
                    wires_from=["timeline/beat_chops"],
                    comment=f"Disco-ball volumetric mask generator #{i}",
                )
            )
    else:
        # Default: two generic scanners
        bpm = render_spec.metadata.get("estimated_bpm", 120.0) if render_spec.metadata else 120.0
        for i, sc_id in enumerate(["disco_main", "crowd_sweep"], start=1):
            operators.append(
                OperatorNode(
                    op_type="scriptCHOP",
                    name=f"scanner_{i}",
                    params={
                        "scanner_id": sc_id,
                        "scanner_type": "rotating_cone",
                        "cone_angle_deg": 22.0,
                        "beats_per_rotation": 8.0,
                        "beat_pulse_gain": 0.35,
                        "bpm": bpm,
                        "write_channels": [
                            "reveal_splat", "hide_photo", "boost_wireframe", "edge_emission",
                        ],
                    },
                    wires_from=["timeline/beat_chops"],
                    comment=f"Default disco-ball scanner #{i}",
                )
            )

    operators.append(
        OperatorNode(
            op_type="noiseCHOP",
            name="global_noise",
            params={"period": 2.0, "amplitude": 0.08},
            comment="Low-frequency noise modulation for organic feel",
        )
    )
    operators.append(
        OperatorNode(
            op_type="scriptCHOP",
            name="mask_composer",
            params={},
            wires_from=[op.name for op in operators],
            comment="Composites scanner channel masks into final per-domain opacity channels",
        )
    )

    return OperatorGroup(name="fields", operators=operators)


def _build_materials_group(render_spec: RenderSpec) -> OperatorGroup:
    """Build /materials: per-domain material networks (MAT/GLSL)."""
    palette = render_spec.palette or []

    def palette_color(index: int) -> str:
        return palette[index] if index < len(palette) else "#ffffff"

    return OperatorGroup(
        name="materials",
        operators=[
            OperatorNode(
                op_type="pbrMAT",
                name="photo_materials",
                params={"base_color": palette_color(0), "roughness": 0.8},
                wires_from=["scene/photo_loader"],
                comment="PBR material for the photo domain",
            ),
            OperatorNode(
                op_type="pbrMAT",
                name="mesh_materials",
                params={
                    "base_color": palette_color(1),
                    "roughness": 0.4,
                    "wireframe": False,
                    "emission_strength": 0.0,
                },
                wires_from=["scene/mesh_loader"],
                comment="PBR + wireframe-boost material for the mesh domain",
            ),
            OperatorNode(
                op_type="pointspriteMAT",
                name="splat_materials",
                params={"base_color": palette_color(2), "point_size": 2.0},
                wires_from=["scene/splat_loader"],
                comment="Point-sprite material for Gaussian-splat domain",
            ),
            OperatorNode(
                op_type="pbrMAT",
                name="performer_materials",
                params={"base_color": "#ffffff", "edge_glow": 0.35},
                wires_from=["scene/performer_loader"],
                comment="Material preserving photoreal performer in any domain blend",
            ),
        ],
    )


def _build_mix_group(render_spec: RenderSpec) -> OperatorGroup:
    """Build /mix: domain blend (Composite TOP), edge FX, particles, bloom."""
    bpm = render_spec.metadata.get("estimated_bpm", 120.0) if render_spec.metadata else 120.0

    return OperatorGroup(
        name="mix",
        operators=[
            OperatorNode(
                op_type="compositeTOP",
                name="domain_blend",
                params={
                    "operand": "over",
                    # Initial opacities; overridden at runtime by mask_composer channels
                    "photo_opacity": 1.0,
                    "mesh_opacity": 0.0,
                    "splat_opacity": 0.0,
                    "performer_opacity": 1.0,
                    "fx_opacity": 0.0,
                },
                wires_from=[
                    "materials/photo_materials",
                    "materials/mesh_materials",
                    "materials/splat_materials",
                    "materials/performer_materials",
                    "fields/mask_composer",
                ],
                comment="Blends all domain layers using mask_composer channel values",
            ),
            OperatorNode(
                op_type="edgeTOP",
                name="edge_fx",
                params={"gain": 1.0, "color": "#00f5ff"},
                wires_from=["mix/domain_blend", "fields/mask_composer"],
                comment="Edge emission FX driven by scanner edge_emission channel",
            ),
            OperatorNode(
                op_type="particlesgpuSOP",
                name="particles",
                params={
                    "emit_rate_bpm": bpm,
                    "drums_scale": 1.0,
                    "bass_scale": 1.0,
                },
                wires_from=["timeline/beat_chops"],
                comment="GPU particle system; emit rate driven by drums stem + BPM",
            ),
            OperatorNode(
                op_type="bloomTOP",
                name="bloom_grade",
                params={"threshold": 0.6, "strength": 0.4},
                wires_from=["mix/edge_fx", "mix/particles"],
                comment="Bloom + color-grade post-process",
            ),
        ],
    )


def _build_camera_group(render_spec: RenderSpec) -> OperatorGroup:
    """Build /camera: Camera COMP + shot controller."""
    # Extract first keyframe camera params if present
    dense = render_spec.dense_keyframes or []
    first_kf = dense[0] if dense else None
    initial_energy = getattr(first_kf, "energy", 0.5) if first_kf else 0.5

    return OperatorGroup(
        name="camera",
        operators=[
            OperatorNode(
                op_type="cameraCOMP",
                name="camera_rig",
                params={
                    "tx": 0.0, "ty": 1.5, "tz": 4.5,
                    "rx": -10.0, "ry": 0.0, "rz": 0.0,
                    "fov": 70.0,
                    "near": 0.1,
                    "far": 1000.0,
                },
                comment="Main camera; position animated by shot_controller",
            ),
            OperatorNode(
                op_type="scriptCHOP",
                name="shot_controller",
                params={
                    "mode": "orbit_target",
                    "radius": 4.5,
                    "energy_scale": initial_energy,
                },
                wires_from=["timeline/event_router", "timeline/beat_chops"],
                comment="Drives camera_rig transform from beat + keyframe data",
            ),
        ],
    )


def _build_ui_group() -> OperatorGroup:
    """Build /ui: review panel, overrides panel, debug views."""
    return OperatorGroup(
        name="ui",
        operators=[
            OperatorNode(
                op_type="containerCOMP",
                name="review_panel",
                params={"visible": True},
                comment="Primary review / preview UI panel",
            ),
            OperatorNode(
                op_type="containerCOMP",
                name="overrides_panel",
                params={"visible": True, "overrides_file": "overrides.yaml"},
                comment="Shows current overrides; trigger export-overrides on save",
            ),
            OperatorNode(
                op_type="containerCOMP",
                name="debug_views",
                params={"visible": False},
                comment="Debug: scanner mask channels, beat CHOP waveform, segment table",
            ),
        ],
    )


def _build_output_group() -> OperatorGroup:
    """Build /output: Preview_Out + Render_Out + Movie_File_Out."""
    return OperatorGroup(
        name="output",
        operators=[
            OperatorNode(
                op_type="outTOP",
                name="preview_out",
                params={"active": True},
                wires_from=["mix/bloom_grade"],
                comment="Interactive preview (NDI/Spout available via add-on)",
            ),
            OperatorNode(
                op_type="renderTOP",
                name="render_out",
                params={"resolution": [1920, 1080], "active": False},
                wires_from=["mix/bloom_grade", "camera/camera_rig"],
                comment="Offline render pass (activate for deterministic frame output)",
            ),
            OperatorNode(
                op_type="moviefileoutTOP",
                name="movie_file_out",
                params={
                    "file": "output.mov",
                    "codec": "h264",
                    "quality": 0.9,
                    "active": False,
                },
                wires_from=["output/render_out"],
                comment="Frame-perfect MP4/ProRes encode (offline mode only)",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_spec_to_network(
    render_spec: RenderSpec,
    scanner_specs: list[ScannerSpec] | None = None,
) -> NetworkSpec:
    """Convert a RenderSpec v2 to a :class:`NetworkSpec`.

    This is the core mapping function — no I/O, pure transformation.

    Args:
        render_spec: A fully-populated RenderSpec v2 object.
        scanner_specs: Optional list of :class:`~melosviz.scene.models.ScannerSpec`
            objects.  When absent, two default disco-ball scanners are generated.

    Returns:
        A :class:`NetworkSpec` describing the complete operator graph.
    """
    bpm = render_spec.metadata.get("estimated_bpm", 120.0) if render_spec.metadata else 120.0
    duration = render_spec.metadata.get("duration", 0.0) if render_spec.metadata else 0.0

    network = NetworkSpec(
        version="1.0",
        project_name="melosviz_runtime",
        meta={
            "source_audio": render_spec.metadata.get("source_audio", "") if render_spec.metadata else "",
            "estimated_bpm": bpm,
            "duration": duration,
            "dense_keyframe_count": len(render_spec.dense_keyframes or []),
            "segment_count": len(render_spec.scene_segments or []),
            "timeline_event_count": len(render_spec.timeline_events or []),
            "palette": render_spec.palette or [],
        },
        groups=[
            _build_io_group(),
            _build_timeline_group(render_spec),
            _build_scene_group(render_spec),
            _build_fields_group(render_spec, scanner_specs),
            _build_materials_group(render_spec),
            _build_mix_group(render_spec),
            _build_camera_group(render_spec),
            _build_ui_group(),
            _build_output_group(),
        ],
    )

    return network


def generate_network(
    render_spec: RenderSpec,
    scanner_specs: list[ScannerSpec] | None = None,
    output_dir: Path | None = None,
) -> GenerateResult:
    """Generate a complete TD runtime from a RenderSpec v2.

    Creates the :class:`NetworkSpec`, serialises it to JSON, writes the
    TD-side bootstrap script, and writes a minimal ``.toe`` stub JSON.
    All three files are placed in ``output_dir`` when provided.

    Args:
        render_spec: RenderSpec v2 object.
        scanner_specs: Optional list of :class:`~melosviz.scene.models.ScannerSpec`.
        output_dir: Directory to write output files.  If None, no files are written.

    Returns:
        :class:`GenerateResult` with the in-memory spec and optional paths.
    """
    from melosviz.runtime.touchdesigner.bootstrap import render_bootstrap_script

    network = render_spec_to_network(render_spec, scanner_specs)

    network_spec_path: Path | None = None
    bootstrap_path: Path | None = None
    project_path: Path | None = None

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Network spec JSON
        network_spec_path = output_dir / "network_spec.json"
        network_spec_path.write_text(network.to_json())
        logger.info("Wrote network spec: %s", network_spec_path)

        # 2. TD-side bootstrap Python script
        bootstrap_path = output_dir / "td_bootstrap.py"
        bootstrap_path.write_text(render_bootstrap_script(network))
        logger.info("Wrote TD bootstrap: %s", bootstrap_path)

        # 3. Minimal .toe stub (metadata JSON, not a real binary .toe)
        toe_stub = {
            "format": "melosviz_toe_stub",
            "version": "1.0",
            "network_spec": str(network_spec_path),
            "bootstrap_script": str(bootstrap_path),
            "meta": network.meta,
        }
        project_path = output_dir / "runtime.toe.json"
        project_path.write_text(json.dumps(toe_stub, indent=2))
        logger.info("Wrote .toe stub: %s", project_path)

    return GenerateResult(
        network_spec=network,
        network_spec_path=network_spec_path,
        bootstrap_path=bootstrap_path,
        project_path=project_path,
    )
