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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


PROVENANCE_SCHEMA_VERSION = "1.0"


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


def provenance_path_for(artifact: Path | str) -> Path:
    """Return the sidecar `.provenance.json` path for `artifact`."""
    p = Path(artifact)
    return p.with_name(p.name + ".provenance.json")


def write_provenance(prov: ClipProvenance, *, indent: int = 2) -> Path:
    target = provenance_path_for(prov.artifact_path)
    target.write_text(
        json.dumps(prov.to_dict(), ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )
    return target


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
