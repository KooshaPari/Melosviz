"""Source extraction: KooshaPari/Melosviz at 1aec20a2ba41a01ed557d1c7f63f9a0089f842cf.
Original: backend/src/melosviz/conductor/orchestrator.py
Git blob: 549e70a5741f43546af3d068b5444d54d47affc2.
Three function bodies copied for isolated execution; docstrings/comments omitted.
Not a complete module/checkout. Replay verifies executable AST against the full source.
"""
from __future__ import annotations
import json
import logging
import shutil
from pathlib import Path
logger = logging.getLogger(__name__)


def _is_zero_duration(artifact: str) -> bool | None:
    if not artifact:
        return None
    suffix = Path(artifact).suffix.lower()
    if suffix == ".wav":
        try:
            import wave
            with wave.open(artifact, "rb") as _w:
                nframes = _w.getnframes()
                framerate = _w.getframerate() or 1
            return (nframes == 0) or ((nframes / framerate) <= 0.0)
        except (wave.Error, EOFError, OSError, ValueError):
            return None
    return None


def _artifact_rejection(artifact: str) -> str | None:
    if not artifact:
        return None
    path = Path(artifact)
    try:
        if not path.exists():
            return "artifact missing (the adapter reported a path that does not exist)"
        if not path.is_file():
            return "artifact is not a file"
        if path.stat().st_size == 0:
            return "artifact is empty (0 bytes)"
    except OSError as exc:
        return f"artifact could not be inspected: {exc}"
    if _is_zero_duration(artifact) is True:
        return "artifact is zero-duration media (no playable frames)"
    return None


def _materialise_cached_artifact(blob: Path, output_dir: Path, scene_out_dir: Path) -> Path | None:
    blob_name = blob.name
    relpath: str | None = None
    try:
        stored = json.loads(blob.with_suffix(".json").read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            if stored.get("artifact_relpath"):
                relpath = str(stored["artifact_relpath"])
            if stored.get("artifact_name"):
                blob_name = str(stored["artifact_name"])
    except (OSError, json.JSONDecodeError):
        pass
    target: Path | None = None
    if relpath:
        candidate = (output_dir / relpath).resolve()
        if candidate.is_relative_to(output_dir.resolve()):
            target = candidate
        else:
            logger.warning(
                "cached artifact path %r escapes the output dir; using the plain name",
                relpath,
            )
    if target is None:
        target = scene_out_dir / (Path(blob_name).name or blob.name)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not (target.exists() and target.stat().st_size == blob.stat().st_size):
            shutil.copy2(blob, target)
    except OSError as exc:
        logger.debug("cache materialise failed for %s: %s", blob, exc)
        return None
    return target
