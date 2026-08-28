"""Headless ComfyUI adapter — RenderSpec v2 → generative images / clips → MP4/MOV.

ComfyUI is the **primary generative renderer** of the MelosViz pipeline.
It replaces the Firefly stub as the GOLD-tier image / video source and is the
first stage of every multi-scene music video we ship.

Why ComfyUI (not Firefly, not Stable Diffusion web, not a custom diff. stack)
---------------------------------------------------------------------------
* **Local, OSS, free**: ComfyUI runs locally with the user's own GPUs;
  no per-image API costs, no vendor lock-in, no rate limits, no egress fees.
* **Workflow-as-JSON**: every ComfyUI pipeline is a deterministic JSON graph.
  We serialize our :class:`~melosviz.analysis.models.RenderSpec` into that
  graph, ship it to ComfyUI over its HTTP API, and replay — making renders
  reproducible, diff-able, and reviewable in PRs.
* **Model-agnostic**: SDXL, Flux.1, Wan 2.1, Hunyuan Video, LTX-Video,
  AnimateDiff, SVD, IP-Adapter, ControlNet, LoRAs, IP-Adapter-FaceID —
  everything the modern music-video artist stack uses is one node away.
* **Scene-per-clip model fits the beat-synced music-video brief perfectly**:
  one prompt + one negative + one sampler + one refiner per scene, with the
  scene's seed derived from the segment's beat index for deterministic
  re-runs.
* **Same engine for images and short video clips**: the `video` scene_type
  uses Wan 2.1 / Hunyuan / LTX-Video via ComfyUI-VideoHelperSuite, so
  image-generation and motion-generation share one transport, one queue,
  one error model.

What this adapter does
----------------------
1. Builds a **workflow JSON** (image OR video) by interpolating a Jinja2
   template (`workflows/sdxl_image.json`, `workflows/wan_video.json`,
   …) with the scene's prompt, seed, sampler, and beat-conditioned params.
2. POSTs it to ``POST {comfyui_base}/prompt`` with a ``client_id``.
3. Polls ``GET {comfyui_base}/history/{prompt_id}`` until the workflow
   finishes (or times out).
4. Downloads outputs via ``GET {comfyui_base}/view?filename=…&type=output``
   to ``output_path`` (per scene).
5. Returns the list of file paths to the orchestrator for downstream
   assembly (DaVinci / AE / ffmpeg).

Configuration (env vars)
------------------------
``MELOSVIZ_COMFYUI_URL``   Base URL (default ``http://127.0.0.1:8188``).
``MELOSVIZ_COMFYUI_TIMEOUT`` Wall-clock timeout per workflow, seconds
                            (default ``900`` = 15 min — covers 5 s video clips
                            on slow GPUs).
``MELOSVIZ_COMFYUI_WORKFLOWS_DIR``  Directory holding the ``workflows/*.json``
                            Jinja2 templates shipped with this repo
                            (default ``backend/workflows``).
``MELOSVIZ_COMFYUI_MODEL`` Override the checkpoint node id wired into the
                            template (default ``""`` = use whatever the
                            template already has).

Failure modes
-------------
* ComfyUI HTTP error / timeout → :class:`ComfyUIError`.
* Missing workflow template → :class:`ComfyUIWorkflowMissingError`.
* Connection refused (no ComfyUI running) → :class:`ComfyUIUnavailableError`
  (distinct so callers can degrade to the Blender / FFmpeg fallback path).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from melosviz.analysis.models import RenderSpec

logger = logging.getLogger(__name__)

__all__ = [
    "ComfyUIAdapter",
    "ComfyUIError",
    "ComfyUIUnavailableError",
    "ComfyUIWorkflowMissingError",
    "render_image",
    "render_video",
    "is_comfyui_available",
]

# ---------------------------------------------------------------------------
# Constants / env-var knobs
# ---------------------------------------------------------------------------

_COMFYUI_ENV_URL = "MELOSVIZ_COMFYUI_URL"
_COMFYUI_ENV_TIMEOUT = "MELOSVIZ_COMFYUI_TIMEOUT"
_COMFYUI_ENV_WORKFLOWS = "MELOSVIZ_COMFYUI_WORKFLOWS_DIR"
_COMFYUI_ENV_MODEL = "MELOSVIZ_COMFYUI_MODEL"

DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
DEFAULT_COMFYUI_TIMEOUT_S = 900
DEFAULT_WORKFLOWS_DIRNAME = "workflows"

#: Scene-type strings the conductor routes to this adapter.
SCENE_TYPES: tuple[str, ...] = (
    "comfyui_image",       # single-frame stills (album-art, intro cards)
    "comfyui_video",       # short clips (Wan 2.1 / LTX / Hunyuan / AnimateDiff)
    "generative_asset",    # legacy alias for Firefly → ComfyUI rewire
    # WBS-107, WBS-108: native-audio video workflows. Director routes
    # drop → comfyui_audio_video_wan, chorus (with character) →
    # comfyui_audio_video_seedance; scenes carry audio_path + motion
    # strength + audio influence to drive the audio-conditioned sampler.
    "comfyui_audio_video_wan",
    "comfyui_audio_video_seedance",
)

#: Scene-type strings that route to a character-consistent workflow.
#: These scenes reference a named character via ``scene["character"]`` (or
#: via ``scene["characters"] = [name1, ...]``) and the orchestrator stamps
#: the resolved ``character_*`` template fields (face/identity references,
#: weight knobs, engine selector) onto the scene before dispatch so the
#: ``ipadapter_character.json`` / ``pulid_character.json`` templates can
#: ``{character_front}`` etc. without the adapter knowing about ID details.
CHARACTER_SCENE_TYPES: tuple[str, ...] = (
    "comfyui_image",
    "comfyui_video",
    "ipadapter_character",
    "pulid_character",
)

#: Jinja2-like (we use stdlib ``str.format``-safe) templates shipped with repo.
DEFAULT_WORKFLOWS = {
    "comfyui_image": "sdxl_image.json",
    "comfyui_video": "wan_video.json",
    "generative_asset": "sdxl_image.json",
    # WBS-107, WBS-108: native-audio video workflows.
    "comfyui_audio_video_wan": "wan_s2v_audio.json",
    "comfyui_audio_video_seedance": "seedance_a2v.json",
    "ipadapter_character": "ipadapter_character.json",
    "pulid_character": "pulid_character.json",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ComfyUIError(RuntimeError):
    """Base class for any ComfyUI adapter failure."""


class ComfyUIUnavailableError(ComfyUIError):
    """ComfyUI server is unreachable — caller should fall back."""


class ComfyUIWorkflowMissingError(ComfyUIError):
    """Workflow template file is missing from the workflows dir."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comfyui_url() -> str:
    return os.environ.get(_COMFYUI_ENV_URL, DEFAULT_COMFYUI_URL).rstrip("/")


def _comfyui_offline() -> bool:
    """When ``MELOSVIZ_COMFYUI_OFFLINE=1`` the adapter never touches the
    network and instead emits a job-spec JSON per scene. Useful in CI and
    when the operator wants to review prompts before spending GPU time."""
    return os.environ.get("MELOSVIZ_COMFYUI_OFFLINE", "").strip().lower() in (
        "1", "true", "yes", "on"
    )


def _comfyui_timeout_s() -> int:
    raw = os.environ.get(_COMFYUI_ENV_TIMEOUT, str(DEFAULT_COMFYUI_TIMEOUT_S))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_COMFYUI_TIMEOUT_S


def _workflows_dir() -> Path:
    override = os.environ.get(_COMFYUI_ENV_WORKFLOWS)
    if override:
        return Path(override).expanduser().resolve()
    # backend/src/melosviz/render/comfyui_adapter.py → ../../../../workflows
    here = Path(__file__).resolve()
    return (here.parent.parent.parent.parent / DEFAULT_WORKFLOWS_DIRNAME).resolve()


def _http_json(method: str, url: str, *, body: dict | None = None,
               timeout_s: int = 30) -> dict:
    """Tiny stdlib HTTP client — keeps the adapter dep-free."""
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
        raw = resp.read()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))


def _http_download(url: str, dest: Path, *, timeout_s: int = 120) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp, open(dest, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)
    return dest


def is_comfyui_available(base_url: str | None = None) -> bool:
    """True iff ComfyUI ``/system_stats`` responds within 2 s."""
    url = (base_url or _comfyui_url()) + "/system_stats"
    try:
        _http_json("GET", url, timeout_s=2)
        return True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _build_workflow(scene_type: str, scene: dict[str, Any],
                    *, model_override: str | None = None) -> dict:
    """Render the workflow JSON for one scene from its on-disk template."""
    templates = _workflows_dir()
    tpl_name = DEFAULT_WORKFLOWS.get(scene_type)
    if tpl_name is None:
        raise ComfyUIWorkflowMissingError(f"Unknown scene_type={scene_type!r}")
    tpl_path = templates / tpl_name
    if not tpl_path.is_file():
        raise ComfyUIWorkflowMissingError(
            f"Workflow template not found: {tpl_path}. "
            f"Set ${_COMFYUI_ENV_WORKFLOWS} or ship the file."
        )
    raw = tpl_path.read_text(encoding="utf-8")
    # The templates use ``"text": "{prompt}"`` where {prompt} is already
    # wrapped in JSON quotes. We need to JSON-escape the value (so an
    # internal quote like ``depicts: "City lights"`` becomes
    # ``depicts: \"City lights\"``) but NOT add surrounding quotes — that
    # would double-wrap and break the JSON. We achieve that with
    # ``json.dumps(s)[1:-1]``.
    def _esc(s: object) -> str:
        return json.dumps(s, ensure_ascii=False)[1:-1]
    safe = _SafeDict({
        "prompt": _esc(scene.get("prompt", "")),
        "negative": _esc(scene.get("negative", "lowres, blurry, watermark")),
        "seed": int(scene.get("seed", 0)),
        "steps": int(scene.get("steps", 28)),
        "cfg": float(scene.get("cfg", 5.5)),
        "sampler": _esc(scene.get("sampler", "euler_ancestral")),
        "scheduler": _esc(scene.get("scheduler", "normal")),
        "width": int(scene.get("width", 1280)),
        "height": int(scene.get("height", 720)),
        "frames": int(scene.get("frames", 48)),
        "fps": int(scene.get("fps", 24)),
        "model": _esc(model_override or os.environ.get(_COMFYUI_ENV_MODEL, "")),
        "lora": _esc(scene.get("lora", "")),
        # v2 (WBS-2): ``ip_adapter_image`` is the on-wire name for the
        # ``ContinuityAnchor.reference_image`` path on most ComfyUI
        # IP-Adapter / Wan / ControlNet templates. The orchestrator
        # stamps the validated path from
        # ``spec_dict["continuity"]["reference_image"]`` onto every scene
        # before dispatch (see ``orchestrator.py``), so templates that
        # declare ``{ip_adapter_image}`` get it, and templates that
        # don't are left untouched — the placeholder is safe in either
        # case (it falls back to ``""`` when the scene has no IP-Adapter).
        "ip_adapter_image": _esc(scene.get("ip_adapter_image", "")),
        # v2 (WBS-2): ``reference_image`` + ``reference_image_strength``
        # are the explicit ContinuityAnchor v2 field names — workflow
        # templates that prefer the canonical schema name can use these
        # placeholders directly. ``reference_image_strength`` defaults to
        # ``0.65`` (a sensible "style leans reference" value for
        # IP-Adapter) and is overridable per scene via
        # ``scene["reference_image_strength"]`` or globally via the
        # orchestrator's ``reference_image_strength`` kwarg.
        "reference_image": _esc(scene.get("reference_image", "")),
        "reference_image_strength": _esc(
            scene.get("reference_image_strength", 0.65)
        ),
        "controlnet_image": _esc(scene.get("controlnet_image", "")),
        # WBS-101..106 character-consistency reference slots. Templates that
        # don't reference these are left untouched (the SafeDict swallows
        # them). Defaults are empty strings so legacy templates still
        # substitute safely without our character scene-stamping.
        "character_front": _esc(scene.get("character_front", "")),
        "character_three_quarter": _esc(scene.get("character_three_quarter", "")),
        "character_profile": _esc(scene.get("character_profile", "")),
        "character_full_body": _esc(scene.get("character_full_body", "")),
        "character_style_ref": _esc(scene.get("character_style_ref", "")),
        "character_face_weight": _esc(scene.get("character_face_weight", "")),
        "character_style_weight": _esc(scene.get("character_style_weight", "")),
        "character_engine": _esc(scene.get("character_engine", "")),
        # WBS-107..109 (2026-08): Native-audio video workflows. The
        # orchestrator stamps audio_path / motion_strength / audio_influence
        # from the SceneSegment onto every audio-conditioned scene. Defaults
        # keep non-audio templates untouched — _SafeDict leaves unknown keys
        # literal, so these placeholders land on the audio-conditioned
        # templates only (``wan_s2v_audio.json`` / ``seedance_a2v.json``).
        "audio_path": _esc(scene.get("audio_path", "")),
        "motion_strength": _esc(scene.get("motion_strength", 1.0)),
        "audio_influence": _esc(scene.get("audio_influence", 0.8)),
    })
    return json.loads(_safe_format(raw, safe))


def _safe_format(template: str, mapping: dict[str, Any]) -> str:
    """Replace ``{key}`` occurrences with ``mapping[key]`` (str() coerced)
    without recursing into the substituted value (unlike ``str.format_map``).
    Missing keys are left as the literal ``"{key}"`` token."""
    import re as _re
    pattern = _re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    def _sub(match: "_re.Match[str]") -> str:
        key = match.group(1)
        if key in mapping:
            return str(mapping[key])
        return match.group(0)

    return pattern.sub(_sub, template)


class _SafeDict(dict):
    """dict that returns ``"{key}"`` for missing keys instead of raising."""
    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return "{" + key + "}"


def _submit_workflow(workflow: dict, *, base_url: str,
                     client_id: str) -> str:
    body = {"prompt": workflow, "client_id": client_id}
    resp = _http_json("POST", base_url + "/prompt", body=body, timeout_s=30)
    pid = resp.get("prompt_id")
    if not pid:
        raise ComfyUIError(f"ComfyUI /prompt returned no prompt_id: {resp!r}")
    return pid


def _await_workflow(prompt_id: str, *, base_url: str,
                    timeout_s: int, poll_s: float = 1.5) -> dict:
    """Block until the prompt finishes, returns the history entry."""
    deadline = time.monotonic() + timeout_s
    last_status: dict | None = None
    while time.monotonic() < deadline:
        try:
            hist = _http_json(
                "GET", f"{base_url}/history/{prompt_id}", timeout_s=10
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ComfyUIUnavailableError(
                f"ComfyUI history poll failed: {exc}"
            ) from exc
        entry = hist.get(prompt_id) if isinstance(hist, dict) else None
        if entry:
            status = entry.get("status") or {}
            completed = bool(status.get("completed"))
            if completed:
                return entry
            last_status = status
        time.sleep(poll_s)
    raise ComfyUIError(
        f"ComfyUI workflow {prompt_id!r} did not finish within "
        f"{timeout_s}s (last status: {last_status!r})"
    )


def _collect_outputs(history_entry: dict, *, base_url: str,
                     output_dir: Path) -> list[Path]:
    """Download every image/video the workflow produced to ``output_dir``."""
    outputs_section = history_entry.get("outputs") or {}
    files: list[Path] = []
    for node_id, node_out in outputs_section.items():
        for kind in ("images", "gifs", "videos"):
            for item in node_out.get(kind, []) or []:
                filename = item.get("filename")
                if not filename:
                    continue
                subfolder = item.get("subfolder", "")
                q = urllib.parse.urlencode(
                    {"filename": filename, "subfolder": subfolder, "type": "output"}
                )
                url = f"{base_url}/view?{q}"
                dest = output_dir / f"{node_id}_{filename}"
                _http_download(url, dest)
                files.append(dest)
    if not files:
        raise ComfyUIError(
            "ComfyUI workflow completed but produced no images/videos."
        )
    return files


# ---------------------------------------------------------------------------
# Public render entry-points
# ---------------------------------------------------------------------------


def render_image(scene: dict[str, Any], *, output_dir: Path | str,
                 base_url: str | None = None,
                 timeout_s: int | None = None) -> list[Path]:
    """Render one image-scene via ComfyUI; returns list of output file paths."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    return _dispatch_scene("comfyui_image", scene, output_dir=out,
                           base_url=base_url, timeout_s=timeout_s)


def render_video(scene: dict[str, Any], *, output_dir: Path | str,
                 base_url: str | None = None,
                 timeout_s: int | None = None) -> list[Path]:
    """Render one short video clip via ComfyUI (Wan 2.1 / LTX / Hunyuan)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    return _dispatch_scene("comfyui_video", scene, output_dir=out,
                           base_url=base_url, timeout_s=timeout_s)


def _dispatch_scene(scene_type: str, scene: dict[str, Any], *,
                    output_dir: Path, base_url: str | None,
                    timeout_s: int | None) -> list[Path]:
    base = (base_url or _comfyui_url()).rstrip("/")
    if not is_comfyui_available(base):
        raise ComfyUIUnavailableError(
            f"ComfyUI not reachable at {base}. "
            "Start ComfyUI (`python main.py` in ComfyUI repo) and retry."
        )
    workflow = _build_workflow(scene_type, scene)
    client_id = f"melosviz-{os.getpid()}-{int(time.time())}"
    prompt_id = _submit_workflow(workflow, base_url=base, client_id=client_id)
    logger.info("ComfyUI: submitted %s for scene_type=%s", prompt_id, scene_type)
    history = _await_workflow(
        prompt_id,
        base_url=base,
        timeout_s=timeout_s if timeout_s is not None else _comfyui_timeout_s(),
    )
    return _collect_outputs(history, base_url=base, output_dir=output_dir)


# ---------------------------------------------------------------------------
# Adapter (conductor integration)
# ---------------------------------------------------------------------------


class ComfyUIAdapter:
    """Conductor-compatible adapter.

    Exposes ``scene_type = "comfyui_image"`` (the default) but also accepts
    ``comfyui_video`` and ``generative_asset`` via the conductor registry.
    """

    scene_type: str = "comfyui_image"

    def __init__(self, scene_type: str = "comfyui_image") -> None:
        if scene_type not in SCENE_TYPES:
            raise ValueError(
                f"ComfyUIAdapter: unsupported scene_type={scene_type!r}; "
                f"choose one of {SCENE_TYPES}"
            )
        self.scene_type = scene_type

    # ------------------------------------------------------------------
    # AdapterProtocol.render
    # ------------------------------------------------------------------
    def render(self, render_spec: Any, *, output_path: Any = None,
               **kwargs: Any) -> list[Path]:
        """Render every scene of ``render_spec`` through ComfyUI.

        ComfyUI is the **primary generative renderer** of the pipeline, so
        when the orchestrator invokes it we render ALL scenes — picking the
        correct workflow (``comfyui_image`` vs ``comfyui_video``) per scene
        based on each scene's ``scene_type``. Other adapters (C4D, UE, …)
        may re-route individual scenes later for specific finishing work.
        """
        out_dir = Path(str(output_path)) if output_path is not None else Path(
            "/tmp/melosviz-comfyui"
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        scenes = _extract_scenes(render_spec)
        if not scenes:
            logger.warning(
                "ComfyUIAdapter: spec contains no scenes; nothing to render",
            )
            return []

        results: list[Path] = []
        # Offline mode → write a per-scene job spec and skip the network.
        if _comfyui_offline():
            job_spec = {
                "mode": "offline-job-spec",
                "server": _comfyui_url(),
                "scene_type": self.scene_type,
                "scenes": [],
            }
            for i, scene in enumerate(scenes):
                wf_type = _resolve_workflow_for_scene(scene)
                scene = _ensure_default_prompt(scene, index=i)
                workflow = _build_workflow(wf_type, scene)
                scene_out = out_dir / f"scene_{i:03d}"
                scene_out.mkdir(parents=True, exist_ok=True)
                spec_path = scene_out / "workflow.json"
                spec_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
                job_spec["scenes"].append({
                    "index": i,
                    "scene_type": wf_type,
                    "label": scene.get("label", f"scene_{i}"),
                    "prompt": scene.get("prompt", ""),
                    "negative": scene.get("negative", ""),
                    "seed": scene.get("seed", 0),
                    "workflow_json": str(spec_path),
                })
                results.append(spec_path)
            manifest = out_dir / "job_spec.json"
            manifest.write_text(json.dumps(job_spec, indent=2), encoding="utf-8")
            return results

        for i, scene in enumerate(scenes):
            scene_out = out_dir / f"scene_{i:03d}"
            scene_out.mkdir(parents=True, exist_ok=True)
            wf_type = _resolve_workflow_for_scene(scene)
            try:
                files = _dispatch_scene(
                    wf_type, scene, output_dir=scene_out,
                    base_url=kwargs.get("base_url"),
                    timeout_s=kwargs.get("timeout_s"),
                )
            except ComfyUIError:
                raise
            results.extend(files)
        return results


def _extract_scenes(render_spec: Any, *, scene_type: str | None = None) -> list[dict]:
    """Pull scenes out of either a Pydantic spec or a dict.

    If ``scene_type`` is provided, only scenes matching it are returned
    (the legacy one-adapter-per-scene-type path). If ``scene_type`` is
    ``None``, all scenes are returned in source order (the umbrella
    ComfyUI renderer path).
    """
    if hasattr(render_spec, "model_dump"):
        data = render_spec.model_dump()
    elif isinstance(render_spec, dict):
        data = render_spec
    else:
        return []
    scenes = data.get("scenes") or data.get("scene_segments") or []
    if scene_type is None:
        return [s for s in scenes if isinstance(s, dict)]
    out: list[dict] = []
    for s in scenes:
        if isinstance(s, dict) and s.get("scene_type", "comfyui_image") == scene_type:
            out.append(s)
    return out


def _resolve_character_sheet(scene: dict[str, Any],
                            registry: Any | None) -> dict[str, Any] | None:
    """Return the first character sheet referenced by ``scene``.

    Accepts either ``scene["character"]`` (str) or ``scene["characters"]``
    (list[str]). The ``registry`` may be a dict-like ``{name: sheet}`` or
    an object with a ``.require(name)`` / ``.get(name)`` method (the
    conductor's ``CharacterRegistry``). Returns ``None`` if the scene
    names no character or the registry doesn't carry that name.
    """
    if registry is None:
        return None
    names: list[str] = []
    primary = scene.get("character")
    if isinstance(primary, str) and primary.strip():
        names.append(primary.strip())
    secondary = scene.get("characters")
    if isinstance(secondary, (list, tuple)):
        for n in secondary:
            if isinstance(n, str) and n.strip():
                names.append(n.strip())
    if not names:
        return None
    for name in names:
        try:
            if hasattr(registry, "require"):
                sheet = registry.require(name)
            elif hasattr(registry, "get"):
                sheet = registry.get(name)
            else:
                sheet = registry[name] if isinstance(registry, dict) else None
        except (KeyError, AttributeError, IndexError):
            sheet = None
        if sheet is not None:
            return sheet
    return None


def _resolve_workflow_for_scene(scene: dict[str, Any],
                                *, registry: Any | None = None) -> str:
    """Pick the ComfyUI workflow type for ``scene``.

    Explicit ``ipadapter_character`` / ``pulid_character`` scene_types
    pass through. If a scene names a character via ``scene["character"]``
    and a ``registry`` is supplied, the engine recorded on the character
    sheet decides between ``ipadapter_character`` and ``pulid_character``
    (WBS-101..106). Otherwise the legacy heuristic applies:
    ``generative_asset`` -> ``comfyui_image``; motion / duration > 4 s
    (with unknown scene_type) -> ``comfyui_video``.
    """
    raw = (scene.get("scene_type") or "comfyui_image").strip()
    if raw in {"ipadapter_character", "pulid_character"}:
        return raw
    sheet = _resolve_character_sheet(scene, registry)
    if sheet is not None:
        engine = (sheet.get("engine") or "ipadapter").strip().lower()
        if engine == "pulid":
            return "pulid_character"
        return "ipadapter_character"
    if raw in SCENE_TYPES:
        return raw
    if raw == "generative_asset":
        return "comfyui_image"
    motion = bool(scene.get("motion") or scene.get("video"))
    duration = float(scene.get("duration_s") or 0.0)
    if motion or duration > 4.0:
        return "comfyui_video"
    return "comfyui_image"


def _stamp_character_fields(scene: dict[str, Any],
                            *, registry: Any | None) -> dict[str, Any]:
    """Return a copy of ``scene`` populated with ``character_*`` fields.

    Looks up the named character in ``registry`` (dict or registry
    object), copies the resolved reference paths into the scene under
    ``character_front`` / ``character_three_quarter`` / ``character_profile``
    / ``character_full_body`` / ``character_style_ref``, copies the
    ``face_weight`` / ``style_weight`` / ``engine`` metadata into the
    corresponding ``character_*_weight`` / ``character_engine`` keys, and
    returns the merged scene. Returns the scene untouched (as a new dict)
    if no character resolves.

    Scene authors can override individual fields by setting
    ``scene["character_face_weight"]`` (etc.) before stamping - the
    existing keys take precedence.
    """
    sheet = _resolve_character_sheet(scene, registry)
    if sheet is None:
        return dict(scene)
    refs = sheet.get("references") or {}
    metadata = sheet.get("metadata") or {}
    out = dict(scene)
    slot_map = {
        "front": "character_front",
        "three_quarter": "character_three_quarter",
        "profile": "character_profile",
        "full_body": "character_full_body",
        "style": "character_style_ref",
    }
    for slot, target in slot_map.items():
        if target not in out and isinstance(refs.get(slot), str) and refs[slot]:
            out[target] = refs[slot]
    if "character_face_weight" not in out:
        fw = metadata.get("face_weight")
        if fw is not None:
            out["character_face_weight"] = str(fw)
    if "character_style_weight" not in out:
        sw = metadata.get("style_weight")
        if sw is not None:
            out["character_style_weight"] = str(sw)
    if "character_engine" not in out:
        eng = sheet.get("engine")
        if isinstance(eng, str) and eng:
            out["character_engine"] = eng
    return out


def _ensure_default_prompt(scene: dict[str, Any], *, index: int) -> dict[str, Any]:
    """Fill in a sensible ComfyUI prompt if the scene didn't ship one.

    Without this, scenes with no explicit ``prompt`` field would land on
    ComfyUI with an empty string and silently produce garbage.  We compose
    a deterministic, comma-separated prompt from the scene's metadata
    (label, energy, palette hint, beat index) so offline reviews get a
    realistic-looking workflow graph.
    """
    if scene.get("prompt"):
        return scene
    label = scene.get("label") or f"scene_{index}"
    energy = float(scene.get("energy_mean") or scene.get("energy") or 0.5)
    seed = int(scene.get("seed") or index)
    palette_hint = scene.get("palette_hint") or "neon"
    descriptor = {
        "intro": "establishing shot, cinematic, slow dolly-in",
        "verse": "medium shot, ambient particles, soft motion",
        "chorus": "dynamic camera, dramatic lighting, hard cuts on beat",
        "bridge": "wide shot, low key, fog, restraint",
        "outro": "pull-back, slow zoom, dreamy haze",
    }.get(label, "music video composition, 35mm film look")
    palette = {
        "neon": "magenta + cyan + electric purple",
        "warm": "amber + rose + deep crimson",
        "cool": "teal + indigo + slate",
        "monochrome": "high-contrast black + white with rim light",
    }.get(palette_hint, "cinematic color grade")
    prompt = (
        f"music video scene {label!r}, {descriptor}, "
        f"palette: {palette}, energy {energy:.2f}, "
        "anamorphic lens, 24fps, "
        "subject sharply lit against depth-blurred background, "
        "no text, no watermark"
    )
    return {**scene, "prompt": prompt, "seed": seed}


# ---------------------------------------------------------------------------
# Optional CLI: scaffold a default workflow set for new users
# ---------------------------------------------------------------------------


def scaffold_workflows(target_dir: Path | str) -> list[Path]:
    """Write minimal-but-real ComfyUI workflow templates to ``target_dir``.

    Two templates: ``sdxl_image.json`` (txt2img) and ``wan_video.json``
    (Wan 2.1 5B text-to-video). The templates are valid ComfyUI prompt
    graphs (every node has the required ``class_type`` + ``inputs``).

    Callers normally don't need this; it's here so a fresh clone with no
    ComfyUI experience can `viz comfyui init` and get started.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for name, body in _WORKFLOW_TEMPLATES.items():
        path = target / name
        path.write_text(json.dumps(body, indent=2), encoding="utf-8")
        out.append(path)
    return out


_SDXL_IMAGE_WORKFLOW: dict[str, Any] = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 28,
            "cfg": 5.5,
            "sampler_name": "euler_ancestral",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1280, "height": 720, "batch_size": 1},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "{prompt}", "clip": ["4", 1]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "{negative}", "clip": ["4", 1]},
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "melosviz", "images": ["8", 0]},
    },
}

_WAN_VIDEO_WORKFLOW: dict[str, Any] = {
    "10": {
        "class_type": "WanVideoSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 6.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "width": 1280,
            "height": 720,
            "num_frames": 48,
            "model": ["11", 0],
            "positive": ["12", 0],
            "negative": ["13", 0],
            "latent_image": ["14", 0],
        },
    },
    "11": {
        "class_type": "WanVideoModelLoader",
        "inputs": {"model_name": "wan2.1_t2v_5B_bf16.safetensors"},
    },
    "12": {
        "class_type": "WanVideoTextEncode",
        "inputs": {"text": "{prompt}", "model": ["11", 0]},
    },
    "13": {
        "class_type": "WanVideoTextEncode",
        "inputs": {"text": "{negative}", "model": ["11", 0]},
    },
    "14": {
        "class_type": "WanVideoEmptyLatent",
        "inputs": {"width": 1280, "height": 720, "num_frames": 48},
    },
    "15": {
        "class_type": "WanVideoDecode",
        "inputs": {"samples": ["10", 0], "model": ["11", 0]},
    },
    "16": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": "melosviz_clip",
            "format": "video/h264-mp4",
            "save_output": True,
            "pingpong": False,
            "images": ["15", 0],
        },
    },
}

_WORKFLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "sdxl_image.json": _SDXL_IMAGE_WORKFLOW,
    "wan_video.json": _WAN_VIDEO_WORKFLOW,
}
