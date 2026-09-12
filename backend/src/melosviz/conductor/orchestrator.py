"""Conductor orchestrator — routes a RenderSpec to pro-tool adapters.

The orchestrator:
1. Identifies which scene types appear in ``spec.scene_segments``.
2. Dispatches each scene type to the corresponding adapter from
   :data:`~melosviz.conductor.registry.ADAPTER_REGISTRY`.
3. Collects per-adapter render results.
4. Triggers the final ``assembly_encode`` step (MediaEncoder or ffmpeg
   fallback) with the collected per-segment output paths.
5. Emits per-scene :class:`~melosviz.conductor.events.RenderEvent`
   records through the in-process event bus so the web + desktop
   Director's Console render queue can live-update via SSE.

Failure policy
--------------
* Missing adapter for a scene type raises :class:`ConductorError` (loud, not silent).
* Adapter render failures propagate their own exceptions; the orchestrator
  wraps them with scene-type context.
* The final assembly step is always attempted last; failure is also loud.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

from melosviz.conductor.provenance import ClipProvenance, write_provenance
from melosviz.conductor.render_cache import (
    RenderCache,
    scene_cache_key,
    scene_render_cached,
)
from melosviz.conductor.visual_diff import compute_visual_diff

logger = logging.getLogger(__name__)

__all__ = ["Orchestrator", "ConductorError", "OrchestratorResult"]


class ConductorError(RuntimeError):
    """Raised when the conductor cannot route or dispatch a render."""


def _scene_label(seg: dict[str, Any], scene_index: int) -> str:
    name = str(seg.get("name") or seg.get("label") or f"scene_{scene_index:03d}")
    return name[:80]


class OrchestratorResult:
    """Aggregated result from a full :meth:`Orchestrator.render` run.

    Attributes:
        per_scene_results: ``{scene_type: adapter_result}`` for each dispatched type.
        assembly_result: Result from the final ``assembly_encode`` step.
        output_dir: Base directory used for all outputs.
        job_id: Unique identifier for this run (used to key SSE event streams).
        events: All :class:`RenderEvent` records emitted during the run.
    """

    def __init__(
        self,
        per_scene_results: dict[str, Any],
        assembly_result: Any | None,
        output_dir: Path | None,
        job_id: str = "",
        events: list[Any] | None = None,
    ) -> None:
        self.per_scene_results = per_scene_results
        self.assembly_result = assembly_result
        self.output_dir = output_dir
        self.job_id = job_id
        self.events = events or []


class Orchestrator:
    """Multi-tool render orchestrator.

    Dispatches a :class:`~melosviz.analysis.models.RenderSpec` to all
    registered adapters, then runs the final assembly step.

    Args:
        output_dir: Base directory for all adapter outputs.
            Defaults to ``/tmp/melosviz-conductor``.
        skip_assembly: When True, skip the final ``assembly_encode`` step
            (useful for per-adapter unit tests).
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        skip_assembly: bool = False,
        *,
        auto_offline: bool = True,
        job_id: str | None = None,
        only_scenes: Sequence[int] | None = None,
        character_root: Path | str | None = None,
    ) -> None:
        """Orchestrator.

        Args:
            output_dir: Base directory for all adapter outputs.
                Defaults to ``/tmp/melosviz-conductor``.
            skip_assembly: When True, skip the final ``assembly_encode`` step
                (useful for per-adapter unit tests).
            auto_offline: When True (default) and the orchestrator cannot
                reach any external service (ComfyUI / Cinema 4D / Unreal /
                DaVinci) it auto-enables ``MELOSVIZ_COMFYUI_OFFLINE=1`` so
                adapters fall back to writing JSON job-specs instead of
                raising.  Set False to require live services (production).
            job_id: Optional caller-supplied render-job id used to tag every
                :class:`RenderEvent` emitted on the SSE bus. When None the
                orchestrator generates a 12-char hex id per :meth:`render`
                call (which means subscribers would not see a stable id
                across multiple processes — pass ``job_id`` explicitly when
                bridging CLI <-> web bridge <-> SSE listener).
            only_scenes: When set, only dispatch scenes whose
                ``scene_index`` is in this iterable.
            character_root: Optional path to a directory of character
                reference sheets (YAML/JSON files or per-character
                sub-dirs; see :mod:`melosviz.character`). When set, the
                orchestrator eagerly loads every sheet via
                :func:`melosviz.character.load_registry` and threads the
                resulting :class:`~melosviz.character.CharacterRegistry`
                into every adapter call as ``registry=...`` so scenes
                that reference a character get the correct
                ``ipadapter_character`` / ``pulid_character`` workflow
                and the appropriate ``character_*`` template fields
                stamped onto them.
        """
        self._output_dir = (
            Path(output_dir)
            if output_dir is not None
            else Path("/tmp/melosviz-conductor")
        )
        self._skip_assembly = skip_assembly
        self._auto_offline = auto_offline
        self._job_id = job_id
        self._only_scenes: tuple[int, ...] | None = (
            tuple(only_scenes) if only_scenes else None
        )
        # WBS-101..106 — character consistency wiring. Lazy-import the
        # character module so the conductor's import graph stays light for
        # callers that don't use characters. ``character_root`` may be a
        # path that doesn't yet exist on disk; we record it but only
        # attempt to load it if a scene actually references a character.
        self._character_root: Path | None = (
            Path(character_root).expanduser().resolve()
            if character_root is not None
            else None
        )
        self._character_registry: Any = None  # CharacterRegistry instance
        self._active_characters: tuple[str, ...] = ()  # names opted in via CLI
        if self._character_root is not None:
            self._load_character_registry()
        # Depth layer (render-cache + provenance): always construct
        # the per-instance attributes so the per-scene dispatch loop
        # can call them even when no scene actually triggers the cache
        # fast-path or the sidecar write. Both objects are best-effort:
        # if the underlying modules are missing or the disk is full,
        # the orchestrator logs at debug and continues. The attribute
        # NAMES matter — render() reads self._render_cache.cache_dir and
        # self._provenance_records, so renaming either would silently
        # break the cache fast-path at runtime.
        self._render_cache: RenderCache = RenderCache(
            self._output_dir / "_render_cache"
        )
        self._provenance_records: list[ClipProvenance] = []
        # Offline detection: if the operator hasn't explicitly set
        # ``MELOSVIZ_COMFYUI_OFFLINE`` and ComfyUI is unreachable, surface a
        # warning so the operator knows the pipeline will fall back to
        # stub-mode adapters. We deliberately do NOT mutate ``os.environ``
        # here — global env mutation pollutes the parent process and breaks
        # test isolation (subsequent test functions inherit the offline
        # flag). Operators running the pipeline interactively should set
        # ``MELOSVIZ_COMFYUI_OFFLINE=1`` themselves.
        if auto_offline and not os.environ.get("MELOSVIZ_COMFYUI_OFFLINE"):
            try:
                from melosviz.render.comfyui_adapter import is_comfyui_available

                if not is_comfyui_available():
                    logger.warning(
                        "Orchestrator: ComfyUI not reachable; adapters will "
                        "fall back to stub mode. Set "
                        "MELOSVIZ_COMFYUI_OFFLINE=1 to suppress this warning "
                        "and emit job-spec JSON instead."
                    )
            except Exception:  # pragma: no cover — defensive
                pass

    # ------------------------------------------------------------------
    # Character registry management (WBS-101..106)
    # ------------------------------------------------------------------
    def _load_character_registry(self) -> None:
        """Load character sheets from ``self._character_root``.

        Missing directories are tolerated — we record an empty registry
        but log a warning so the operator knows character resolution
        will silently no-op. Other I/O errors (permissions, malformed
        YAML) propagate.
        """
        from melosviz.character import CharacterRegistry, load_registry

        root = self._character_root
        if root is None:
            return
        if not root.is_dir():
            logger.warning(
                "Orchestrator: character_root=%s does not exist or is "
                "not a directory; character scenes will render without "
                "identity references.", root,
            )
            self._character_registry = CharacterRegistry()
            return
        try:
            self._character_registry = load_registry(root)
            logger.info(
                "Orchestrator: loaded %d character sheet(s) from %s",
                len(self._character_registry.names()), root,
            )
        except Exception as exc:
            logger.warning(
                "Orchestrator: failed to load character_root=%s (%s); "
                "character scenes will render without identity references.",
                root, exc,
            )
            self._character_registry = CharacterRegistry()

    @property
    def character_root(self) -> Path | None:
        """The configured character root, if any."""
        return self._character_root

    @property
    def character_registry(self) -> Any:
        """The currently loaded :class:`CharacterRegistry`.

        Returns an empty registry when no ``character_root`` is set so
        callers can always pass ``orchestrator.character_registry``
        directly into adapter kwargs without a None-guard.
        """
        if self._character_registry is None:
            from melosviz.character import CharacterRegistry

            return CharacterRegistry()
        return self._character_registry

    def set_active_characters(self, names: Sequence[str] | None) -> None:
        """Opt a subset of loaded character sheets into the next render.

        Useful for the CLI's ``--character name1 --character name2``
        flags: it limits the registry exposed to adapters to only those
        characters named on the command line. Pass ``None`` to clear.
        """
        if not names:
            self._active_characters = ()
            return
        seen: set[str] = set()
        out: list[str] = []
        for raw in names:
            n = str(raw).strip()
            if not n or n in seen:
                continue
            seen.add(n)
            out.append(n)
        self._active_characters = tuple(out)

    def _effective_registry(self) -> Any:
        """Return the (possibly subset) registry to pass into adapters.

        When the CLI opted specific characters in via
        :meth:`set_active_characters`, build a temporary registry
        containing only those sheets. Otherwise return the full
        registry.
        """
        reg = self.character_registry
        if not self._active_characters:
            return reg
        try:
            from melosviz.character import CharacterRegistry

            subset = CharacterRegistry()
            for name in self._active_characters:
                sheet = reg.get(name)
                if sheet is not None:
                    subset.add(sheet)
            return subset
        except Exception:
            return reg

    def render(
        self,
        render_spec: RenderSpec,
        *,
        scene_types: list[str] | None = None,
        segment_paths: list[str | Path] | None = None,
        only_scenes: list[int] | None = None,
        audio_path: Path | None = None,
    ) -> OrchestratorResult:
        """Dispatch the render spec to all relevant adapters.

        Args:
            render_spec: RenderSpec v2 instance.
            scene_types: Override the list of scene types to dispatch.
                When None, derives them from ``spec.scene_segments``.
            segment_paths: Pre-existing per-segment clip paths to pass to
                the assembly step.  When None, collected from per-adapter results.
            only_scenes: When set, only dispatch scenes whose ``scene_index``
                matches one of these integers (the art-director feedback
                loop calls ``viz direct --scene-index N --re-render`` to
                re-render just one scene + its immediate neighbors, so a
                1-scene tweak doesn't force a full 3-minute re-render).
                Indices outside the spec's range raise :class:`ConductorError`.

        Returns:
            :class:`OrchestratorResult` with all adapter results.

        Raises:
            ConductorError: When a required adapter is missing, or when
                ``only_scenes`` references an out-of-range index.
        """
        from melosviz.conductor.registry import ADAPTER_REGISTRY

        self._output_dir.mkdir(parents=True, exist_ok=True)

        # ---- Resolve scene types from spec ---------------------------------
        spec_dict = (
            render_spec.model_dump()
            if hasattr(render_spec, "model_dump")
            else render_spec
        )
        segs = spec_dict.get("scene_segments") or []

        # audio_path resolution: prefer explicit kwarg, fall back to the
        # spec's metadata.audio_path or the spec's top-level audio_path.
        # The WBS-107..109 stamp below needs a path-shaped string for
        # audio_video scene types — it can be None for purely visual jobs.
        wav_path: Path | None = audio_path
        if wav_path is None and isinstance(spec_dict, dict):
            meta = spec_dict.get("metadata") or {}
            if isinstance(meta, dict):
                _raw = meta.get("audio_path")
                if _raw:
                    wav_path = Path(str(_raw))
            if wav_path is None:
                _raw = spec_dict.get("audio_path")
                if _raw:
                    wav_path = Path(str(_raw))

        # ---- v2 ContinuityAnchor plumbing (WBS-2, 2026-08) -----------------
        # Pull ``continuity.reference_image`` off the spec and stamp it onto
        # every scene as ``scene["ip_adapter_image"]`` (ComfyUI IP-Adapter
        # / Wan / ControlNet on-wire name) AND ``scene["reference_image"]``
        # (canonical v2 ContinuityAnchor field name) *before* dispatching
        # to render adapters. The adapter reads these fields via
        # :func:`comfyui_adapter._build_workflow` and feeds them to the
        # ``{ip_adapter_image}`` / ``{reference_image}`` template
        # placeholders. ``reference_image_strength`` defaults to ``0.65``
        # (sensible IP-Adapter default) and is overridable per-scene or
        # via the orchestrator's ``reference_image_strength`` kwarg.
        # Missing files are dropped to ``None`` with a warning so the
        # render can still proceed (IP-Adapter is an enhancement, not a
        # hard requirement).
        _continuity_ref: str | None = None
        _continuity_strength: float = 0.65
        _continuity = (
            spec_dict.get("continuity")
            if isinstance(spec_dict, dict)
            else None
        )
        if isinstance(_continuity, dict):
            ref = _continuity.get("reference_image")
            if ref:
                ref_str = str(ref)
                if Path(ref_str).is_file():
                    _continuity_ref = ref_str
                else:
                    logger.warning(
                        "Orchestrator: continuity.reference_image %s missing "
                        "on disk; scenes will render without IP-Adapter "
                        "reference.",
                        ref_str,
                    )
            strength_raw = _continuity.get("reference_image_strength")
            if strength_raw is not None:
                try:
                    _continuity_strength = float(strength_raw)
                except (TypeError, ValueError):
                    logger.warning(
                        "Orchestrator: continuity.reference_image_strength "
                        "%r is not a float; using default 0.65.",
                        strength_raw,
                    )
        if _continuity_ref and segs:
            for _seg in segs:
                if isinstance(_seg, dict):
                    _seg["ip_adapter_image"] = _continuity_ref
                    _seg["reference_image"] = _continuity_ref
                    _seg.setdefault(
                        "reference_image_strength", _continuity_strength
                    )

        # ---- Character-consistency plumbing (WBS-101..106, 2026-08) --------
        # For each scene that names a character (via ``scene["character"]``
        # or ``scene["characters"]``) and refers to a named character in
        # the registry, merge the resolved reference paths into the scene
        # under ``character_front`` / ``character_three_quarter`` /
        # ``character_profile`` / ``character_full_body`` /
        # ``character_style_ref`` and copy ``face_weight`` /
        # ``style_weight`` / ``engine`` metadata. This is the stamp-side
        # counterpart of :func:`comfyui_adapter._stamp_character_fields`;
        # we pre-stamp here so renderers that don't run through the
        # ComfyUI adapter still see the resolved paths (e.g. any future
        # adapter that wants to consume ``character_front`` directly).
        char_root = self._character_root
        char_reg = self._character_registry
        if (char_root is not None or char_reg is not None) and segs:
            for _seg in segs:
                if not isinstance(_seg, dict):
                    continue
                _names = []
                _primary = _seg.get("character")
                if isinstance(_primary, str) and _primary.strip():
                    _names.append(_primary.strip())
                _secondary = _seg.get("characters")
                if isinstance(_secondary, (list, tuple)):
                    for _n in _secondary:
                        if isinstance(_n, str) and _n.strip():
                            _names.append(_n.strip())
                if not _names:
                    continue
                _sheet = None
                if char_reg is not None:
                    for _n in _names:
                        try:
                            _sheet = char_reg.get(_n) if hasattr(char_reg, "get") else None
                            if _sheet is None and hasattr(char_reg, "require"):
                                _sheet = char_reg.require(_n)
                        except KeyError:
                            _sheet = None
                        if _sheet is not None:
                            break
                if _sheet is None:
                    continue
                _refs = _sheet.get("references") or {}
                _meta = _sheet.get("metadata") or {}
                _slot_map = {
                    "front": "character_front",
                    "three_quarter": "character_three_quarter",
                    "profile": "character_profile",
                    "full_body": "character_full_body",
                    "style": "character_style_ref",
                }
                for _slot, _target in _slot_map.items():
                    if _target in _seg:
                        continue
                    _val = _refs.get(_slot) if isinstance(_refs, dict) else None
                    if isinstance(_val, str) and _val:
                        _seg[_target] = _val
                if "character_face_weight" not in _seg:
                    _fw = _meta.get("face_weight") if isinstance(_meta, dict) else None
                    if _fw is not None:
                        _seg["character_face_weight"] = str(_fw)
                if "character_style_weight" not in _seg:
                    _sw = _meta.get("style_weight") if isinstance(_meta, dict) else None
                    if _sw is not None:
                        _seg["character_style_weight"] = str(_sw)
                if "character_engine" not in _seg:
                    _eng = _sheet.get("engine") if isinstance(_sheet, dict) else None
                    if isinstance(_eng, str) and _eng:
                        _seg["character_engine"] = _eng

        # WBS-107..109: stamp audio-conditioned scene fields onto every
        # audio-video scene so the adapter's _SafeDict can substitute them
        # without knowing about the calling pipeline. The orchestrator is
        # the single source of truth for "what audio drives this scene" —
        # the Director emits scene_type, but the runtime audio file path +
        # knobs come from the conductor / storyboard.
        _audio_scene_types = {
            "comfyui_audio_video_wan",
            "comfyui_audio_video_seedance",
        }
        for _seg in segs:
            if str(_seg.get("scene_type", "")) not in _audio_scene_types:
                continue
            if "audio_path" not in _seg and wav_path is not None:
                _seg["audio_path"] = str(wav_path)
            if "motion_strength" not in _seg:
                # Defaults: drop/chorus → strong motion (0.85), else moderate (0.6).
                _label = str(_seg.get("label", _seg.get("archetype", ""))).lower()
                _default_motion = 0.85 if _label in {"drop", "chorus"} else 0.6
                _seg["motion_strength"] = _default_motion
            if "audio_influence" not in _seg:
                _seg["audio_influence"] = 0.75

        if scene_types is None:
            # Deduplicate while preserving order
            seen: set[str] = set()
            _types: list[str] = []
            for seg in segs:
                st = str(seg.get("scene_type", "video_export"))
                if st not in seen:
                    seen.add(st)
                    _types.append(st)
            # If no scene_segments, fall back to video_export
            if not _types:
                _types = ["video_export"]
        else:
            _types = list(scene_types)

        # ---- Setup render-event bus ----------------------------------------
        from melosviz.conductor.events import (
            RenderEvent,
            get_bus,
        )

        job_id = self._job_id or uuid.uuid4().hex[:12]
        bus = get_bus()
        emitted: list[RenderEvent] = []

        # ---- Dispatch per scene type ----------------------------------------
        per_scene_results: dict[str, Any] = {}
        collected_paths: list[str | Path] = list(segment_paths or [])

        # Build the list of (scene_index, scene_name, scene_type) for event
        # emission. One entry per individual scene so every render gets its
        # own queued -> rendering -> done triad in the SSE stream, even when
        # multiple scenes share a scene_type (the common case for a 27-scene
        # music video where many scenes dispatch to comfyui_image).
        per_scene_dispatch: list[tuple[int, str, str, dict]] = []
        if scene_types is not None and segs:
            # The caller asked for an explicit set of scene_types. Honour
            # the intersection with the segs so each matching scene_segment
            # generates its own queued -> rendering -> done event triad.
            # Fall back to a synthetic per-type dispatch only when no seg
            # matches (so the adapter registry is exercised even when
            # scene_segments lack matching scene_type metadata — this lets
            # ConductorError surface for unknown types).
            per_scene_dispatch = []
            for i, seg in enumerate(segs):
                st = str(seg.get("scene_type", "video_export"))
                if st == "assembly_encode":
                    continue
                if st in scene_types:
                    per_scene_dispatch.append(
                        (i, _scene_label(seg, i), st, seg)
                    )
            if not per_scene_dispatch:
                per_scene_dispatch = [
                    (i, f"scene_{i:03d}", st, {})
                    for i, st in enumerate(_types)
                    if st != "assembly_encode"
                ]
        elif segs:
            for i, seg in enumerate(segs):
                st = str(seg.get("scene_type", "video_export"))
                if st == "assembly_encode":
                    continue
                per_scene_dispatch.append((i, _scene_label(seg, i), st, seg))
        elif _types:
            # No scene_segments: dispatch once per requested type with a
            # synthetic scene name.
            per_scene_dispatch = [
                (i, f"scene_{i:03d}", st, {})
                for i, st in enumerate(_types)
                if st != "assembly_encode"
            ]

        for scene_idx, scene_name, scene_type, _seg_for_render in per_scene_dispatch:
            scene_out_dir = self._output_dir / scene_type
            scene_out_dir.mkdir(parents=True, exist_ok=True)

            adapter_cls = ADAPTER_REGISTRY.get(scene_type)
            if adapter_cls is None:
                # Emit error event then raise so the SSE stream gets the
                # failure before the orchestrator aborts.
                err_evt = bus.emit_error(
                    job_id=job_id,
                    scene_index=scene_idx,
                    scene_name=scene_name,
                    scene_type=scene_type,
                    backend="(no adapter)",
                    error=f"no adapter registered for scene_type={scene_type!r}",
                )
                emitted.append(err_evt)
                raise ConductorError(
                    f"Orchestrator: no adapter registered for scene_type={scene_type!r}. "
                    f"Registered types: {list(ADAPTER_REGISTRY.keys())}. "
                    "Register an adapter in melosviz.conductor.registry.ADAPTER_REGISTRY."
                )

            # Synthetic dispatch (no matching scene_segment in the spec)
            # is a directory-only op: the caller asked the orchestrator to
            # materialise output dirs for ``scene_types`` they listed, but
            # there is no real scene work to render. Stub the per-scene
            # result and continue without invoking the adapter.
            if not _seg_for_render:
                per_scene_results.setdefault(scene_type, {
                    "artifact_path": None,
                    "cache_key": "",
                })
                continue

            backend_key = f"{adapter_cls.__module__}.{adapter_cls.__name__}"

            queued_evt = bus.emit_queued(
                job_id=job_id,
                scene_index=scene_idx,
                scene_name=scene_name,
                scene_type=scene_type,
                backend=backend_key,
            )
            emitted.append(queued_evt)

            logger.info(
                "Orchestrator: dispatching scene[%d] type=%r → %s",
                scene_idx,
                scene_type,
                adapter_cls,
            )

            # Render cache fast-path: if the same prompt/seed/size/model was
            # already rendered into scene_out_dir, skip the adapter call
            # entirely and emit a done event with from_cache=True.
            cache_root: Path | None = self._render_cache.cache_dir if self._render_cache is not None else None
            cached_artifact: Path | None = None
            if cache_root is not None:
                cached_artifact = scene_render_cached(_seg_for_render, cache_root)
            if cached_artifact is not None and cached_artifact.exists():
                logger.info(
                    "Orchestrator: scene[%d] cache HIT → %s",
                    scene_idx,
                    cached_artifact,
                )
                elapsed_ms = 0.0
                done_evt = RenderEvent(
                    job_id=job_id,
                    scene_index=scene_idx,
                    scene_name=scene_name,
                    scene_type=scene_type,
                    state="done",
                    backend=backend_key,
                    started_at=_now_ms(),
                    finished_at=_now_ms(),
                    duration_ms=0.0,
                    artifact_path=str(cached_artifact),
                    extras={"from_cache": True, "cache_key": scene_cache_key(_seg_for_render, cache_root).fingerprint()},
                )
                bus._events.append(done_evt)
                emitted.append(done_evt)
                per_scene_results.setdefault(scene_type, {
                    "artifact_path": cached_artifact,
                    "cache_key": scene_cache_key(_seg_for_render, cache_root).fingerprint(),
                })
                continue

            t0 = time.monotonic()
            try:
                rendering_evt = bus.emit_rendering(
                    job_id=job_id,
                    scene_index=scene_idx,
                    scene_name=scene_name,
                    scene_type=scene_type,
                    backend=backend_key,
                    progress=0.05,
                )
                emitted.append(rendering_evt)

                adapter = adapter_cls()
                # ---- v2 ContinuityAnchor kwargs (WBS-2, 2026-08) ------------
                # The per-scene stamp loop above writes
                # ``reference_image`` and ``reference_image_strength``
                # onto every scene segment. We pull them off the live
                # seg dict here and forward as kwargs so adapters that
                # accept them directly (ComfyUI image/video/audio
                # adapters) can wire them into workflow nodes without
                # re-reading the spec. ``scene_ip_adapter_image`` is
                # kept as an alias for backwards compatibility with
                # adapters that already keyed off the pre-WBS-2 name.
                _render_kwargs: dict[str, Any] = {
                    "output_path": scene_out_dir,
                    "registry": self._effective_registry(),
                }
                _ref_img = _seg_for_render.get("reference_image") or _seg_for_render.get(
                    "ip_adapter_image"
                )
                if _ref_img:
                    _render_kwargs["reference_image"] = str(_ref_img)
                    _ref_str = _seg_for_render.get("reference_image_strength")
                    if _ref_str is not None:
                        try:
                            _render_kwargs["reference_image_strength"] = float(
                                _ref_str
                            )
                        except (TypeError, ValueError):
                            _render_kwargs["reference_image_strength"] = 0.65
                    # Backwards-compat alias for older adapters that
                    # still key off the pre-v2 on-wire name.
                    _render_kwargs.setdefault(
                        "scene_ip_adapter_image", str(_ref_img)
                    )
                result = adapter.render(render_spec, **_render_kwargs)
            except Exception as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                err_evt = bus.emit_error(
                    job_id=job_id,
                    scene_index=scene_idx,
                    scene_name=scene_name,
                    scene_type=scene_type,
                    backend=backend_key,
                    error=str(exc),
                    duration_ms=elapsed_ms,
                )
                emitted.append(err_evt)
                raise ConductorError(
                    f"Orchestrator: adapter for scene_type={scene_type!r} failed: {exc}"
                ) from exc

            elapsed_ms = (time.monotonic() - t0) * 1000.0
            artifact = ""
            if hasattr(result, "files") and result.files:
                artifact = str(result.files[0])
            elif hasattr(result, "output_paths") and result.output_paths:
                artifact = str(result.output_paths[0])

            done_evt = bus.emit_done(
                job_id=job_id,
                scene_index=scene_idx,
                scene_name=scene_name,
                scene_type=scene_type,
                backend=backend_key,
                duration_ms=elapsed_ms,
                artifact_path=artifact,
            )
            emitted.append(done_evt)

            per_scene_results.setdefault(scene_type, result)

            # ---- Provenance sidecar + render cache store ----
            # Track wall-clock timestamps for duration_seconds in provenance.
            _render_started_at = t0
            _render_finished_at = _render_started_at + elapsed_ms / 1000.0
            # Compute visual diff if artifact exists on disk.
            _visual_diff: dict | None = None
            if artifact and Path(artifact).is_file():
                try:
                    _visual_diff = compute_visual_diff(
                        artifact_path=artifact,
                        prompt=getattr(render_spec, "prompt", None) or scene_name,
                    )
                except Exception:  # best-effort
                    _visual_diff = None
            try:
                clip_prov = ClipProvenance(
                    scene_index=scene_idx,
                    scene_name=scene_name,
                    scene_type=scene_type,
                    backend=backend_key,
                    render_started_at=_render_started_at,
                    render_finished_at=_render_finished_at,
                    seed=getattr(render_spec, "seed", None) or scene_idx,
                    artifact_path=artifact,
                    prompt=getattr(render_spec, "prompt", None) or scene_name,
                    width=int(getattr(render_spec, "width", 1920) or 1920),
                    height=int(getattr(render_spec, "height", 1080) or 1080),
                    fps=int(getattr(render_spec, "fps", 24) or 24),
                    visual_diff=_visual_diff,
                )
                write_provenance(clip_prov)
            except Exception as exc:  # provenance is best-effort
                logger.debug("provenance write skipped: %s", exc)

            try:
                cache_key = scene_cache_key(_seg_for_render, cache_root) if cache_root else scene_cache_key(_seg_for_render, self._output_dir)
                if self._render_cache is not None and artifact:
                    self._render_cache.store(
                        cache_key,
                        src_artifact_path=Path(artifact),
                        meta={"scene_index": scene_idx, "scene_name": scene_name},
                    )
            except Exception as exc:  # cache store is best-effort
                logger.debug("render cache store skipped: %s", exc)

        # ---- Final assembly step -------------------------------------------
        assembly_result: Any = None
        if not self._skip_assembly:
            me_cls = ADAPTER_REGISTRY.get("assembly_encode")
            if me_cls is None:
                raise ConductorError(
                    "Orchestrator: 'assembly_encode' adapter missing from registry. "
                    "Wiring error — MEAdapter must be registered."
                )
            assembly_out = self._output_dir / "assembly"
            assembly_out.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Orchestrator: running final assembly_encode step → %s "
                "(segment_paths=%d, ffmpeg fallback if AME absent)",
                assembly_out,
                len(collected_paths),
            )
            try:
                me_adapter = me_cls()
                assembly_result = me_adapter.render(
                    render_spec,
                    output_path=assembly_out,
                    segment_paths=collected_paths,
                )
            except Exception as exc:
                raise ConductorError(
                    f"Orchestrator: final assembly_encode step failed: {exc}"
                ) from exc

        return OrchestratorResult(
            per_scene_results=per_scene_results,
            assembly_result=assembly_result,
            output_dir=self._output_dir,
            job_id=job_id,
            events=emitted,
        )
