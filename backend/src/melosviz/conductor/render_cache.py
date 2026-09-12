"""
melosviz.conductor.render_cache — content-hash scene render cache.

Lets the orchestrator skip scenes whose render inputs (prompt + seed +
scene_type + backend + width + height + fps + continuity tokens) didn't
change since the last successful render. The cache key is SHA-256 of the
JSON-serialized inputs; the artifact path mirrors the canonical per-scene
output layout so a hit is a path copy, not a re-render.

Public surface:
    SceneCacheKey.from_scene(scene, backend_key, render_spec) -> SceneCacheKey
    SceneCacheKey.fingerprint() -> str   (SHA-256 hex)

    RenderCache.for_storyboard(cache_dir, storyboard_id) -> RenderCache
        .lookup(scene_cache_key) -> Path | None
        .store(scene_cache_key, src_artifact_path, meta=None) -> Path
        .stats() -> dict   (hits, misses, total_bytes)

Cache directory layout (under .melosviz/render_cache/<storyboard_id>/):
    <fingerprint>.json   # metadata: ts, scene_index, backend, prompt_hash
    <fingerprint>.bin    # symlink or copy of the rendered artifact
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


CACHE_ROOT_DIRNAME = ".melosviz/render_cache"


def _cache_root() -> Path:
    """Default cache root — overridable via MELOSVIZ_RENDER_CACHE_ROOT."""
    override = os.environ.get("MELOSVIZ_RENDER_CACHE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path.cwd() / CACHE_ROOT_DIRNAME


def _audio_fingerprint(scene: Mapping[str, Any]) -> str:
    """Content-hash of the audio input for *scene* (or "" if none).

    Two scenes with the same prompt / seed / camera but different audio
    must hash to different fingerprints — otherwise a re-render against
    a swapped audio source would silently reuse the cached visual from
    the previous audio. We hash the actual file content (cheap for the
    short clips that ship through this pipeline) when present, and fall
    back to the path string so callers can still get a stable key when
    the audio is only described symbolically.
    """
    audio = scene.get("audio") or scene.get("wav_path") or scene.get("audio_path")
    if audio is None or audio == "":
        return ""
    path = Path(str(audio))
    if path.is_file():
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"
    # Symbolic / remote reference — keep the string verbatim so the key
    # is still deterministic across hosts.
    return f"path:{path.as_posix()}"


@dataclass(frozen=True)
class SceneCacheKey:
    """A scene's render input fingerprint.

    Two scenes with the same SceneCacheKey are guaranteed to produce the
    same rendered artifact (modulo non-deterministic noise we don't model
    yet, e.g. CUDA timing). Used to skip re-renders on the second
    `viz generate --storyboard storyboard_v2.json` run after a `viz direct`
    edit that only touched scene N.
    """

    backend: str
    scene_type: str
    prompt: str
    seed: int
    width: int
    height: int
    fps: int
    camera: str
    camera_motion: str
    subject_token: str
    env_token: str
    palette_key: str
    lrc_phrase_key: str
    audio_fingerprint: str
    extra: Mapping[str, Any]

    @staticmethod
    def from_scene(scene: Mapping[str, Any], backend_key: str, render_spec: Any) -> "SceneCacheKey":
        """Build a SceneCacheKey from a storyboard scene + adapter metadata."""
        continuity = scene.get("continuity") or {}
        lyric = scene.get("lyric") or {}
        palette = scene.get("palette") or []
        if isinstance(palette, str):
            palette_list = [p.strip() for p in palette.split() if p.strip()]
        else:
            palette_list = [str(p) for p in palette]
        seed = scene.get("seed")
        if seed is None:
            seed = 0
        width = int(scene.get("width", getattr(render_spec, "width", 1920) or 1920))
        height = int(scene.get("height", getattr(render_spec, "height", 1080) or 1080))
        fps = int(scene.get("fps", getattr(render_spec, "fps", 24) or 24))
        return SceneCacheKey(
            backend=backend_key,
            scene_type=str(scene.get("scene_type", "")),
            prompt=str(scene.get("prompt") or ""),
            seed=int(seed),
            width=width,
            height=height,
            fps=fps,
            camera=str(scene.get("camera") or ""),
            camera_motion=str(scene.get("camera_motion") or ""),
            subject_token=str(continuity.get("subject_token") or ""),
            env_token=str(continuity.get("env_token") or ""),
            palette_key="|".join(palette_list),
            lrc_phrase_key=f"{lyric.get('phrase_id', '')}::{lyric.get('start', 0):.3f}->{lyric.get('end', 0):.3f}",
            audio_fingerprint=_audio_fingerprint(scene),
            extra=copy.deepcopy(scene.get("cache_extra") or {}),
        )

    def fingerprint(self) -> str:
        """SHA-256 hex of the JSON-serialized inputs (deterministic)."""
        payload = {
            "backend": self.backend,
            "scene_type": self.scene_type,
            "prompt": self.prompt,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "camera": self.camera,
            "camera_motion": self.camera_motion,
            "subject_token": self.subject_token,
            "env_token": self.env_token,
            "palette_key": self.palette_key,
            "lrc_phrase_key": self.lrc_phrase_key,
            "audio_fingerprint": self.audio_fingerprint,
            "extra": dict(self.extra),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class RenderCache:
    """Content-addressed per-scene artifact cache."""

    cache_dir: Path

    @staticmethod
    def for_storyboard(storyboard_id: str, root: Path | None = None) -> "RenderCache":
        rid = (storyboard_id or "default").strip() or "default"
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in rid)
        base = (root or _cache_root()) / safe
        base.mkdir(parents=True, exist_ok=True)
        return RenderCache(cache_dir=base)

    def lookup(self, key: SceneCacheKey) -> Path | None:
        target = self.cache_dir / f"{key.fingerprint()}.bin"
        if target.exists() and target.stat().st_size > 0:
            return target
        return None

    def store(self, key: SceneCacheKey, src_artifact_path: Path, meta: Mapping[str, Any] | None = None) -> Path:
        target = self.cache_dir / f"{key.fingerprint()}.bin"
        meta_path = self.cache_dir / f"{key.fingerprint()}.json"
        src = Path(src_artifact_path)
        if target.exists():
            target.unlink()
        if src.is_file():
            shutil.copy2(src, target)
        else:
            target.write_text(src.read_text() if src.exists() else "", encoding="utf-8")
        meta_obj = {
            "fingerprint": key.fingerprint(),
            "stored_at": time.time(),
            "backend": key.backend,
            "scene_type": key.scene_type,
            "prompt_sha": hashlib.sha256(key.prompt.encode("utf-8")).hexdigest()[:16],
            "size_bytes": target.stat().st_size,
            "scene_index": (meta or {}).get("scene_index"),
            "scene_name": (meta or {}).get("scene_name"),
            "storyboard_id": (meta or {}).get("storyboard_id"),
            "seed": key.seed,
        }
        meta_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def stats(self) -> dict:
        files = list(self.cache_dir.glob("*.bin"))
        total = sum(f.stat().st_size for f in files if f.is_file())
        return {
            "cache_dir": str(self.cache_dir),
            "hits": 0,  # populated by the caller
            "misses": 0,  # populated by the caller
            "stored": len(files),
            "total_bytes": total,
        }


def scene_cache_key(seg: dict, cache_root: Path) -> SceneCacheKey:
    """Build a :class:`SceneCacheKey` for *seg* under *cache_root*.

    Convenience wrapper used by the orchestrator to compute a fingerprint
    for the render-cache lookup. Falls back to a minimal key when the
    storyboard spec doesn't supply rich metadata.
    """
    # Build a thin RenderSpec stand-in for from_scene — only attributes
    # the from_scene factory reads (width / height / fps) are needed.
    spec_proxy = type("_S", (), {
        "width": int(seg.get("width", 1920) or 1920),
        "height": int(seg.get("height", 1080) or 1080),
        "fps": int(seg.get("fps", 24) or 24),
    })()
    backend = str(seg.get("backend") or seg.get("scene_type") or "unknown")
    return SceneCacheKey.from_scene(seg, backend, spec_proxy)


def scene_render_cached(seg: dict, cache_root: Path) -> Path | None:
    """Look up a cached artifact for *seg* in *cache_root*.

    Returns the cached path if a hit is found, otherwise ``None``. The
    orchestrator uses this for a fast-path before dispatching to
    adapters.
    """
    if cache_root is None or not Path(cache_root).is_dir():
        return None
    key = scene_cache_key(seg, cache_root)
    cache = RenderCache(cache_dir=Path(cache_root))
    return cache.lookup(key)


__all__ = [
    "RenderCache",
    "SceneCacheKey",
    "scene_cache_key",
    "scene_render_cached",
]
