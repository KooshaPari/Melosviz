"""After Effects / nexrender conductor adapter — ``motion_graphics_beat_sync``.

Generates a `nexrender <https://github.com/inlife/nexrender>`_-compatible job
JSON spec + a data-driven MOGRT parameter map from a
:class:`~melosviz.analysis.models.RenderSpec` v2 payload.

Design
------
* **Wrap-over-handroll**: we generate a nexrender job spec (JSON) consumed
  by the nexrender CLI / aerender worker.  We do NOT shell into AE directly;
  the serialised spec is the artifact.
* **Generator pattern**: no AE runtime is required here — specs are generated
  and validated as plain JSON.  Tests assert on the emitted spec structure,
  matching the P3/P5 approach (Blender/TD headless generators).
* **Beat → keyframe mapping**: ``dense_keyframes`` beats and onsets drive
  MOGRT expression-linked data files (``beats.csv``, ``onsets.csv``).
  Segment-level ``label`` drives template selection from a MOGRT library.
* **Roto Brush 3 performer-isolation hook**: when a ``source_video`` path is
  present in the spec metadata, an aerender ``rotobrush3`` asset entry is
  emitted so AE's Roto Brush 3 pass can isolate performers from background
  before compositing with MOGRT layers.
* **Fail-loud**: :func:`build_ae_job_spec` raises :class:`AESpecError` when
  required fields are missing; it never returns a partial spec silently.

Job spec shape (nexrender v2)::

    {
      "schema": "https://nexrender.com/schema/v2/job.json",
      "template": {
        "src": "file:///path/to/project.aep",
        "composition": "MotionGraphicsBeatSync",
        "frameStart": 0,
        "frameEnd": <total_frames>,
        "outputModule": "h264_main",
        "outputExt": "mp4"
      },
      "assets": [
        { "type": "data",  "layerName": "beat_data",   "property": "Source File", ... },
        { "type": "data",  "layerName": "onset_data",  "property": "Source File", ... },
        { "type": "data",  "layerName": "segment_data","property": "Source File", ... },
        { "type": "data",  "layerName": "palette_data","property": "Source File", ... },
        // optional: rotobrush3 performer isolation
        { "type": "footage", "layerName": "rotobrush3_source", "src": "...", ... }
      ],
      "actions": {
        "prerender": [],
        "postrender": [
          { "module": "@nexrender/action-encode", "preset": "mp4", ... }
        ]
      },
      "mogrt_params": {
        "<segment_label>": { <MOGRT param map for template selection> },
        ...
      },
      "melosviz_meta": {
        "scene_type": "motion_graphics_beat_sync",
        "render_spec_version": 2,
        "duration": <float>,
        "fps": <int>,
        "segment_count": <int>,
        "beat_count": <int>,
        "has_rotobrush3": <bool>
      }
    }
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "AEAdapter",
    "AESpecError",
    "AERenderResult",
    "build_ae_job_spec",
    "build_mogrt_param_map",
    "build_beats_csv",
    "build_onsets_csv",
    "build_segment_csv",
    "SCENE_TYPE",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Conductor scene-type key this adapter handles.
SCENE_TYPE = "motion_graphics_beat_sync"

#: Default AEP project path placeholder (operator sets real path via env/config).
_DEFAULT_AEP_SRC = "file:///melosviz/templates/MotionGraphicsBeatSync.aep"

#: Default nexrender composition name.
_DEFAULT_COMPOSITION = "MotionGraphicsBeatSync"

#: nexrender schema URL.
_NEXRENDER_SCHEMA = "https://nexrender.com/schema/v2/job.json"

#: MOGRT template library — map segment labels to template names.
_SEGMENT_TEMPLATE_MAP: dict[str, str] = {
    "intro": "IntroReveal",
    "verse": "VerseSubtle",
    "chorus": "ChorusBurst",
    "drop": "DropImpact",
    "bridge": "BridgeTransition",
    "breakdown": "BreakdownPulse",
    "outro": "OutroFade",
    "unknown": "DefaultBeatSync",
}

#: Dominant-stem → MOGRT layer-param override mapping.
_STEM_LAYER_PARAMS: dict[str, dict[str, Any]] = {
    "drums": {"rhythm_layer_opacity": 1.0, "melody_layer_opacity": 0.3},
    "bass": {"bass_waveform_scale": 1.5, "rhythm_layer_opacity": 0.6},
    "vocals": {"vocal_text_opacity": 1.0, "melody_layer_opacity": 1.0},
    "other": {"ambient_layer_opacity": 0.8},
}


# ---------------------------------------------------------------------------
# Exceptions / result
# ---------------------------------------------------------------------------


class AESpecError(RuntimeError):
    """Raised when a nexrender job spec cannot be built from the given RenderSpec.

    Never raised silently — callers must handle or propagate.
    """


class AERenderResult:
    """Outcome of a successful :meth:`AEAdapter.render` call.

    Attributes:
        job_spec: The nexrender job spec as a JSON-serialisable dict.
        job_spec_path: Path where the spec was written (None if no output_path given).
        beats_csv: Beat timing CSV content (string).
        onsets_csv: Onset timing CSV content (string).
        segment_csv: Segment metadata CSV content (string).
    """

    def __init__(
        self,
        job_spec: dict[str, Any],
        job_spec_path: Any | None = None,
        beats_csv: str = "",
        onsets_csv: str = "",
        segment_csv: str = "",
    ) -> None:
        self.job_spec = job_spec
        self.job_spec_path = job_spec_path
        self.beats_csv = beats_csv
        self.onsets_csv = onsets_csv
        self.segment_csv = segment_csv


# ---------------------------------------------------------------------------
# CSV data builders (beat/onset/segment data files for MOGRT expressions)
# ---------------------------------------------------------------------------


def build_beats_csv(dense_keyframes: list[dict[str, Any]]) -> str:
    """Build a CSV string mapping beat times → beat_strength for MOGRT expressions.

    Columns: ``t``, ``beat_strength``, ``energy``.
    Only keyframes with ``beat_strength > 0`` are included (actual beat frames).

    Args:
        dense_keyframes: List of dense-keyframe dicts from RenderSpec v2.

    Returns:
        CSV string (UTF-8, LF line endings, header row included).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["t", "beat_strength", "energy"])
    for kf in dense_keyframes:
        bs = float(kf.get("beat_strength", 0.0))
        if bs > 0.0:
            writer.writerow([
                round(float(kf.get("t", 0.0)), 4),
                round(bs, 4),
                round(float(kf.get("energy", 0.0)), 4),
            ])
    return buf.getvalue()


def build_onsets_csv(dense_keyframes: list[dict[str, Any]]) -> str:
    """Build a CSV string mapping onset times → onset_strength for MOGRT expressions.

    Columns: ``t``, ``onset_strength``, ``brightness``.
    Only keyframes with ``onset_strength > 0`` are included.

    Args:
        dense_keyframes: List of dense-keyframe dicts from RenderSpec v2.

    Returns:
        CSV string (UTF-8, LF line endings, header row included).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["t", "onset_strength", "brightness"])
    for kf in dense_keyframes:
        os_ = float(kf.get("onset_strength", 0.0))
        if os_ > 0.0:
            writer.writerow([
                round(float(kf.get("t", 0.0)), 4),
                round(os_, 4),
                round(float(kf.get("brightness", 0.0)), 4),
            ])
    return buf.getvalue()


def build_segment_csv(scene_segments: list[dict[str, Any]]) -> str:
    """Build a CSV string with segment metadata for MOGRT template layer switching.

    Columns: ``index``, ``label``, ``start``, ``end``, ``energy_mean``,
    ``dominant_stem``, ``valence``, ``arousal``, ``mogrt_template``.

    Args:
        scene_segments: List of scene-segment dicts from RenderSpec v2.

    Returns:
        CSV string (UTF-8, LF line endings, header row included).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([
        "index", "label", "start", "end",
        "energy_mean", "dominant_stem", "valence", "arousal", "mogrt_template",
    ])
    for seg in scene_segments:
        label = str(seg.get("label", "unknown"))
        mood = seg.get("mood", {})
        if isinstance(mood, dict):
            valence = float(mood.get("valence", 0.5))
            arousal = float(mood.get("arousal", 0.5))
        else:
            valence = 0.5
            arousal = 0.5
        writer.writerow([
            int(seg.get("index", 0)),
            label,
            round(float(seg.get("start", 0.0)), 4),
            round(float(seg.get("end", 0.0)), 4),
            round(float(seg.get("energy_mean", 0.0)), 4),
            str(seg.get("dominant_stem", "other")),
            round(valence, 4),
            round(arousal, 4),
            _SEGMENT_TEMPLATE_MAP.get(label, "DefaultBeatSync"),
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# MOGRT parameter map builder
# ---------------------------------------------------------------------------


def build_mogrt_param_map(
    scene_segments: list[dict[str, Any]],
    palette: list[str],
    mir: dict[str, Any],
) -> dict[str, Any]:
    """Build a per-segment MOGRT parameter map for data-driven template selection.

    Each entry in the returned dict maps a segment label to a dict of MOGRT
    expression-controllable parameter values.  Downstream AE/nexrender
    post-processors write these into the MOGRT Expression Controls.

    Args:
        scene_segments: Segment list from RenderSpec v2.
        palette: Hex colour list from RenderSpec.
        mir: MIR summary dict from RenderSpec v2.

    Returns:
        ``{ "<label>": { <param_key>: <value>, ... }, ... }``
    """
    tempo_bpm = float(mir.get("tempo_bpm") or 0.0)
    danceability = float(mir.get("danceability") or 0.5)
    key = str(mir.get("key") or "C")
    mode = str(mir.get("mode") or "major")

    result: dict[str, Any] = {}
    for seg in scene_segments:
        label = str(seg.get("label", "unknown"))
        mood = seg.get("mood", {})
        if isinstance(mood, dict):
            valence = float(mood.get("valence", 0.5))
            arousal = float(mood.get("arousal", 0.5))
        else:
            valence = 0.5
            arousal = 0.5

        dominant_stem = str(seg.get("dominant_stem", "other"))
        energy_mean = float(seg.get("energy_mean", 0.3))

        # Pick palette colour by segment index (cycle)
        seg_idx = int(seg.get("index", 0))
        base_color = palette[seg_idx % len(palette)] if palette else "#00f5ff"

        # Build base param map
        params: dict[str, Any] = {
            "mogrt_template": _SEGMENT_TEMPLATE_MAP.get(label, "DefaultBeatSync"),
            "primary_color": base_color,
            "energy_scale": round(0.5 + energy_mean, 4),
            "tempo_bpm": round(tempo_bpm, 2),
            "danceability": round(danceability, 4),
            "valence": round(valence, 4),
            "arousal": round(arousal, 4),
            "key_label": f"{key} {mode}",
        }

        # Merge stem-specific layer overrides
        stem_overrides = _STEM_LAYER_PARAMS.get(dominant_stem, {})
        params.update(stem_overrides)

        result[label] = params

    return result


# ---------------------------------------------------------------------------
# Core job-spec builder
# ---------------------------------------------------------------------------


def build_ae_job_spec(
    spec: RenderSpec,
    *,
    aep_src: str | None = None,
    composition: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Generate a nexrender v2 job JSON spec from a RenderSpec v2.

    This is the primary artifact of the AE adapter.  It contains:
    - nexrender ``template`` block (AEP source, composition, frame range).
    - ``assets`` referencing beat/onset/segment/palette CSV data files that
      AE MOGRT expressions load via nexrender's file-injection mechanism.
    - Optional ``rotobrush3`` footage asset when ``source_video`` is present.
    - ``mogrt_params`` map (per-segment MOGRT expression controls).
    - ``melosviz_meta`` describing the source spec version/shape.

    Args:
        spec: RenderSpec v2 instance (or dict-shaped equivalent).
        aep_src: AEP project path / nexrender URI.  Defaults to the
            template constant.  Must be set for real renders.
        composition: AE composition name.  Defaults to the template constant.
        output_dir: Base directory for rendered output assets.  When None,
            defaults to ``/tmp/melosviz-ae-renders``.

    Returns:
        A JSON-serialisable dict shaped as the nexrender v2 job spec.

    Raises:
        AESpecError: When the RenderSpec is missing required v2 fields that
            the MOGRT pipeline depends on (dense_keyframes or scene_segments
            completely absent and no metadata duration).
    """
    # ---- Extract spec fields -----------------------------------------------
    if hasattr(spec, "model_dump"):
        spec_dict: dict[str, Any] = spec.model_dump()
    elif isinstance(spec, dict):
        spec_dict = spec
    else:
        spec_dict = {}

    metadata: dict[str, Any] = spec_dict.get("metadata", {})
    palette: list[str] = spec_dict.get("palette") or ["#00f5ff", "#ff2fd5", "#8a75ff"]
    dense_keyframes: list[dict[str, Any]] = spec_dict.get("dense_keyframes") or []
    scene_segments: list[dict[str, Any]] = spec_dict.get("scene_segments") or []
    mir: dict[str, Any] = spec_dict.get("mir") or {}

    # Validate: we need at least duration from metadata
    duration = float(metadata.get("duration", 0.0))
    if duration <= 0.0:
        raise AESpecError(
            "build_ae_job_spec: RenderSpec metadata.duration is missing or zero. "
            "Cannot build a frame-range-based AE job spec without track duration."
        )

    fps = int(metadata.get("fps", 30))
    if fps <= 0:
        raise AESpecError(
            f"build_ae_job_spec: invalid fps={fps!r} in metadata."
        )

    total_frames = max(1, int(round(duration * fps)))
    source_video: str | None = metadata.get("source_video")
    _aep_src = aep_src or _DEFAULT_AEP_SRC
    _composition = composition or _DEFAULT_COMPOSITION
    _output_dir = output_dir or "/tmp/melosviz-ae-renders"

    # ---- Build data CSVs ---------------------------------------------------
    beats_csv = build_beats_csv(dense_keyframes)
    onsets_csv = build_onsets_csv(dense_keyframes)
    segment_csv = build_segment_csv(scene_segments)

    beat_count = sum(
        1 for kf in dense_keyframes if float(kf.get("beat_strength", 0.0)) > 0.0
    )

    # ---- Build MOGRT param map ---------------------------------------------
    mogrt_params = build_mogrt_param_map(scene_segments, palette, mir)

    # ---- Assets block ------------------------------------------------------
    assets: list[dict[str, Any]] = [
        {
            "type": "data",
            "layerName": "beat_data",
            "property": "Source File",
            "value": f"{_output_dir}/beats.csv",
            "data": beats_csv,
        },
        {
            "type": "data",
            "layerName": "onset_data",
            "property": "Source File",
            "value": f"{_output_dir}/onsets.csv",
            "data": onsets_csv,
        },
        {
            "type": "data",
            "layerName": "segment_data",
            "property": "Source File",
            "value": f"{_output_dir}/segments.csv",
            "data": segment_csv,
        },
        {
            "type": "data",
            "layerName": "palette_data",
            "property": "Source File",
            "value": f"{_output_dir}/palette.json",
            "data": json.dumps({"palette": palette}),
        },
    ]

    # Roto Brush 3 performer-isolation hook: emitted when source_video is set.
    has_rotobrush3 = bool(source_video)
    if has_rotobrush3:
        assets.append({
            "type": "footage",
            "layerName": "rotobrush3_source",
            "src": source_video,
            "composition": _composition,
            "layerIndex": 1,
            "rotobrush3": {
                "enabled": True,
                "refine_edge": True,
                "propagation": "multi_frame",
                "output_layer": "rotobrush3_matte",
            },
        })
        logger.info(
            "build_ae_job_spec: Roto Brush 3 hook enabled for source_video=%s",
            source_video,
        )

    # ---- Actions block ------------------------------------------------------
    actions: dict[str, Any] = {
        "prerender": [],
        "postrender": [
            {
                "module": "@nexrender/action-encode",
                "preset": "mp4",
                "output": f"{_output_dir}/melosviz-ae-render.mp4",
            },
        ],
    }

    # ---- Assemble job spec --------------------------------------------------
    job_spec: dict[str, Any] = {
        "schema": _NEXRENDER_SCHEMA,
        "template": {
            "src": _aep_src,
            "composition": _composition,
            "frameStart": 0,
            "frameEnd": total_frames,
            "outputModule": "h264_main",
            "outputExt": "mp4",
            "settingsTemplate": "_HIDDEN_",
        },
        "assets": assets,
        "actions": actions,
        "mogrt_params": mogrt_params,
        "melosviz_meta": {
            "scene_type": SCENE_TYPE,
            "render_spec_version": 2,
            "duration": duration,
            "fps": fps,
            "total_frames": total_frames,
            "segment_count": len(scene_segments),
            "beat_count": beat_count,
            "has_rotobrush3": has_rotobrush3,
            "palette": palette,
        },
    }

    logger.info(
        "build_ae_job_spec: built spec composition=%s frames=%d segments=%d beats=%d",
        _composition,
        total_frames,
        len(scene_segments),
        beat_count,
    )
    return job_spec


# ---------------------------------------------------------------------------
# Conductor adapter
# ---------------------------------------------------------------------------


class AEAdapter:
    """After Effects / nexrender conductor adapter for ``motion_graphics_beat_sync``.

    Drop-in replacement for the ``motion_graphics_beat_sync`` stub in the
    conductor's adapter registry.  Generates a nexrender job spec + CSV data
    files from a RenderSpec v2, optionally writing them to ``output_path``.

    The adapter does NOT invoke AE or nexrender directly — generated specs
    are artifacts ready for a nexrender worker to consume.

    Args:
        aep_src: Path / URI to the AEP project template.  When None, a
            default placeholder is used.
        composition: AE composition name to render.  Defaults to the
            module constant.
    """

    #: Key used in the conductor adapter registry.
    scene_type: str = SCENE_TYPE

    def __init__(
        self,
        aep_src: str | None = None,
        composition: str | None = None,
    ) -> None:
        self._aep_src = aep_src
        self._composition = composition

    def render(
        self,
        render_spec: RenderSpec,
        *,
        output_path: Any = None,
        **_kwargs: Any,
    ) -> AERenderResult:
        """Generate a nexrender job spec from a RenderSpec v2.

        Args:
            render_spec: A RenderSpec v2 instance.
            output_path: Directory where ``nexrender_job.json``,
                ``beats.csv``, ``onsets.csv``, ``segments.csv`` are written.
                When None, files are not written (in-memory only).
            **_kwargs: Extra kwargs ignored (conductor forward compat).

        Returns:
            :class:`AERenderResult` containing the job spec and CSV data.

        Raises:
            AESpecError: On spec validation failure (never silent).
        """
        import pathlib

        output_dir_str: str | None = None
        if output_path is not None:
            output_dir_str = str(output_path)

        job_spec = build_ae_job_spec(
            render_spec,
            aep_src=self._aep_src,
            composition=self._composition,
            output_dir=output_dir_str or "/tmp/melosviz-ae-renders",
        )

        # Extract CSV data from embedded assets
        beats_csv = next(
            (a["data"] for a in job_spec["assets"] if a.get("layerName") == "beat_data"),
            "",
        )
        onsets_csv = next(
            (a["data"] for a in job_spec["assets"] if a.get("layerName") == "onset_data"),
            "",
        )
        segment_csv = next(
            (a["data"] for a in job_spec["assets"] if a.get("layerName") == "segment_data"),
            "",
        )

        job_spec_path: Any = None
        if output_path is not None:
            out_dir = pathlib.Path(output_path)
            out_dir.mkdir(parents=True, exist_ok=True)
            job_spec_path = out_dir / "nexrender_job.json"
            job_spec_path.write_text(
                json.dumps(job_spec, indent=2), encoding="utf-8"
            )
            (out_dir / "beats.csv").write_text(beats_csv, encoding="utf-8")
            (out_dir / "onsets.csv").write_text(onsets_csv, encoding="utf-8")
            (out_dir / "segments.csv").write_text(segment_csv, encoding="utf-8")
            logger.info("AEAdapter.render: wrote job spec → %s", job_spec_path)

        return AERenderResult(
            job_spec=job_spec,
            job_spec_path=job_spec_path,
            beats_csv=beats_csv,
            onsets_csv=onsets_csv,
            segment_csv=segment_csv,
        )
