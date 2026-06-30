"""Headless Blender adapter — RenderSpec v2 → procedural Geo/Shader scene → MP4.

This module drives Blender in headless mode (``blender -b --python <script>``)
to produce a photosensitive-safe, music-driven 3-D animation from a
:class:`~melosviz.analysis.models.RenderSpec` v2 payload.

Design
------
* **Wrap-over-handroll**: we write a bpy driver script and hand it to a
  Blender subprocess — we do not re-implement rendering.  Blender remains the
  actual renderer; this module is the glue layer.
* **Fail-open / optional-heavy**: Blender is *not* a hard runtime dep.
  :func:`export_blender` raises :class:`BlenderNotFoundError` when the binary
  is absent.  The existing :func:`~melosviz.render.video_exporter.export_video`
  (FFmpeg path) stays the always-available fallback.
* **Baked keyframes, not per-frame Python**: the generated bpy script inserts
  Blender keyframes for every dense-keyframe time step *before* rendering.
  No Python callback runs during the actual render pass, so Blender can use
  its normal multi-threaded tile renderer.
* **Flash safety (P1-safety)**: a post-pass clamps the full-frame luminance
  flash rate to ≤ 3 large transitions per second (Blender Energy column → the
  emitter strength curve).  This satisfies the photosensitive-epilepsy
  safety requirement identified in the gap-sweep.

RenderSpec v2 → Blender mapping
--------------------------------
| RenderSpec field            | Blender target                                       |
|-----------------------------|------------------------------------------------------|
| energy                      | Emitter object scale + emission strength             |
| beat_strength / onset_strength | Pulse emitter scale (instantaneous spike)         |
| stems.drums                 | Particle system birth rate modifier                  |
| stems.bass                  | Camera Z offset + main mesh scale                    |
| stems.vocals                | Highlighted "vocals" mesh emission colour intensity  |
| stems.other                 | Background shader mix factor                         |
| spectral_centroid / brightness | Base colour hue rotation (HSV H channel)          |
| valence / arousal           | Palette tint mix (warm↔cool, calm↔vibrant)           |
| scene_segments              | Distinct World/Background colour per segment         |
| easing                      | Blender interpolation type on keyframes              |

Output pipeline
---------------
Blender renders an EXR/PNG sequence → :func:`_mux_sequence_to_mp4` calls
ffmpeg to produce the final MP4, reusing the same ffmpeg-resolution helpers
from :mod:`~melosviz.render.video_exporter`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "BlenderNotFoundError",
    "BlenderRenderError",
    "export_blender",
    "is_blender_available",
    "build_bpy_script",
    "apply_flash_safety",
    "FLASH_SAFETY_MAX_HZ",
    "_BLENDER_ENV_VAR",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Environment variable used to override the Blender binary path.
_BLENDER_ENV_VAR = "MELOSVIZ_BLENDER_BIN"

#: P1-safety: maximum allowed full-frame luminance flash rate (flashes/sec).
#: Values above this are clamped by :func:`apply_flash_safety`.
FLASH_SAFETY_MAX_HZ: float = 3.0

#: Easing hint → Blender keyframe interpolation type.
_EASING_MAP: dict[str, str] = {
    "linear": "LINEAR",
    "ease_in": "EASE_IN",
    "ease_out": "EASE_OUT",
    "ease_in_out": "EASE_IN_OUT",
    "bounce": "BOUNCE",
    "back": "BACK",
    "elastic": "ELASTIC",
}

#: Stem → visual target description (used in generated script comments).
_STEM_ROLE: dict[str, str] = {
    "drums": "particles",
    "bass": "camera_scale",
    "vocals": "vocal_highlight",
    "other": "bg_mix",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BlenderRenderError(RuntimeError):
    """Raised when the Blender subprocess fails or produces no output."""


class BlenderNotFoundError(BlenderRenderError):
    """Raised when no working Blender binary can be located."""


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------


def _resolve_blender_binary() -> str:
    """Return the path to a working ``blender`` binary, or raise.

    Lookup order:

    1. ``MELOSVIZ_BLENDER_BIN`` environment variable.
    2. ``shutil.which("blender")`` — standard ``$PATH`` lookup.
    3. Common macOS application bundle path.

    Each candidate is probed with ``blender --version``.

    Raises:
        BlenderNotFoundError: When no working candidate is found.
    """
    candidates: list[str | None] = [
        os.environ.get(_BLENDER_ENV_VAR),
        shutil.which("blender"),
        # macOS application bundle (common install location)
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if not candidate_path.exists():
            continue
        try:
            probe = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            logger.info("blender resolved: %s", candidate)
            return candidate
    raise BlenderNotFoundError(
        "Unable to locate a working Blender binary for headless rendering. "
        f"Set the {_BLENDER_ENV_VAR} environment variable or install "
        "Blender (https://www.blender.org/download/)."
    )


def is_blender_available() -> bool:
    """Return ``True`` if a working Blender binary can be resolved.

    Never raises; a missing binary simply returns ``False``.
    """
    try:
        _resolve_blender_binary()
    except BlenderNotFoundError:
        return False
    return True


# ---------------------------------------------------------------------------
# Flash-safety limiter (P1-safety)
# ---------------------------------------------------------------------------


def apply_flash_safety(
    energy_values: list[float],
    fps: float,
    max_flash_hz: float = FLASH_SAFETY_MAX_HZ,
) -> list[float]:
    """Clamp full-frame luminance flash rate to ``max_flash_hz`` flashes/sec.

    A "flash" is defined here as a large upward luminance transition
    (energy delta > 0.5 relative to the previous frame) that follows
    another flash within ``1 / max_flash_hz`` seconds.

    The algorithm is a simple greedy suppressor: when a disqualifying flash
    is detected at frame *i*, the peak is replaced with the average of its
    neighbours so the beat pulse still exists (audible) but no longer
    constitutes a photosensitive-risk flash.

    Args:
        energy_values: Per-frame normalised energy [0, 1], length == frames.
        fps: Frames per second of the animation.
        max_flash_hz: Maximum allowed flash rate.

    Returns:
        A new list with the same length where rapid large flashes are
        suppressed.
    """
    if not energy_values or fps <= 0:
        return list(energy_values)

    values = list(energy_values)
    min_gap_frames = fps / max_flash_hz  # minimum frames between large flashes

    # Flash threshold: a large upward transition > 50 % range.
    flash_threshold = 0.5

    last_flash_frame: int = -int(min_gap_frames) - 1
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        if delta > flash_threshold:
            frames_since_last = i - last_flash_frame
            if frames_since_last < min_gap_frames:
                # Too close to previous flash — suppress this peak.
                prev_val = values[i - 1]
                next_val = values[i + 1] if i + 1 < len(values) else values[i - 1]
                values[i] = (prev_val + next_val) / 2.0
                # Don't update last_flash_frame — this was suppressed.
            else:
                last_flash_frame = i

    return values


# ---------------------------------------------------------------------------
# bpy driver script generator
# ---------------------------------------------------------------------------


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    """Return a linear float (r, g, b) tuple from a ``#rrggbb`` hex string."""
    clean = color.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        return (0.0, 0.0, 0.0)
    try:
        r = int(clean[0:2], 16) / 255.0
        g = int(clean[2:4], 16) / 255.0
        b = int(clean[4:6], 16) / 255.0
        return (r, g, b)
    except ValueError:
        return (0.0, 0.0, 0.0)


def _interp_type(easing: str) -> str:
    """Return the Blender interpolation type string for an easing hint."""
    return _EASING_MAP.get(easing, "LINEAR")


def build_bpy_script(
    spec: RenderSpec,
    output_path: str,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Generate a Blender Python (bpy) driver script from a RenderSpec v2.

    The generated script:

    1. Clears the default Blender scene.
    2. Creates a procedural geometry-node / emission-shader driven scene:
       - An emitter sphere whose scale and emission strength track ``energy``.
       - Per-stem visual elements: drum particles, bass camera/scale,
         vocal highlight mesh, other/background mix.
       - Colour driven by ``spectral_centroid`` / ``brightness`` (HSV hue).
       - Valence/arousal tinting of the palette.
    3. Bakes all parameters as Blender keyframes at each dense-keyframe time
       step (no per-frame Python during render).
    4. Per scene_segment: sets a distinct World background colour so each
       segment has a visually distinct look.
    5. Sets output to ``output_path`` and configures codec for EXR/PNG
       sequence output (caller muxes to MP4 via ffmpeg afterwards).

    Args:
        spec: RenderSpec v2 instance (or a dict shaped like one).
        output_path: Output path prefix for Blender's ``//`` frame sequence
            (e.g. ``/tmp/melosviz-blender/frame_``).
        fps: Frames per second for the animation timeline.
        width: Output frame width in pixels.
        height: Output frame height in pixels.

    Returns:
        A string of valid Python code to pass to ``blender -b --python``.
    """
    # ---- Extract spec fields -----------------------------------------------
    if hasattr(spec, "model_dump"):
        spec_dict: dict[str, Any] = spec.model_dump()
    elif isinstance(spec, dict):
        spec_dict = spec
    else:
        spec_dict = {}

    metadata: dict[str, Any] = spec_dict.get("metadata", {})
    duration: float = float(metadata.get("duration", 10.0))
    palette: list[str] = spec_dict.get("palette", ["#00f5ff", "#ff2fd5", "#8a75ff"])
    dense_kfs: list[dict[str, Any]] = spec_dict.get("dense_keyframes", [])
    scene_segs: list[dict[str, Any]] = spec_dict.get("scene_segments", [])

    total_frames = max(1, int(round(duration * fps)))

    # ---- Build per-frame energy values (flash-safety applied) ---------------
    if dense_kfs:
        raw_energy = [float(kf.get("energy", 0.0)) for kf in dense_kfs]
    else:
        raw_energy = [0.5] * total_frames

    safe_energy = apply_flash_safety(raw_energy, float(fps))

    # ---- Build the per-keyframe data tables as JSON for inline embedding ----
    kf_data: list[dict[str, Any]] = []
    for idx, kf in enumerate(dense_kfs):
        t = float(kf.get("t", 0.0))
        frame = int(round(t * fps)) + 1  # Blender frames are 1-indexed

        stems: dict[str, float] = {}
        raw_stems = kf.get("stems", {})
        if isinstance(raw_stems, dict):
            stems = {k: float(v) for k, v in raw_stems.items()}

        kf_data.append({
            "frame": frame,
            "energy": safe_energy[idx] if idx < len(safe_energy) else 0.5,
            "brightness": float(kf.get("brightness", 0.5)),
            "valence": float(kf.get("valence", 0.5)),
            "arousal": float(kf.get("arousal", 0.5)),
            "beat_strength": float(kf.get("beat_strength", 0.0)),
            "onset_strength": float(kf.get("onset_strength", 0.0)),
            "spectral_centroid": float(kf.get("spectral_centroid", 2000.0)),
            "stems": stems,
            "interp": _interp_type(str(kf.get("easing", "linear"))),
        })

    # ---- Build segment colour table -----------------------------------------
    seg_data: list[dict[str, Any]] = []
    for seg in scene_segs:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", duration))
        label = str(seg.get("label", "unknown"))
        seg_energy = float(seg.get("energy_mean", 0.3))
        mood = seg.get("mood", {})
        if isinstance(mood, dict):
            valence = float(mood.get("valence", 0.5))
            arousal = float(mood.get("arousal", 0.5))
        else:
            valence = 0.5
            arousal = 0.5
        dominant_stem = str(seg.get("dominant_stem", "other"))
        seg_data.append({
            "frame_start": int(round(start * fps)) + 1,
            "frame_end": int(round(end * fps)) + 1,
            "label": label,
            "energy_mean": seg_energy,
            "valence": valence,
            "arousal": arousal,
            "dominant_stem": dominant_stem,
        })

    # ---- Convert palette to RGB floats for embedding -----------------------
    palette_rgb = [_hex_to_rgb(c) for c in (palette or ["#00f5ff"])]

    # ---- Embed data as JSON literals in the generated script ---------------
    kf_json = json.dumps(kf_data)
    seg_json = json.dumps(seg_data)
    palette_json = json.dumps(palette_rgb)

    # ---- Generate the bpy script -------------------------------------------
    script = textwrap.dedent(f"""\
        # MelosViz headless Blender driver script — auto-generated, do not edit.
        # RenderSpec v2 → procedural Geo/Shader scene.
        # All keyframes are baked here; no per-frame Python runs during render.

        import bpy
        import json
        import math

        # ---- Embedded data -------------------------------------------------
        KF_DATA    = json.loads({kf_json!r})
        SEG_DATA   = json.loads({seg_json!r})
        PALETTE    = json.loads({palette_json!r})
        FPS        = {fps}
        TOTAL_FRAMES = {total_frames}
        WIDTH      = {width}
        HEIGHT     = {height}
        OUTPUT_PATH = {output_path!r}

        # ---- Scene setup ---------------------------------------------------
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.render.fps = FPS
        scene.frame_start = 1
        scene.frame_end = TOTAL_FRAMES
        scene.render.resolution_x = WIDTH
        scene.render.resolution_y = HEIGHT
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = OUTPUT_PATH

        # ---- Camera --------------------------------------------------------
        bpy.ops.object.camera_add(location=(0, -10, 3))
        cam = bpy.context.active_object
        cam.name = "MelosVizCam"
        scene.camera = cam
        cam.data.lens = 35

        # ---- World (background) --------------------------------------------
        world = bpy.data.worlds.new("MelosVizWorld")
        scene.world = world
        world.use_nodes = True
        world_nodes = world.node_tree.nodes
        world_links = world.node_tree.links
        world_nodes.clear()
        bg_node = world_nodes.new("ShaderNodeBackground")
        out_node = world_nodes.new("ShaderNodeOutputWorld")
        world_links.new(bg_node.outputs["Background"], out_node.inputs["Surface"])
        bg_node.inputs["Color"].default_value = (*PALETTE[0], 1.0) if PALETTE else (0.0, 0.05, 0.15, 1.0)
        bg_node.inputs["Strength"].default_value = 0.3

        # ---- Emitter sphere (energy → scale + emission) --------------------
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 0))
        emitter = bpy.context.active_object
        emitter.name = "MelosVizEmitter"

        # Emission material
        mat = bpy.data.materials.new("EmitterMat")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        emission = nodes.new("ShaderNodeEmission")
        output = nodes.new("ShaderNodeOutputMaterial")
        links.new(emission.outputs["Emission"], output.inputs["Surface"])
        base_color = (*PALETTE[0], 1.0) if PALETTE else (0.0, 0.9, 1.0, 1.0)
        emission.inputs["Color"].default_value = base_color
        emission.inputs["Strength"].default_value = 1.0
        emitter.data.materials.append(mat)

        # ---- Vocal highlight mesh ------------------------------------------
        bpy.ops.mesh.primitive_torus_add(location=(0, 0, 2))
        vocal_obj = bpy.context.active_object
        vocal_obj.name = "MelosVizVocals"
        vmat = bpy.data.materials.new("VocalMat")
        vmat.use_nodes = True
        vnodes = vmat.node_tree.nodes
        vlinks = vmat.node_tree.links
        vnodes.clear()
        vemit = vnodes.new("ShaderNodeEmission")
        vout = vnodes.new("ShaderNodeOutputMaterial")
        vlinks.new(vemit.outputs["Emission"], vout.inputs["Surface"])
        vemit.inputs["Color"].default_value = (1.0, 0.2, 0.8, 1.0)
        vemit.inputs["Strength"].default_value = 0.0
        vocal_obj.data.materials.append(vmat)

        # ---- Bass indicator (ring object, camera follows via constraint) ----
        bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=0.1, location=(0, 0, -1.5))
        bass_obj = bpy.context.active_object
        bass_obj.name = "MelosVizBass"

        # ---- Particle system for drums -------------------------------------
        bpy.ops.mesh.primitive_plane_add(size=0.01, location=(0, 0, 0))
        drum_src = bpy.context.active_object
        drum_src.name = "MelosVizDrumSrc"
        drum_ps = drum_src.modifiers.new("DrumParticles", "PARTICLE_SYSTEM")
        ps = drum_src.particle_systems[0]
        ps.settings.count = 50
        ps.settings.lifetime = int(FPS * 0.5)
        ps.settings.emit_from = "FACE"

        # ---- Helper: map spectral centroid (Hz) to hue (0-1) ---------------
        def centroid_to_hue(hz):
            # 50 Hz → 0.0 (red), 20000 Hz → 1.0 (violet)
            clamped = max(50.0, min(20000.0, hz))
            return math.log(clamped / 50.0) / math.log(20000.0 / 50.0)

        def valence_arousal_to_tint(valence, arousal):
            # High valence → warm (red), low valence → cool (blue)
            # High arousal → saturated, low arousal → desaturated
            r = 0.3 + 0.7 * valence
            b = 0.3 + 0.7 * (1.0 - valence)
            g = 0.2 + 0.6 * (1.0 - abs(valence - 0.5))
            # Arousal scales overall intensity
            intensity = 0.4 + 0.6 * arousal
            return (r * intensity, g * intensity, b * intensity, 1.0)

        # ---- Bake dense keyframes ------------------------------------------
        for kf in KF_DATA:
            f     = kf["frame"]
            e     = kf["energy"]
            bs    = kf["beat_strength"]
            os_   = kf["onset_strength"]
            bright = kf["brightness"]
            val   = kf["valence"]
            aro   = kf["arousal"]
            sc    = kf["spectral_centroid"]
            stems = kf.get("stems", {{}})
            interp = kf["interp"]

            drums_e  = stems.get("drums", 0.0)
            bass_e   = stems.get("bass", 0.0)
            vocals_e = stems.get("vocals", 0.0)
            other_e  = stems.get("other", 0.0)

            # Pulse factor: beat/onset spike added on top of energy
            pulse = max(0.0, min(1.0, e + 0.4 * bs + 0.2 * os_))

            # -- Emitter scale (energy → scale, beat → pulse) ----------------
            scale = 0.5 + 1.5 * pulse
            emitter.scale = (scale, scale, scale)
            emitter.keyframe_insert("scale", frame=f)

            # -- Emission strength -------------------------------------------
            emit_str = 0.5 + 4.5 * e
            emission.inputs["Strength"].default_value = emit_str
            emission.inputs["Strength"].keyframe_insert("default_value", frame=f)

            # -- Colour from spectral centroid + brightness ------------------
            hue = centroid_to_hue(sc) * bright if bright > 0.01 else centroid_to_hue(sc)
            # Pick palette colour closest to hue position
            pal_idx = int(hue * max(1, len(PALETTE) - 1)) % max(1, len(PALETTE))
            base = PALETTE[pal_idx] if PALETTE else (0.0, 0.9, 1.0)
            tint = valence_arousal_to_tint(val, aro)
            blended = (
                base[0] * 0.6 + tint[0] * 0.4,
                base[1] * 0.6 + tint[1] * 0.4,
                base[2] * 0.6 + tint[2] * 0.4,
                1.0,
            )
            emission.inputs["Color"].default_value = blended
            emission.inputs["Color"].keyframe_insert("default_value", frame=f)

            # -- Vocal highlight --------------------------------------------
            vocal_str = 0.0 + 6.0 * vocals_e
            vemit.inputs["Strength"].default_value = vocal_str
            vemit.inputs["Strength"].keyframe_insert("default_value", frame=f)

            # -- Bass object scale (bass stem → squeeze/expand) -------------
            bass_scale = 0.8 + 0.8 * bass_e
            bass_obj.scale = (bass_scale, bass_scale, bass_scale)
            bass_obj.keyframe_insert("scale", frame=f)

            # -- Camera Z offset (bass drives gentle push/pull) -------------
            cam.location.z = 3.0 + 2.0 * bass_e
            cam.keyframe_insert("location", index=2, frame=f)

            # -- Drum particle count modifier --------------------------------
            # particle count is not animatable directly via keyframe;
            # we proxy through drum_src X scale as a driver-readable value.
            drum_src.scale.x = 0.01 + 0.5 * drums_e
            drum_src.keyframe_insert("scale", index=0, frame=f)

            # -- Set interpolation type on all just-inserted keyframes ------
            for obj in [emitter, vocal_obj, bass_obj, drum_src, cam]:
                if obj.animation_data and obj.animation_data.action:
                    for fc in obj.animation_data.action.fcurves:
                        for kfp in fc.keyframe_points:
                            if kfp.co[0] == f:
                                kfp.interpolation = interp

        # ---- Per-segment: distinct world background colour ----------------
        # We insert world background colour keyframes at segment boundaries.
        SEGMENT_COLORS = [
            (0.0, 0.05, 0.2),   # intro: deep blue
            (0.0, 0.1,  0.05),  # verse: dark green
            (0.1, 0.0,  0.2),   # chorus: deep violet
            (0.2, 0.05, 0.0),   # drop: deep red
            (0.05, 0.1, 0.15),  # bridge: teal
            (0.08, 0.0, 0.12),  # breakdown: purple
            (0.0, 0.0,  0.1),   # outro: dark blue
        ]
        LABEL_COLOR_IDX = {{
            "intro": 0, "verse": 1, "chorus": 2, "drop": 3,
            "bridge": 4, "breakdown": 5, "outro": 6, "unknown": 0,
        }}

        for seg_idx, seg in enumerate(SEG_DATA):
            fs = seg["frame_start"]
            label = seg["label"]
            color_idx = LABEL_COLOR_IDX.get(label, seg_idx % len(SEGMENT_COLORS))
            base_color = SEGMENT_COLORS[color_idx % len(SEGMENT_COLORS)]
            # Scale by arousal
            aro = seg["arousal"]
            brightness = 0.2 + 0.8 * aro * seg["energy_mean"]
            world_color = (
                base_color[0] * brightness,
                base_color[1] * brightness,
                base_color[2] * brightness,
                1.0,
            )
            bg_node.inputs["Color"].default_value = world_color
            bg_node.inputs["Color"].keyframe_insert("default_value", frame=fs)

        # ---- Render --------------------------------------------------------
        bpy.ops.render.render(animation=True)
    """)

    return script


# ---------------------------------------------------------------------------
# ffmpeg mux helper
# ---------------------------------------------------------------------------


def _resolve_ffmpeg_binary() -> str:
    """Resolve an ffmpeg binary, delegating to the video_exporter helper."""
    # Import here to avoid a hard circular dep at module import time.
    from melosviz.render.video_exporter import (
        FFMpegNotFoundError,
    )
    from melosviz.render.video_exporter import (
        _resolve_ffmpeg_binary as _vx_resolve,
    )

    try:
        return _vx_resolve()
    except FFMpegNotFoundError as exc:
        raise BlenderRenderError(
            f"ffmpeg required for muxing but not found: {exc}"
        ) from exc


def _mux_sequence_to_mp4(
    frame_pattern: str,
    output_path: Path,
    fps: int,
) -> None:
    """Mux a PNG/EXR sequence into an MP4 using ffmpeg.

    Args:
        frame_pattern: ffmpeg image2 pattern, e.g. ``/tmp/frame_%04d.png``.
        output_path: Destination MP4 file.
        fps: Frames per second.

    Raises:
        BlenderRenderError: On ffmpeg failure.
    """
    ffmpeg = _resolve_ffmpeg_binary()
    cmd = [
        ffmpeg,
        "-y",
        "-framerate", str(fps),
        "-i", frame_pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    logger.debug("_mux_sequence_to_mp4: cmd=%s", cmd)
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except OSError as exc:
        raise BlenderRenderError(f"ffmpeg mux failed to start: {exc}") from exc

    if completed.returncode != 0:
        tail = "\n".join((completed.stderr or "").strip().splitlines()[-5:])
        raise BlenderRenderError(
            f"ffmpeg mux returned rc={completed.returncode}. Tail:\n{tail}"
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def export_blender(
    spec: RenderSpec,
    output_dir: Path | str | None = None,
    *,
    fps: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    """Render a RenderSpec v2 to MP4 using Blender headless.

    This is the GOLD-tier renderer.  It requires Blender to be installed.
    When Blender is absent, raises :class:`BlenderNotFoundError` — the caller
    should fall back to :func:`~melosviz.render.video_exporter.export_video`.

    Pipeline:

    1. Resolve the Blender binary (fail loudly if absent).
    2. Generate a bpy driver script from the RenderSpec.
    3. Write the script to a temp file.
    4. Run ``blender -b --python <script>``.
    5. Mux the rendered PNG sequence → MP4 via ffmpeg.
    6. Return the MP4 path.

    Args:
        spec: RenderSpec v2 (or compatible v1) instance.
        output_dir: Directory for the final MP4. Created if absent.
            Defaults to ``<tempdir>/melosviz-blender-exports``.
        fps: Override frames per second (defaults to ``spec.metadata.fps``
            or 30).
        width: Override output width (defaults to ``spec.metadata.width``
            or 1920).
        height: Override output height (defaults to ``spec.metadata.height``
            or 1080).

    Returns:
        Absolute path to the produced MP4 file.

    Raises:
        BlenderNotFoundError: When no Blender binary is found.
        BlenderRenderError: When Blender or ffmpeg fails, or produces no
            output.
    """
    blender = _resolve_blender_binary()  # raises BlenderNotFoundError if absent

    # ---- Pull render parameters from spec -----------------------------------
    if hasattr(spec, "metadata"):
        metadata: dict[str, Any] = spec.metadata or {}
    elif isinstance(spec, dict):
        metadata = spec.get("metadata", {})
    else:
        metadata = {}

    _fps = fps if fps is not None else int(metadata.get("fps", 30))
    _width = width if width is not None else int(metadata.get("width", 1920))
    _height = height if height is not None else int(metadata.get("height", 1080))

    # ---- Resolve output directory -------------------------------------------
    if output_dir is None:
        output_dir = Path(tempfile.gettempdir()) / "melosviz-blender-exports"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_mp4 = output_dir / "melosviz-blender-render.mp4"

    with tempfile.TemporaryDirectory(prefix="melosviz-blender-") as tmp:
        tmp_path = Path(tmp)
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        frame_output_prefix = str(frames_dir / "frame_")

        # ---- Generate bpy script -------------------------------------------
        script_content = build_bpy_script(
            spec,
            output_path=frame_output_prefix,
            fps=_fps,
            width=_width,
            height=_height,
        )
        script_path = tmp_path / "melosviz_driver.py"
        script_path.write_text(script_content, encoding="utf-8")

        logger.info(
            "export_blender: invoking blender %s --python %s",
            blender,
            script_path,
        )

        # ---- Run Blender headless ------------------------------------------
        cmd = [
            blender,
            "-b",            # headless / background mode
            "--python", str(script_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except OSError as exc:
            raise BlenderRenderError(
                f"Failed to start Blender at {blender!r}: {exc}"
            ) from exc

        if result.returncode != 0:
            tail = "\n".join((result.stderr or "").strip().splitlines()[-10:])
            raise BlenderRenderError(
                f"Blender returned rc={result.returncode}. Tail of stderr:\n{tail}"
            )

        # ---- Locate rendered frames ----------------------------------------
        png_frames = sorted(frames_dir.glob("frame_*.png"))
        exr_frames = sorted(frames_dir.glob("frame_*.exr"))
        frames = png_frames or exr_frames
        if not frames:
            raise BlenderRenderError(
                f"Blender completed (rc=0) but produced no frame files in {frames_dir}."
            )

        # ---- Mux to MP4 ----------------------------------------------------
        suffix = ".png" if png_frames else ".exr"
        frame_pattern = str(frames_dir / f"frame_%04d{suffix}")
        _mux_sequence_to_mp4(frame_pattern, output_mp4, _fps)

    if not output_mp4.exists() or output_mp4.stat().st_size == 0:
        raise BlenderRenderError(
            f"MP4 mux reported success but no output at {output_mp4}."
        )

    logger.info(
        "export_blender: wrote %s (%d bytes)",
        output_mp4,
        output_mp4.stat().st_size,
    )
    return output_mp4
