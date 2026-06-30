"""Blender adapter extension for P4 hybrid representation-domain scene.

This module extends P3's :mod:`melosviz.render.blender_exporter` with the
multi-domain / scanner-mask layer.  The scanner mask + domain/material/
transition specs drive a multi-domain Blender scene — domain opacity and
material per the transition mappings, scanner as an animated cone/empty
driving a mask, per-segment domain selection.

MVP domain coverage
-------------------
- **photo**     — image plane or 360-sphere with an image texture.
- **mesh**      — wireframe modifier on the main geometry object.
- **splat**     — point-cloud / particle proxy (full 3DGS is future work).
- **performer** — placeholder empty tagged for roto compositing.
- **fx**        — edge-emission shader (FX domain; driven by ``edge_emission``).

Flash-safety
------------
Opacity changes driven by the scanner mask honour the same
:data:`~melosviz.render.blender_exporter.FLASH_SAFETY_MAX_HZ` clamp applied
to raw energy in :func:`~melosviz.render.blender_exporter.apply_flash_safety`.
"""

from __future__ import annotations

import logging
import textwrap
from typing import Any

from melosviz.render.blender_exporter import FLASH_SAFETY_MAX_HZ, apply_flash_safety
from melosviz.scene.models import (
    Domain,
    DomainMaterialLook,
    MaterialSpec,
    SceneSpec,
    ScannerSpec,
    TransitionSpec,
)
from melosviz.scene.scanner import ChannelMaskFrame, evaluate_scanner

logger = logging.getLogger(__name__)

__all__ = [
    "build_hybrid_bpy_segment",
    "HybridDomainAssembly",
    "assemble_multi_domain_scene",
]


# ---------------------------------------------------------------------------
# Multi-domain assembly helpers
# ---------------------------------------------------------------------------


def _domain_opacities_at(
    channels: dict[str, float],
    transitions: list[TransitionSpec],
    default_domain: Domain = Domain.PHOTO,
) -> dict[Domain, float]:
    """Resolve per-domain opacities for a given set of channel values.

    Applies all active transitions.  If multiple transitions affect the same
    domain, the last one wins (order matters in the spec list).

    If no transitions are active, the default_domain gets opacity 1.0 and
    all others get 0.0.
    """
    opacities: dict[Domain, float] = {d: 0.0 for d in Domain}

    any_active = False
    for tr in transitions:
        if tr.conditions_active(channels):
            any_active = True
            for domain, opacity in tr.evaluate_opacities(channels).items():
                opacities[domain] = opacity

    if not any_active:
        opacities[default_domain] = 1.0

    return opacities


def _look_name(look: DomainMaterialLook) -> str:
    """Convert a DomainMaterialLook enum to a Blender-friendly material name."""
    return f"melo_{look.value}"


# ---------------------------------------------------------------------------
# Per-frame domain data type
# ---------------------------------------------------------------------------


class HybridDomainAssembly:
    """Snapshot of per-domain opacities and material overrides at one keyframe.

    Produced by :func:`assemble_multi_domain_scene` for each scanner mask
    frame, ready to be baked into Blender keyframes.
    """

    __slots__ = ("t", "opacities", "material_looks", "edge_energy", "scanner_angle_rad")

    def __init__(
        self,
        t: float,
        opacities: dict[Domain, float],
        material_looks: dict[Domain, DomainMaterialLook],
        edge_energy: float,
        scanner_angle_rad: float,
    ) -> None:
        self.t = t
        self.opacities = opacities
        self.material_looks = material_looks
        self.edge_energy = edge_energy
        self.scanner_angle_rad = scanner_angle_rad


def assemble_multi_domain_scene(
    scanner: ScannerSpec,
    scene_spec: SceneSpec,
    transitions: list[TransitionSpec],
    materials: list[MaterialSpec],
    render_spec: Any,
    *,
    fps: int = 30,
) -> list[HybridDomainAssembly]:
    """Assemble per-keyframe domain state for the hybrid scene.

    Steps:

    1. Evaluate the scanner mask over the RenderSpec timeline →
       :class:`~melosviz.scene.scanner.ChannelMaskFrame` per frame.
    2. For each frame, resolve domain opacities via :func:`_domain_opacities_at`.
    3. Pick the material look for each domain (beat-pulse / drop / default).
    4. Apply flash-safety clamping to opacity deltas.
    5. Return one :class:`HybridDomainAssembly` per frame.

    Args:
        scanner: Scanner spec for the main disco-ball scanner.
        scene_spec: Top-level scene spec (used for future asset queries).
        transitions: Ordered list of transition specs.
        materials: Per-domain material specs.
        render_spec: RenderSpec v2 instance.
        fps: Frames per second (used to interpret flash-safety window).

    Returns:
        List of :class:`HybridDomainAssembly`, one per dense keyframe.
    """
    # 1. Scanner mask frames
    mask_frames: list[ChannelMaskFrame] = evaluate_scanner(scanner, render_spec)
    if not mask_frames:
        return []

    # Index materials by domain for quick lookup
    mat_by_domain: dict[Domain, MaterialSpec] = {m.domain: m for m in materials}

    # Extract timeline_events for beat/section detection
    if hasattr(render_spec, "timeline_events"):
        raw_events = render_spec.timeline_events or []
    elif isinstance(render_spec, dict):
        raw_events = render_spec.get("timeline_events", [])
    else:
        raw_events = []

    beat_times = sorted(
        float(ev["t"] if isinstance(ev, dict) else ev.t)
        for ev in raw_events
        if (ev["type"] if isinstance(ev, dict) else ev.type) in ("beat", "downbeat")
    )

    drop_sections: set[str] = {"drop", "chorus"}

    if hasattr(render_spec, "scene_segments"):
        raw_segs = render_spec.scene_segments or []
    elif isinstance(render_spec, dict):
        raw_segs = render_spec.get("scene_segments", [])
    else:
        raw_segs = []

    def _is_drop(t: float) -> bool:
        for seg in raw_segs:
            start = float(seg["start"] if isinstance(seg, dict) else seg.start)
            end = float(seg["end"] if isinstance(seg, dict) else seg.end)
            label = (seg["label"] if isinstance(seg, dict) else seg.label) or ""
            if start <= t <= end and label.lower() in drop_sections:
                return True
        return False

    def _is_on_beat(t: float, window_frac: float = 0.15) -> bool:
        if not beat_times:
            return False
        metadata: dict[str, Any] = {}
        if hasattr(render_spec, "metadata"):
            metadata = render_spec.metadata or {}
        elif isinstance(render_spec, dict):
            metadata = render_spec.get("metadata", {})
        bpm = float(metadata.get("estimated_bpm", 120.0))
        spb = 60.0 / bpm if bpm > 0 else 0.5
        for bt in beat_times:
            if abs(t - bt) < spb * window_frac:
                return True
        return False

    # 2-4. Resolve opacities per frame and pick materials
    # We also track previous opacities per domain to apply flash-safety.
    # apply_flash_safety operates on a 1-D sequence; we call it column-wise.

    assemblies: list[HybridDomainAssembly] = []

    # Collect raw domain opacity sequences first for flash-safety post-pass
    raw_opacity_seq: dict[Domain, list[float]] = {d: [] for d in Domain}
    raw_edge_seq: list[float] = []
    raw_angle_seq: list[float] = []
    raw_looks: list[dict[Domain, DomainMaterialLook]] = []

    for frame in mask_frames:
        t = frame.t
        channels = frame.channels

        opacities = _domain_opacities_at(channels, transitions)

        # Pick material look per domain
        looks: dict[Domain, DomainMaterialLook] = {}
        for domain in Domain:
            mat = mat_by_domain.get(domain)
            if mat is None:
                looks[domain] = DomainMaterialLook.CLEAN_PBR
            elif _is_drop(t) and mat.drop_look is not None:
                looks[domain] = mat.drop_look
            elif _is_on_beat(t) and mat.beat_pulse_look is not None:
                looks[domain] = mat.beat_pulse_look
            else:
                looks[domain] = mat.default_look

        edge_energy = channels.get("edge_emission", 0.0)
        # Find the transition's fx_edge_gain to apply
        for tr in transitions:
            if tr.conditions_active(channels):
                fx_ch_val = channels.get(tr.fx_edge_channel, 0.0)
                edge_energy = min(1.0, fx_ch_val * tr.fx_edge_gain)
                break

        # Accumulate
        for d in Domain:
            raw_opacity_seq[d].append(opacities.get(d, 0.0))
        raw_edge_seq.append(edge_energy)

        # Scanner angle: retrieve from a parallel evaluate_pose call stored
        # in channels if present, else reconstruct.
        raw_angle_seq.append(0.0)  # placeholder; filled after flash-safety
        raw_looks.append(looks)

    # Flash-safety post-pass on domain opacities (treat as "strength" column)
    for domain in Domain:
        seq = raw_opacity_seq[domain]
        clamped = apply_flash_safety(seq, fps=fps, max_hz=FLASH_SAFETY_MAX_HZ)
        raw_opacity_seq[domain] = clamped

    # Reconstruct scanner angles from mask_frames (we need poses)
    if hasattr(render_spec, "metadata"):
        metadata = render_spec.metadata or {}
    elif isinstance(render_spec, dict):
        metadata = render_spec.get("metadata", {})
    else:
        metadata = {}
    bpm = float(metadata.get("estimated_bpm", 120.0))

    from melosviz.scene.scanner import evaluate_pose  # local import avoids circularity

    for i, frame in enumerate(mask_frames):
        pose = evaluate_pose(scanner, frame.t, bpm, beat_times)
        raw_angle_seq[i] = pose.orbit_angle_rad

    # 5. Build final assembly list
    for i, frame in enumerate(mask_frames):
        opacities = {d: raw_opacity_seq[d][i] for d in Domain}
        assemblies.append(
            HybridDomainAssembly(
                t=frame.t,
                opacities=opacities,
                material_looks=raw_looks[i],
                edge_energy=raw_edge_seq[i],
                scanner_angle_rad=raw_angle_seq[i],
            )
        )

    return assemblies


# ---------------------------------------------------------------------------
# Blender bpy script segment (appended to the P3 base script)
# ---------------------------------------------------------------------------


def build_hybrid_bpy_segment(
    assemblies: list[HybridDomainAssembly],
    fps: int = 30,
) -> str:
    """Generate the bpy Python snippet that bakes hybrid domain keyframes.

    This is appended to / called from the base bpy script generated by
    :func:`~melosviz.render.blender_exporter.build_bpy_script`.  It creates
    Blender objects for each domain and inserts opacity/visibility keyframes
    driven by the scanner mask.

    MVP domain objects
    ------------------
    - ``melo_photo``    — image plane / 360-sphere (photo domain).
    - ``melo_mesh``     — cube with Wireframe modifier (mesh domain).
    - ``melo_splat``    — particle-emitter point-cloud proxy (splat domain).
    - ``melo_performer`` — empty / placeholder (performer domain).
    - ``melo_fx_edge``  — emission-only object (fx domain).
    - ``melo_scanner``  — empty animated with the scanner orbit angle (z-rotation).

    Args:
        assemblies: Per-frame domain state from :func:`assemble_multi_domain_scene`.
        fps: Frames per second (matches the Blender scene FPS).

    Returns:
        Python source code string (bpy script fragment).
    """
    if not assemblies:
        return "# No hybrid domain assemblies — skipping multi-domain setup.\n"

    # Serialise assembly data as a compact Python literal so the generated
    # script is self-contained (no external JSON file required).
    frames_data = [
        {
            "f": max(1, round(a.t * fps)),
            "photo": round(a.opacities.get(Domain.PHOTO, 0.0), 4),
            "mesh": round(a.opacities.get(Domain.MESH, 0.0), 4),
            "splat": round(a.opacities.get(Domain.SPLAT, 0.0), 4),
            "performer": round(a.opacities.get(Domain.PERFORMER, 0.0), 4),
            "fx": round(a.opacities.get(Domain.FX, 0.0), 4),
            "edge_energy": round(a.edge_energy, 4),
            "scanner_angle": round(a.scanner_angle_rad, 5),
        }
        for a in assemblies
    ]

    # Encode as a Python literal string
    frames_literal = repr(frames_data)

    script = textwrap.dedent(f"""\
        # ---------- P4 Hybrid domain scene setup ----------

        import bpy
        import math

        HYBRID_FRAMES = {frames_literal}

        def _get_or_create(name, kind="MESH"):
            if name in bpy.data.objects:
                return bpy.data.objects[name]
            if kind == "MESH":
                mesh = bpy.data.meshes.new(name + "_mesh")
                obj = bpy.data.objects.new(name, mesh)
            elif kind == "EMPTY":
                obj = bpy.data.objects.new(name, None)
            else:
                obj = bpy.data.objects.new(name, None)
            bpy.context.collection.objects.link(obj)
            return obj

        def _ensure_material(obj, mat_name, base_color=(0.5, 0.5, 0.5, 1.0), emission_strength=1.0):
            if mat_name in bpy.data.materials:
                mat = bpy.data.materials[mat_name]
            else:
                mat = bpy.data.materials.new(mat_name)
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links
                nodes.clear()
                out_node = nodes.new("ShaderNodeOutputMaterial")
                emit_node = nodes.new("ShaderNodeEmission")
                emit_node.inputs["Color"].default_value = base_color
                emit_node.inputs["Strength"].default_value = emission_strength
                links.new(emit_node.outputs["Emission"], out_node.inputs["Surface"])
            if obj.data and not obj.material_slots:
                obj.data.materials.append(mat)
            elif obj.material_slots:
                obj.material_slots[0].material = mat
            return mat

        # --- Create domain proxy objects ---
        photo_obj = _get_or_create("melo_photo", "MESH")
        if not photo_obj.data or not photo_obj.data.polygons:
            bpy.context.view_layer.objects.active = photo_obj
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.mesh.primitive_plane_add(size=8.0)
            photo_obj = bpy.context.active_object
            photo_obj.name = "melo_photo"
        photo_mat = _ensure_material(photo_obj, "melo_photo_mat", base_color=(0.9, 0.7, 0.5, 1.0))

        mesh_obj = _get_or_create("melo_mesh", "MESH")
        if not mesh_obj.data or not mesh_obj.data.polygons:
            bpy.context.view_layer.objects.active = mesh_obj
            bpy.ops.mesh.primitive_cube_add(size=3.0)
            mesh_obj = bpy.context.active_object
            mesh_obj.name = "melo_mesh"
            # Add wireframe modifier for mesh domain look
            wf_mod = mesh_obj.modifiers.new("Wireframe", "WIREFRAME")
            wf_mod.thickness = 0.05
        mesh_mat = _ensure_material(mesh_obj, "melo_mesh_mat", base_color=(0.0, 0.8, 1.0, 1.0), emission_strength=2.0)

        splat_obj = _get_or_create("melo_splat", "EMPTY")
        # Particle emitter proxy for the splat domain
        if "melo_splat_src" not in bpy.data.objects:
            bpy.ops.mesh.primitive_ico_sphere_add(radius=0.1)
            splat_src = bpy.context.active_object
            splat_src.name = "melo_splat_src"
            splat_src.hide_render = True
        else:
            splat_src = bpy.data.objects["melo_splat_src"]

        performer_obj = _get_or_create("melo_performer", "EMPTY")
        performer_obj.empty_display_type = "SPHERE"
        performer_obj.empty_display_size = 1.5

        fx_obj = _get_or_create("melo_fx_edge", "MESH")
        if not fx_obj.data or not fx_obj.data.polygons:
            bpy.context.view_layer.objects.active = fx_obj
            bpy.ops.mesh.primitive_torus_add(major_radius=2.5, minor_radius=0.05)
            fx_obj = bpy.context.active_object
            fx_obj.name = "melo_fx_edge"
        fx_mat = _ensure_material(fx_obj, "melo_fx_mat", base_color=(1.0, 0.2, 0.9, 1.0), emission_strength=5.0)

        # Scanner empty — animated with the orbit angle (z-rotation)
        scanner_obj = _get_or_create("melo_scanner", "EMPTY")
        scanner_obj.empty_display_type = "CONE"
        scanner_obj.empty_display_size = 3.0
        scanner_obj.location = (0.0, 0.0, 4.0)

        # --- Insert per-frame domain keyframes ---
        for kf in HYBRID_FRAMES:
            f         = kf["f"]
            photo_op  = kf["photo"]
            mesh_op   = kf["mesh"]
            splat_op  = kf["splat"]
            perf_op   = kf["performer"]
            fx_op     = kf["fx"]
            edge_en   = kf["edge_energy"]
            scan_ang  = kf["scanner_angle"]

            # Photo domain: drive plane transparency via emission strength
            if photo_mat.use_nodes:
                emit = photo_mat.node_tree.nodes.get("Emission") or (
                    [n for n in photo_mat.node_tree.nodes if n.type == "EMISSION"] or [None]
                )[0]
                if emit:
                    emit.inputs["Strength"].default_value = photo_op * 2.0
                    emit.inputs["Strength"].keyframe_insert("default_value", frame=f)

            # Photo visibility (hide completely when opacity is ~0)
            photo_obj.hide_render = photo_op < 0.05
            photo_obj.keyframe_insert("hide_render", frame=f)

            # Mesh domain: wireframe emission strength
            if mesh_mat.use_nodes:
                emit = mesh_mat.node_tree.nodes.get("Emission") or (
                    [n for n in mesh_mat.node_tree.nodes if n.type == "EMISSION"] or [None]
                )[0]
                if emit:
                    emit.inputs["Strength"].default_value = mesh_op * 4.0
                    emit.inputs["Strength"].keyframe_insert("default_value", frame=f)
            mesh_obj.hide_render = mesh_op < 0.05
            mesh_obj.keyframe_insert("hide_render", frame=f)

            # Splat domain: scale proxy (larger = more visible point cloud)
            sc = max(0.01, splat_op * 2.0)
            splat_obj.scale = (sc, sc, sc)
            splat_obj.keyframe_insert("scale", frame=f)
            splat_obj.hide_render = splat_op < 0.05
            splat_obj.keyframe_insert("hide_render", frame=f)

            # Performer domain: visibility placeholder
            performer_obj.hide_render = perf_op < 0.05
            performer_obj.keyframe_insert("hide_render", frame=f)

            # FX / edge domain: emission strength driven by edge_energy
            if fx_mat.use_nodes:
                emit = fx_mat.node_tree.nodes.get("Emission") or (
                    [n for n in fx_mat.node_tree.nodes if n.type == "EMISSION"] or [None]
                )[0]
                if emit:
                    emit.inputs["Strength"].default_value = edge_en * 8.0
                    emit.inputs["Strength"].keyframe_insert("default_value", frame=f)
            fx_obj.hide_render = fx_op < 0.05 and edge_en < 0.05
            fx_obj.keyframe_insert("hide_render", frame=f)

            # Scanner orbit: animate Z rotation
            scanner_obj.rotation_euler[2] = scan_ang
            scanner_obj.keyframe_insert("rotation_euler", index=2, frame=f)

        print("[melosviz-p4] Hybrid domain keyframes inserted OK.")
        # ---------- end P4 hybrid domain setup ----------
    """)

    return script
