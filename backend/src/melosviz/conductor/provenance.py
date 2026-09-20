"""
melosviz.conductor.provenance — per-clip render provenance / lineage metadata.

Writes a sidecar `<artifact>.provenance.json` next to every rendered clip
so a downstream consumer (DaVinci import, festival VJ system, archival
ingest) can replay the exact workflow + inputs + backend + timestamps
that produced the artifact.

Schema (v1):
    {
      "schema_version": "1.0",
      "artifact_path": str,
      "storyboard_id": str | None,
      "scene_index": int,
      "scene_name": str,
      "scene_type": str,
      "backend": str,
      "seed": int | None,
      "render_started_at": float,
      "render_finished_at": float,
      "duration_seconds": float,
      "input_hash": str,         # SceneCacheKey fingerprint
      "prompt": str,
      "width": int,
      "height": int,
      "fps": int,
      "palette": list[str],
      "continuity": {subject_token, env_token},
      "lyric": {phrase_id, text, mood_label} | None,
      "workflow_json_path": str | None,
      "comfyui_prompt_id": str | None,
      "comfyui_job_id": str | None,
      "extra": dict
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROVENANCE_SCHEMA_VERSION = "1.0"

# Characters Windows forbids anywhere in a path component. A sidecar is written
# next to its artifact, so an artifact name that only some platforms can
# represent produces a file that cannot be checked out on the others.
_NON_PORTABLE_CHARS = '<>:"|?*'

# Device names Windows reserves regardless of extension.
_RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _assert_portable_component(name: str) -> None:
    """Reject a file name that cannot exist on every supported platform.

    Raises:
        ValueError: if `name` is empty, holds a Windows-illegal character, holds
            a control character, ends in a dot or space, or is a reserved
            Windows device name.

    Guarding here matters because the failure is not local: a sidecar named
    after a Mock repr (``<MagicMock ...>.provenance.json``) was committed at
    ``6539d2b`` and made ``git clone`` abort with ``fatal: unable to checkout
    working tree`` on Windows, leaving the whole worktree short of files.
    """
    if not name:
        raise ValueError("artifact path has no file name")
    illegal = sorted({ch for ch in name if ch in _NON_PORTABLE_CHARS})
    if illegal:
        raise ValueError(
            f"artifact name {name!r} contains characters that are not portable "
            f"to Windows: {''.join(illegal)!r}"
        )
    if any(ord(ch) < 0x20 for ch in name):
        raise ValueError(f"artifact name {name!r} contains control characters")
    if name != name.rstrip(". "):
        raise ValueError(f"artifact name {name!r} ends with a dot or a space")
    if name.split(".")[0].strip().upper() in _RESERVED_NAMES:
        raise ValueError(f"artifact name {name!r} is a reserved Windows device name")


@dataclass
class ClipProvenance:
    artifact_path: str
    scene_index: int
    scene_name: str
    scene_type: str
    backend: str
    render_started_at: float
    render_finished_at: float | None = None
    storyboard_id: str | None = None
    seed: int | None = None
    input_hash: str | None = None
    prompt: str = ""
    width: int = 0
    height: int = 0
    fps: int = 0
    palette: list[str] = field(default_factory=list)
    continuity: dict = field(default_factory=dict)
    lyric: dict | None = None
    workflow_json_path: str | None = None
    comfyui_prompt_id: str | None = None
    comfyui_job_id: str | None = None
    visual_diff: dict | None = None  # visual_diff.compute_visual_diff() payload
    extra: dict = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        if self.render_finished_at is None:
            return 0.0
        return max(0.0, self.render_finished_at - self.render_started_at)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "artifact_path": self.artifact_path,
            "storyboard_id": self.storyboard_id,
            "scene_index": self.scene_index,
            "scene_name": self.scene_name,
            "scene_type": self.scene_type,
            "backend": self.backend,
            "seed": self.seed,
            "render_started_at": self.render_started_at,
            "render_finished_at": self.render_finished_at,
            "duration_seconds": self.duration_seconds,
            "input_hash": self.input_hash,
            "prompt": self.prompt,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "palette": self.palette,
            "continuity": self.continuity,
            "lyric": self.lyric,
            "workflow_json_path": self.workflow_json_path,
            "comfyui_prompt_id": self.comfyui_prompt_id,
            "comfyui_job_id": self.comfyui_job_id,
            "visual_diff": self.visual_diff,
            "extra": self.extra,
        }
        return d


def _assert_portable_path(path: Path) -> None:
    """Validate the file name `path` would create on disk.

    Combines :func:`_assert_portable_component` with a drive-relative check:
    Windows reads ``"c:clip.mp4"`` as a drive-qualified relative path, so the
    colon never reaches ``.name`` and a sidecar would be written somewhere other
    than the directory the caller asked for.
    """
    _assert_portable_component(path.name)
    if not path.is_absolute() and ":" in str(path):
        raise ValueError(f"path {str(path)!r} is drive-relative; its colon is not portable")


def provenance_path_for(artifact: Path | str) -> Path:
    """Return the sidecar `.provenance.json` path for `artifact`.

    The derived name is validated for cross-platform portability; see
    :func:`_assert_portable_path`.
    """
    p = Path(artifact)
    _assert_portable_path(p)
    return p.with_name(p.name + ".provenance.json")


def write_provenance(
    prov: ClipProvenance, *, indent: int = 2, target: Path | str | None = None
) -> Path:
    """Write the sidecar for `prov`; return the path written.

    By default the sidecar sits next to ``prov.artifact_path``. Pass `target`
    when a render produced no artifact path but its outcome still has to stay
    traceable; the caller then owns keeping that path inside the render output
    directory.
    """
    dest = Path(target) if target is not None else provenance_path_for(prov.artifact_path)
    _assert_portable_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(prov.to_dict(), ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )
    return dest


def collect_manifest_from_dir(out_dir: Path | str) -> list[dict]:
    """Return all provenance dicts in `out_dir`, sorted by scene_index."""
    root = Path(out_dir)
    out: list[dict] = []
    for sidecar in sorted(root.rglob("*.provenance.json")):
        try:
            d = json.loads(sidecar.read_text(encoding="utf-8"))
            out.append(d)
        except (OSError, json.JSONDecodeError):
            continue
    out.sort(key=lambda d: (d.get("scene_index", 0), d.get("artifact_path", "")))
    return out


__all__ = [
    "ClipProvenance",
    "PROVENANCE_SCHEMA_VERSION",
    "collect_manifest_from_dir",
    "provenance_path_for",
    "write_provenance",
]
