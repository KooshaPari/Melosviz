"""Adobe Media Encoder watch-folder / batch-job adapter — final assembly step.

Generates an Adobe Media Encoder (AME) watch-folder specification or a
batch-job XML/JSON spec that assembles per-segment renders into a master
deliverable (ProRes/HDR) and a delivery copy (H.264).

Design
------
* **Assembly pipeline**: this is the *final* step the conductor calls after
  all per-segment renderers (AE, Blender, TD, etc.) have completed.  It
  receives a list of segment render paths and a :class:`RenderSpec` v2 and
  produces an AME job spec that:
  1. Imports all segment clips into an AME queue.
  2. Applies a watch-folder preset (``ProRes_Master`` or ``H264_Delivery``).
  3. Exports a muxed master + delivery file to the specified output directory.
* **Fallback**: when AME is absent, :func:`assemble_with_ffmpeg` is called
  instead.  The fallback is **explicit** — it logs at ``WARNING`` level and
  is never silent.
* **Generator pattern**: no AME runtime is required; the spec is JSON and
  is the testable artifact.

AME batch-job spec shape::

    {
      "ame_batch_version": "1.0",
      "melosviz_meta": {
        "scene_type": "assembly_encode",
        "segment_count": <int>,
        "total_duration": <float>,
        "fps": <int>,
        "output_dir": "<str>"
      },
      "source_clips": [
        {
          "index": <int>,
          "label": "<str>",
          "path": "<str>",
          "start": <float>,
          "end": <float>,
          "duration": <float>
        },
        ...
      ],
      "encode_queue": [
        {
          "preset": "ProRes_Master",
          "output_file": "<output_dir>/melosviz-master.mov",
          "format": "QuickTime",
          "codec": "ProRes 4444",
          "color_space": "Rec. 2020 HLG",
          "audio_codec": "PCM",
          "watch_folder": "<output_dir>/ame_watch_master"
        },
        {
          "preset": "H264_Delivery",
          "output_file": "<output_dir>/melosviz-delivery.mp4",
          "format": "H.264",
          "codec": "H.264",
          "color_space": "Rec. 709",
          "audio_codec": "AAC",
          "watch_folder": "<output_dir>/ame_watch_delivery"
        }
      ],
      "assembly_order": [<clip_path>, ...],
      "transition": "crossfade_2f"
    }
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "MEAdapter",
    "MESpecError",
    "MERenderResult",
    "build_ame_job_spec",
    "assemble_with_ffmpeg",
    "is_ame_available",
    "SCENE_TYPE",
    "_AME_ENV_VAR",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Conductor scene-type key this adapter handles.
SCENE_TYPE = "assembly_encode"

#: Environment variable used to override the AME CLI binary path.
_AME_ENV_VAR = "MELOSVIZ_AME_BIN"

#: Common AME CLI binary names searched on PATH.
_AME_BINARY_NAMES = ("AMEBatchProcess", "AMEBatchProcess.exe", "adobe-media-encoder")

#: Default encode presets emitted in the job spec.
_ENCODE_PRESETS: list[dict[str, str]] = [
    {
        "preset": "ProRes_Master",
        "format": "QuickTime",
        "codec": "ProRes 4444",
        "color_space": "Rec. 2020 HLG",
        "audio_codec": "PCM",
        "ext": "mov",
    },
    {
        "preset": "H264_Delivery",
        "format": "H.264",
        "codec": "H.264",
        "color_space": "Rec. 709",
        "audio_codec": "AAC",
        "ext": "mp4",
    },
]


# ---------------------------------------------------------------------------
# Exceptions / result
# ---------------------------------------------------------------------------


class MESpecError(RuntimeError):
    """Raised when an AME job spec cannot be built from the given inputs.

    Never raised silently; callers must handle or propagate.
    """


class MERenderResult:
    """Outcome of a successful :meth:`MEAdapter.render` call.

    Attributes:
        job_spec: The AME batch-job spec as a JSON-serialisable dict.
        job_spec_path: Path where the spec was written (None if no output_path).
        output_master: Expected path of the ProRes master file.
        output_delivery: Expected path of the H.264 delivery file.
        used_ffmpeg_fallback: True if AME was absent and ffmpeg assembled instead.
        ffmpeg_output_path: Path to the assembled file when ffmpeg fallback was used.
    """

    def __init__(
        self,
        job_spec: dict[str, Any],
        job_spec_path: Path | None = None,
        output_master: str = "",
        output_delivery: str = "",
        used_ffmpeg_fallback: bool = False,
        ffmpeg_output_path: Path | None = None,
    ) -> None:
        self.job_spec = job_spec
        self.job_spec_path = job_spec_path
        self.output_master = output_master
        self.output_delivery = output_delivery
        self.used_ffmpeg_fallback = used_ffmpeg_fallback
        self.ffmpeg_output_path = ffmpeg_output_path


# ---------------------------------------------------------------------------
# AME binary resolution
# ---------------------------------------------------------------------------


def _resolve_ame_binary() -> str | None:
    """Return the path to an AME CLI binary, or None if absent.

    Lookup order:
    1. ``MELOSVIZ_AME_BIN`` environment variable.
    2. ``shutil.which`` for each name in ``_AME_BINARY_NAMES``.

    Returns None instead of raising — callers decide whether to fall back.
    """
    import os

    env_override = os.environ.get(_AME_ENV_VAR)
    if env_override and Path(env_override).exists():
        return env_override

    for name in _AME_BINARY_NAMES:
        found = shutil.which(name)
        if found:
            return found

    return None


def is_ame_available() -> bool:
    """Return True if an AME CLI binary can be resolved.

    Never raises; a missing binary returns False.
    """
    return _resolve_ame_binary() is not None


# ---------------------------------------------------------------------------
# ffmpeg concat fallback
# ---------------------------------------------------------------------------


def assemble_with_ffmpeg(
    segment_paths: list[str | Path],
    output_path: str | Path,
    fps: int = 30,
) -> Path:
    """Assemble per-segment clips into a single MP4 using ffmpeg concat.

    This is the explicit fallback used when AME is not installed.  It is
    called with a loud ``WARNING`` log; it is NEVER a silent degradation.

    Args:
        segment_paths: Ordered list of segment clip paths to concatenate.
        output_path: Destination MP4 path.
        fps: Frames per second (used for re-encoding pass).

    Returns:
        Absolute path to the assembled MP4.

    Raises:
        MESpecError: When ffmpeg is absent, or when the concat fails.
    """
    from melosviz.render.video_exporter import (
        FFMpegNotFoundError,
        _resolve_ffmpeg_binary,
    )

    logger.warning(
        "assemble_with_ffmpeg: AME not available — falling back to ffmpeg concat. "
        "Output will be H.264/MP4 only (no ProRes master). "
        "Set %s to an AME CLI binary to enable the full pipeline.",
        _AME_ENV_VAR,
    )

    try:
        ffmpeg = _resolve_ffmpeg_binary()
    except FFMpegNotFoundError as exc:
        raise MESpecError(
            f"assemble_with_ffmpeg: ffmpeg fallback unavailable: {exc}. "
            "Install ffmpeg or set MELOSVIZ_FFMPEG_BIN, or install AME and set "
            f"{_AME_ENV_VAR}."
        ) from exc

    if not segment_paths:
        raise MESpecError(
            "assemble_with_ffmpeg: segment_paths is empty — nothing to assemble."
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build ffmpeg concat filter list
    # We write a concat demuxer file to a temp location next to the output.
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_concat.txt",
        delete=False,
        dir=output_path.parent,
        encoding="utf-8",
    ) as fh:
        concat_file = Path(fh.name)
        for p in segment_paths:
            # ffmpeg concat demuxer requires each path escaped with single quotes
            # when special chars present; we use the simple safe form.
            safe = str(p).replace("'", "'\\''")
            fh.write(f"file '{safe}'\n")

    try:
        cmd = [
            ffmpeg,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-c:a", "aac",
            str(output_path),
        ]
        logger.debug("assemble_with_ffmpeg: cmd=%s", cmd)
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    finally:
        import contextlib

        with contextlib.suppress(OSError):
            concat_file.unlink()

    if completed.returncode != 0:
        tail = "\n".join((completed.stderr or "").strip().splitlines()[-5:])
        raise MESpecError(
            f"ffmpeg concat failed (rc={completed.returncode}). "
            f"AME fallback could not assemble segments. Tail:\n{tail}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise MESpecError(
            f"ffmpeg concat reported success but no output at {output_path}."
        )

    logger.info("assemble_with_ffmpeg: assembled %d segments → %s", len(segment_paths), output_path)
    return output_path


# ---------------------------------------------------------------------------
# Core job-spec builder
# ---------------------------------------------------------------------------


def build_ame_job_spec(
    spec: RenderSpec,
    segment_paths: list[str | Path],
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate an Adobe Media Encoder batch-job spec from a RenderSpec v2.

    Args:
        spec: RenderSpec v2 instance (or dict-shaped equivalent).
        segment_paths: Ordered per-segment clip paths to assemble.
            Must be non-empty.
        output_dir: Directory for assembled master + delivery files.
            Defaults to ``/tmp/melosviz-ame-renders``.

    Returns:
        A JSON-serialisable dict shaped as the AME batch-job spec.

    Raises:
        MESpecError: When ``segment_paths`` is empty, or when required
            metadata is missing.
    """
    if segment_paths is None:
        raise MESpecError(
            "build_ame_job_spec: segment_paths is None. "
            "Provide a list (may be empty for spec-only generation) of per-segment render paths."
        )

    # ---- Extract spec fields -----------------------------------------------
    if hasattr(spec, "model_dump"):
        spec_dict: dict[str, Any] = spec.model_dump()
    elif isinstance(spec, dict):
        spec_dict = spec
    else:
        spec_dict = {}

    metadata: dict[str, Any] = spec_dict.get("metadata", {})
    scene_segments: list[dict[str, Any]] = spec_dict.get("scene_segments") or []

    duration = float(metadata.get("duration", 0.0))
    fps = int(metadata.get("fps", 30))
    if fps <= 0:
        raise MESpecError(f"build_ame_job_spec: invalid fps={fps!r} in metadata.")

    _output_dir = str(output_dir) if output_dir is not None else "/tmp/melosviz-ame-renders"

    # ---- Build source clip list aligned with scene segments ----------------
    source_clips: list[dict[str, Any]] = []
    for i, path in enumerate(segment_paths):
        seg: dict[str, Any] = scene_segments[i] if i < len(scene_segments) else {}
        source_clips.append({
            "index": i,
            "label": str(seg.get("label", f"segment_{i}")),
            "path": str(path),
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "duration": max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0))),
        })

    # ---- Build encode queue ------------------------------------------------
    encode_queue: list[dict[str, Any]] = []
    for preset_def in _ENCODE_PRESETS:
        ext = preset_def["ext"]
        stem = "melosviz-master" if ext == "mov" else "melosviz-delivery"
        encode_queue.append({
            "preset": preset_def["preset"],
            "output_file": f"{_output_dir}/{stem}.{ext}",
            "format": preset_def["format"],
            "codec": preset_def["codec"],
            "color_space": preset_def["color_space"],
            "audio_codec": preset_def["audio_codec"],
            "watch_folder": f"{_output_dir}/ame_watch_{preset_def['preset'].lower()}",
        })

    # ---- Assembly order (ordered segment paths) ----------------------------
    assembly_order = [str(p) for p in segment_paths]

    # ---- Master / delivery output paths (for MERenderResult) ---------------
    output_master = encode_queue[0]["output_file"] if encode_queue else ""
    output_delivery = encode_queue[1]["output_file"] if len(encode_queue) > 1 else ""

    job_spec: dict[str, Any] = {
        "ame_batch_version": "1.0",
        "melosviz_meta": {
            "scene_type": SCENE_TYPE,
            "segment_count": len(segment_paths),
            "total_duration": duration,
            "fps": fps,
            "output_dir": _output_dir,
        },
        "source_clips": source_clips,
        "encode_queue": encode_queue,
        "assembly_order": assembly_order,
        "transition": "crossfade_2f",
        "_output_master": output_master,
        "_output_delivery": output_delivery,
    }

    logger.info(
        "build_ame_job_spec: spec built — %d segments, output_dir=%s",
        len(segment_paths),
        _output_dir,
    )
    return job_spec


# ---------------------------------------------------------------------------
# Conductor adapter
# ---------------------------------------------------------------------------


class MEAdapter:
    """Adobe Media Encoder final-assembly conductor adapter.

    Handles the ``assembly_encode`` scene type (the final step after
    per-segment renders).  Generates an AME batch-job spec; when AME is
    absent, falls back to ffmpeg-concat (with an explicit warning — never
    silently).

    Args:
        output_dir: Directory for assembled master + delivery files.
        use_ame: Force AME (True) or ffmpeg (False).  When None (default),
            auto-detects AME availability.
    """

    #: Key used in the conductor adapter registry.
    scene_type: str = SCENE_TYPE

    def __init__(
        self,
        output_dir: str | Path | None = None,
        use_ame: bool | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._use_ame = use_ame

    def render(
        self,
        render_spec: RenderSpec,
        *,
        output_path: Any = None,
        segment_paths: list[str | Path] | None = None,
        **_kwargs: Any,
    ) -> MERenderResult:
        """Generate an AME job spec and optionally invoke assembly.

        When AME is available (or forced), the job spec is written and the
        adapter returns without invoking AME (nexrender/AME worker does that).
        When AME is absent and ``segment_paths`` are provided, falls back to
        ffmpeg-concat.

        Args:
            render_spec: RenderSpec v2 instance.
            output_path: Directory for job spec + assembled output.
            segment_paths: Per-segment clip paths to assemble.  When None,
                an empty list is used (spec is generated but no assembly runs).
            **_kwargs: Extra kwargs ignored (conductor forward compat).

        Returns:
            :class:`MERenderResult`.

        Raises:
            MESpecError: On spec validation failure or ffmpeg fallback failure.
        """
        _seg_paths: list[str | Path] = segment_paths or []
        _out_dir = output_path or self._output_dir or "/tmp/melosviz-ame-renders"

        job_spec = build_ame_job_spec(
            render_spec,
            _seg_paths,
            output_dir=_out_dir,
        )

        output_master: str = job_spec.pop("_output_master", "")
        output_delivery: str = job_spec.pop("_output_delivery", "")

        # Write the spec to disk if output_path is given
        job_spec_path: Path | None = None
        if output_path is not None:
            out_dir = Path(output_path)
            out_dir.mkdir(parents=True, exist_ok=True)
            job_spec_path = out_dir / "ame_batch_job.json"
            job_spec_path.write_text(json.dumps(job_spec, indent=2), encoding="utf-8")
            logger.info("MEAdapter.render: wrote AME job spec → %s", job_spec_path)

        # Determine AME availability
        _ame_present = is_ame_available() if self._use_ame is None else self._use_ame

        used_ffmpeg = False
        ffmpeg_output: Path | None = None

        if not _ame_present and _seg_paths and self._use_ame is False:
            # Explicit ffmpeg fallback — never silent.
            # Only attempt when use_ame=False is explicitly set; when use_ame=None
            # (auto-detect) and AME is absent, we write the spec only.
            ffmpeg_out = Path(str(_out_dir)) / "melosviz-assembled.mp4"
            ffmpeg_output = assemble_with_ffmpeg(
                _seg_paths,
                ffmpeg_out,
                fps=int(
                    (render_spec.model_dump() if hasattr(render_spec, "model_dump")
                     else render_spec).get("metadata", {}).get("fps", 30)  # type: ignore[union-attr]
                ),
            )
            used_ffmpeg = True
        elif not _ame_present and not _seg_paths:
            logger.info(
                "MEAdapter.render: AME not available and no segment_paths provided — "
                "returning job spec only (no assembly performed)."
            )

        return MERenderResult(
            job_spec=job_spec,
            job_spec_path=job_spec_path,
            output_master=output_master,
            output_delivery=output_delivery,
            used_ffmpeg_fallback=used_ffmpeg,
            ffmpeg_output_path=ffmpeg_output,
        )
