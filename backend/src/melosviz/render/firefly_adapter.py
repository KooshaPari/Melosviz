"""Adobe Photoshop Firefly generative-asset conductor adapter.

Upgrades the ``generative_asset`` stub (previously wired to
:mod:`~melosviz.render.video_exporter`) to generate Photoshop Firefly REST
API job specs that produce background / texture assets from segment mood and
semantic metadata.

Design
------
* **Generative-asset pipeline**: for each scene segment, the adapter emits a
  Firefly ``/v3/images/generate`` REST job spec.  Prompt text is derived from
  segment ``mood`` (valence/arousal), ``label``, ``dominant_stem``, and the
  track's ``palette``.  The generated background assets are then composited
  downstream (e.g. in AE or Blender).
* **Generator pattern**: no Firefly API key / network call is required during
  spec generation.  The serialised job specs are the testable artifacts; a
  real Firefly worker picks them up and calls the REST API.
* **VideoExport fallback**: when a caller explicitly requests the legacy path
  (``force_video_export=True``) or when Firefly job specs are rejected by a
  downstream validator, :func:`~melosviz.render.video_exporter.export_video`
  is used as a named fallback — this is logged at ``WARNING`` level and is
  never silent.
* **Fail-loud**: :func:`build_firefly_job_specs` raises
  :class:`FireflySpecError` for structurally invalid specs.

Firefly REST job spec shape (one per segment)::

    {
      "firefly_schema": "https://firefly.adobe.io/v3/images/generate",
      "prompt": "<derived from mood/label/stem/palette>",
      "negative_prompt": "<safety / quality negative>",
      "n": 1,
      "size": { "width": 1920, "height": 1080 },
      "styles": [<style_preset_id>],
      "seed": <segment_index * 7919 % 65536>,
      "content_class": "photo",
      "melosviz_meta": {
        "segment_index": <int>,
        "segment_label": "<str>",
        "dominant_stem": "<str>",
        "valence": <float>,
        "arousal": <float>,
        "palette": [<hex>, ...],
        "output_key": "<label>_<index>.png"
      }
    }
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "FireflyAdapter",
    "FireflySpecError",
    "FireflyJobResult",
    "build_firefly_job_specs",
    "derive_firefly_prompt",
    "SCENE_TYPE",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Conductor scene-type key this adapter handles.
SCENE_TYPE = "generative_asset"

#: Firefly v3 image-generation endpoint schema identifier.
_FIREFLY_SCHEMA = "https://firefly.adobe.io/v3/images/generate"

#: Map segment label → Firefly style preset.
_LABEL_STYLE_MAP: dict[str, str] = {
    "intro": "concept_art",
    "verse": "watercolor",
    "chorus": "neon_punk",
    "drop": "synthwave",
    "bridge": "ethereal",
    "breakdown": "abstract_expressionism",
    "outro": "minimalism",
    "unknown": "digital_art",
}

#: Map dominant_stem → visual texture hint.
_STEM_TEXTURE_HINT: dict[str, str] = {
    "drums": "rhythmic patterns, geometric shapes, pulsing light",
    "bass": "deep waveforms, subsonic ripples, dark gradients",
    "vocals": "human form silhouettes, lyrical flow, radiant glow",
    "other": "ambient haze, soft gradients, textured layers",
}

#: Map valence range → mood descriptor.
def _valence_descriptor(valence: float) -> str:
    if valence >= 0.7:
        return "euphoric, joyful, uplifting"
    if valence >= 0.4:
        return "balanced, reflective, warm"
    return "melancholic, introspective, moody"


#: Map arousal range → energy descriptor.
def _arousal_descriptor(arousal: float) -> str:
    if arousal >= 0.7:
        return "energetic, vibrant, intense"
    if arousal >= 0.4:
        return "dynamic, flowing, engaged"
    return "calm, serene, ambient"


#: Negative prompt common across all generations.
_NEGATIVE_PROMPT = (
    "text, watermark, logo, signature, blurry, distorted, oversaturated, "
    "human faces, violence, explicit content, low quality, artifacts"
)


# ---------------------------------------------------------------------------
# Exceptions / result
# ---------------------------------------------------------------------------


class FireflySpecError(RuntimeError):
    """Raised when a Firefly job spec cannot be built from the given RenderSpec.

    Never raised silently; callers must handle or propagate.
    """


class FireflyJobResult:
    """Outcome of a successful :meth:`FireflyAdapter.render` call.

    Attributes:
        job_specs: List of Firefly REST job specs (one per segment).
        job_specs_path: Path where the specs bundle was written (None if no output_path).
        used_video_export_fallback: True if the VideoExport fallback ran instead.
        fallback_video_path: Path to the fallback export when used.
    """

    def __init__(
        self,
        job_specs: list[dict[str, Any]],
        job_specs_path: Any = None,
        used_video_export_fallback: bool = False,
        fallback_video_path: Any = None,
    ) -> None:
        self.job_specs = job_specs
        self.job_specs_path = job_specs_path
        self.used_video_export_fallback = used_video_export_fallback
        self.fallback_video_path = fallback_video_path


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def derive_firefly_prompt(
    segment: dict[str, Any],
    palette: list[str],
    mir: dict[str, Any],
) -> str:
    """Derive a Firefly text-to-image prompt from segment metadata.

    The prompt incorporates:
    - Segment label (structural section name).
    - Dominant stem (drums/bass/vocals/other) → visual texture hint.
    - Valence/arousal → mood and energy descriptors.
    - Palette → colour instructions.
    - MIR key/mode → harmonic feel.

    Args:
        segment: Scene-segment dict from RenderSpec v2.
        palette: Hex colour list from RenderSpec.
        mir: MIR summary dict from RenderSpec v2.

    Returns:
        A descriptive prompt string for the Firefly image-generation API.
    """
    label = str(segment.get("label", "unknown"))
    dominant_stem = str(segment.get("dominant_stem", "other"))
    mood = segment.get("mood", {})
    if isinstance(mood, dict):
        valence = float(mood.get("valence", 0.5))
        arousal = float(mood.get("arousal", 0.5))
    else:
        valence = 0.5
        arousal = 0.5

    energy_mean = float(segment.get("energy_mean", 0.3))

    # Colour instruction from palette (take up to 3 colours)
    colour_words = ", ".join(palette[:3]) if palette else "#00f5ff, #ff2fd5, #8a75ff"

    # MIR harmonic context
    key = str(mir.get("key") or "C")
    mode = str(mir.get("mode") or "major")
    harmonic = f"{key} {mode}"

    texture = _STEM_TEXTURE_HINT.get(dominant_stem, "abstract textures, layered light")
    mood_desc = _valence_descriptor(valence)
    energy_desc = _arousal_descriptor(arousal)

    prompt = (
        f"Music visualization background for a {label} section. "
        f"Style: {mood_desc}, {energy_desc}. "
        f"Visual elements: {texture}. "
        f"Colour palette: {colour_words}. "
        f"Harmonic key: {harmonic}. "
        f"Energy level: {energy_mean:.2f}/1.0. "
        "Cinematic, high resolution, suitable for music video background layer, "
        "no text or human faces, abstract visual art."
    )
    return prompt


# ---------------------------------------------------------------------------
# Core job-spec builder
# ---------------------------------------------------------------------------


def build_firefly_job_specs(
    spec: RenderSpec,
    *,
    width: int | None = None,
    height: int | None = None,
) -> list[dict[str, Any]]:
    """Generate one Firefly REST job spec per scene segment.

    Args:
        spec: RenderSpec v2 instance (or dict-shaped equivalent).
        width: Output image width in pixels.  Defaults to ``spec.metadata.width``
            or 1920.
        height: Output image height in pixels.  Defaults to ``spec.metadata.height``
            or 1080.

    Returns:
        List of JSON-serialisable Firefly job spec dicts, one per segment.
        Empty list when ``scene_segments`` is absent.

    Raises:
        FireflySpecError: When the RenderSpec is structurally invalid (e.g.
            ``duration`` missing or ``fps`` invalid).
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
    scene_segments: list[dict[str, Any]] = spec_dict.get("scene_segments") or []
    mir: dict[str, Any] = spec_dict.get("mir") or {}

    duration = float(metadata.get("duration", 0.0))
    if duration <= 0.0:
        raise FireflySpecError(
            "build_firefly_job_specs: RenderSpec metadata.duration is missing or zero. "
            "Cannot derive per-segment image specs without track duration."
        )

    _width = width if width is not None else int(metadata.get("width", 1920))
    _height = height if height is not None else int(metadata.get("height", 1080))

    if not scene_segments:
        logger.info(
            "build_firefly_job_specs: no scene_segments in spec — returning empty list."
        )
        return []

    job_specs: list[dict[str, Any]] = []
    for seg in scene_segments:
        idx = int(seg.get("index", len(job_specs)))
        label = str(seg.get("label", "unknown"))
        dominant_stem = str(seg.get("dominant_stem", "other"))
        mood = seg.get("mood", {})
        if isinstance(mood, dict):
            valence = float(mood.get("valence", 0.5))
            arousal = float(mood.get("arousal", 0.5))
        else:
            valence = 0.5
            arousal = 0.5

        prompt = derive_firefly_prompt(seg, palette, mir)
        style_preset = _LABEL_STYLE_MAP.get(label, "digital_art")

        # Deterministic seed per segment (stable across re-runs)
        seed = (idx * 7919) % 65536

        job_spec: dict[str, Any] = {
            "firefly_schema": _FIREFLY_SCHEMA,
            "prompt": prompt,
            "negative_prompt": _NEGATIVE_PROMPT,
            "n": 1,
            "size": {"width": _width, "height": _height},
            "styles": [style_preset],
            "seed": seed,
            "content_class": "photo",
            "melosviz_meta": {
                "segment_index": idx,
                "segment_label": label,
                "dominant_stem": dominant_stem,
                "valence": round(valence, 4),
                "arousal": round(arousal, 4),
                "palette": palette[:3],
                "output_key": f"{label}_{idx}.png",
                "style_preset": style_preset,
            },
        }
        job_specs.append(job_spec)

    logger.info(
        "build_firefly_job_specs: generated %d job specs from %d segments",
        len(job_specs),
        len(scene_segments),
    )
    return job_specs


# ---------------------------------------------------------------------------
# Conductor adapter
# ---------------------------------------------------------------------------


class FireflyAdapter:
    """Photoshop Firefly generative-asset conductor adapter.

    Handles the ``generative_asset`` scene type.  Generates Firefly REST job
    specs from a RenderSpec v2.  When ``force_video_export=True`` is passed
    (or when called via the legacy VideoExport pathway), falls back to the
    video_exporter with an explicit warning.

    Args:
        width: Output image width override (pixels).
        height: Output image height override (pixels).
    """

    #: Key used in the conductor adapter registry.
    scene_type: str = SCENE_TYPE

    def __init__(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self._width = width
        self._height = height

    def render(
        self,
        render_spec: RenderSpec,
        *,
        output_path: Any = None,
        force_video_export: bool = False,
        **_kwargs: Any,
    ) -> FireflyJobResult:
        """Generate Firefly job specs from a RenderSpec v2.

        Args:
            render_spec: RenderSpec v2 instance.
            output_path: Directory where ``firefly_jobs.json`` is written.
                When None, no files are written.
            force_video_export: When True, skip Firefly spec generation and
                run the VideoExport fallback instead (explicit, logged at WARNING).
            **_kwargs: Extra kwargs ignored (conductor forward compat).

        Returns:
            :class:`FireflyJobResult` containing the job specs.

        Raises:
            FireflySpecError: On spec validation failure.
        """
        import json as _json
        import pathlib

        if force_video_export:
            logger.warning(
                "FireflyAdapter.render: force_video_export=True — "
                "falling back to VideoExport pipeline (Firefly spec skipped). "
                "This produces a colour-cycle video, not Firefly-generated images."
            )
            from melosviz.render.video_exporter import export_video

            vp: pathlib.Path | None = None
            if output_path is not None:
                vp = export_video(render_spec, output_dir=pathlib.Path(str(output_path)))
            else:
                vp = export_video(render_spec)
            return FireflyJobResult(
                job_specs=[],
                used_video_export_fallback=True,
                fallback_video_path=vp,
            )

        job_specs = build_firefly_job_specs(
            render_spec,
            width=self._width,
            height=self._height,
        )

        job_specs_path: Any = None
        if output_path is not None:
            out_dir = pathlib.Path(str(output_path))
            out_dir.mkdir(parents=True, exist_ok=True)
            job_specs_path = out_dir / "firefly_jobs.json"
            job_specs_path.write_text(
                _json.dumps(job_specs, indent=2), encoding="utf-8"
            )
            logger.info(
                "FireflyAdapter.render: wrote %d Firefly job specs → %s",
                len(job_specs),
                job_specs_path,
            )

        return FireflyJobResult(
            job_specs=job_specs,
            job_specs_path=job_specs_path,
        )
