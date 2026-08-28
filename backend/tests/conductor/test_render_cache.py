"""Tests for the render-cache module that lets the orchestrator skip scenes
whose render inputs (prompt + camera + palette + seed + backend + width +
height + fps + continuity tokens) didn't change across runs.

Cache key: SHA-256 of the JSON-serialized ``SceneCacheKey`` fields.
Cache layout: ``.melosviz/render_cache/<storyboard_id>/<fingerprint>.bin``
plus a sibling ``<fingerprint>.json`` with the render metadata.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from melosviz.conductor.render_cache import (
    CACHE_ROOT_DIRNAME,
    RenderCache,
    SceneCacheKey,
)


def _render_spec_stub(width: int = 1920, height: int = 1080, fps: int = 24):
    """Minimal stand-in for an analysis.models.RenderSpec."""
    class _RS:
        pass
    rs = _RS()
    rs.width = width
    rs.height = height
    rs.fps = fps
    return rs


def _make_scene(
    index: int = 0,
    prompt: str = "neon underwater city",
    camera: str = "slow_dolly_in",
    palette=None,
    seed: int = 42,
    scene_type: str = "comfyui_image",
    subject_token: str = "silver-haired dancer",
    env_token: str = "underwater city",
):
    palette = palette if palette is not None else ["#0d0d10", "#ff2bd6"]
    return {
        "scene_index": index,
        "prompt": prompt,
        "camera": camera,
        "palette": palette,
        "seed": seed,
        "scene_type": scene_type,
        "continuity": {"subject_token": subject_token, "env_token": env_token},
        "lyric": {"phrase_id": "p1", "start": 0.0, "end": 5.0},
        "width": 1920,
        "height": 1080,
        "fps": 24,
    }


def _make_artifact(tmp_path: Path, scene_index: int, payload: str = "rendered-bytes") -> Path:
    p = tmp_path / f"scene_{scene_index:04d}.bin"
    p.write_text(payload, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# SceneCacheKey
# ---------------------------------------------------------------------------

def test_scene_cache_key_is_stable_for_same_scene():
    spec = _render_spec_stub()
    s = _make_scene()
    k1 = SceneCacheKey.from_scene(s, "comfyui_image", spec)
    k2 = SceneCacheKey.from_scene(s, "comfyui_image", spec)
    assert k1.fingerprint() == k2.fingerprint()


def test_scene_cache_key_changes_when_prompt_changes():
    spec = _render_spec_stub()
    k1 = SceneCacheKey.from_scene(_make_scene(prompt="a"), "comfyui_image", spec)
    k2 = SceneCacheKey.from_scene(_make_scene(prompt="b"), "comfyui_image", spec)
    assert k1.fingerprint() != k2.fingerprint()


def test_scene_cache_key_changes_when_camera_changes():
    spec = _render_spec_stub()
    k1 = SceneCacheKey.from_scene(_make_scene(camera="slow_dolly_in"), "comfyui_image", spec)
    k2 = SceneCacheKey.from_scene(_make_scene(camera="whip_pan_burst"), "comfyui_image", spec)
    assert k1.fingerprint() != k2.fingerprint()


def test_scene_cache_key_changes_when_palette_changes():
    spec = _render_spec_stub()
    k1 = SceneCacheKey.from_scene(_make_scene(palette=["#0d0d10", "#ff2bd6"]), "comfyui_image", spec)
    k2 = SceneCacheKey.from_scene(_make_scene(palette=["#0d0d10", "#22d3ee"]), "comfyui_image", spec)
    assert k1.fingerprint() != k2.fingerprint()


def test_scene_cache_key_changes_when_seed_changes():
    spec = _render_spec_stub()
    k1 = SceneCacheKey.from_scene(_make_scene(seed=42), "comfyui_image", spec)
    k2 = SceneCacheKey.from_scene(_make_scene(seed=99), "comfyui_image", spec)
    assert k1.fingerprint() != k2.fingerprint()


def test_scene_cache_key_changes_when_backend_changes():
    spec = _render_spec_stub()
    k1 = SceneCacheKey.from_scene(_make_scene(), "comfyui_image", spec)
    k2 = SceneCacheKey.from_scene(_make_scene(), "comfyui_video", spec)
    assert k1.fingerprint() != k2.fingerprint()


def test_scene_cache_key_changes_when_resolution_changes():
    spec = _render_spec_stub()
    s1 = _make_scene()
    s1.pop("width", None); s1.pop("height", None); s1.pop("fps", None)
    k1 = SceneCacheKey.from_scene(s1, "comfyui_image", spec)
    spec2 = _render_spec_stub(width=3840, height=2160, fps=30)
    s2 = _make_scene()
    s2.pop("width", None); s2.pop("height", None); s2.pop("fps", None)
    k2 = SceneCacheKey.from_scene(s2, "comfyui_image", spec2)
    assert k1.fingerprint() != k2.fingerprint()


def test_scene_cache_key_uses_palette_string_when_palette_is_string():
    spec = _render_spec_stub()
    s = _make_scene()
    s["palette"] = "#0d0d10 #ff2bd6 #22d3ee"
    k = SceneCacheKey.from_scene(s, "comfyui_image", spec)
    assert "0d0d10" in k.palette_key and "ff2bd6" in k.palette_key


def test_scene_cache_key_handles_missing_seed():
    spec = _render_spec_stub()
    s = _make_scene()
    s.pop("seed", None)
    k = SceneCacheKey.from_scene(s, "comfyui_image", spec)
    assert k.seed == 0


# ---------------------------------------------------------------------------
# RenderCache
# ---------------------------------------------------------------------------

def test_render_cache_for_storyboard_creates_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MELOSVIZ_RENDER_CACHE_ROOT", str(tmp_path))
    cache = RenderCache.for_storyboard("neon-tide")
    assert cache.cache_dir.exists()
    assert cache.cache_dir.parent == tmp_path


def test_render_cache_lookup_miss_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("MELOSVIZ_RENDER_CACHE_ROOT", str(tmp_path))
    cache = RenderCache.for_storyboard("neon-tide")
    spec = _render_spec_stub()
    key = SceneCacheKey.from_scene(_make_scene(), "comfyui_image", spec)
    assert cache.lookup(key) is None


def test_render_cache_store_then_lookup_hits(tmp_path, monkeypatch):
    monkeypatch.setenv("MELOSVIZ_RENDER_CACHE_ROOT", str(tmp_path))
    cache = RenderCache.for_storyboard("neon-tide")
    spec = _render_spec_stub()

    src = _make_artifact(tmp_path, 0)
    key = SceneCacheKey.from_scene(_make_scene(), "comfyui_image", spec)
    stored = cache.store(key, src, meta={"scene_index": 0, "scene_name": "intro", "storyboard_id": "neon-tide"})

    assert stored.exists()
    assert stored.read_text() == "rendered-bytes"
    hit = cache.lookup(key)
    assert hit is not None
    assert hit.read_text() == "rendered-bytes"


def test_render_cache_sibling_metadata_json(tmp_path, monkeypatch):
    monkeypatch.setenv("MELOSVIZ_RENDER_CACHE_ROOT", str(tmp_path))
    cache = RenderCache.for_storyboard("neon-tide")
    spec = _render_spec_stub()
    src = _make_artifact(tmp_path, 0)
    key = SceneCacheKey.from_scene(_make_scene(seed=7), "comfyui_image", spec)
    stored = cache.store(key, src, meta={"scene_index": 0, "scene_name": "intro", "storyboard_id": "neon-tide"})
    meta_path = stored.with_suffix(".json")
    assert meta_path.exists()
    import json
    meta = json.loads(meta_path.read_text())
    assert meta["fingerprint"] == key.fingerprint()
    assert meta["seed"] == 7
    assert meta["scene_index"] == 0
    assert meta["scene_name"] == "intro"
    assert meta["storyboard_id"] == "neon-tide"


def test_render_cache_stats(tmp_path, monkeypatch):
    monkeypatch.setenv("MELOSVIZ_RENDER_CACHE_ROOT", str(tmp_path))
    cache = RenderCache.for_storyboard("neon-tide")
    spec = _render_spec_stub()
    for i in range(3):
        src = _make_artifact(tmp_path, i, payload=f"bytes-{i}")
        # Vary the prompt per index so each SceneCacheKey is distinct
        key = SceneCacheKey.from_scene(_make_scene(index=i, prompt=f"neon underwater city {i}"), "comfyui_image", spec)
        cache.store(key, src, meta={"scene_index": i})
    stats = cache.stats()
    assert stats["stored"] == 3
    assert stats["total_bytes"] > 0
    assert stats["cache_dir"].endswith("neon-tide")


def test_render_cache_storyboard_id_sanitization(tmp_path, monkeypatch):
    monkeypatch.setenv("MELOSVIZ_RENDER_CACHE_ROOT", str(tmp_path))
    cache = RenderCache.for_storyboard("foo/../bar&baz?")
    assert cache.cache_dir.exists()
    # Illegal chars get replaced with _
    assert "/" not in cache.cache_dir.name or cache.cache_dir.name == "foo_.._bar_baz_"


def test_render_cache_handles_preexisting_file_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("MELOSVIZ_RENDER_CACHE_ROOT", str(tmp_path))
    cache = RenderCache.for_storyboard("neon-tide")
    spec = _render_spec_stub()
    src = _make_artifact(tmp_path, 0, payload="first")
    key = SceneCacheKey.from_scene(_make_scene(), "comfyui_image", spec)
    cache.store(key, src, meta={"scene_index": 0})

    src.write_text("second", encoding="utf-8")
    cache.store(key, src, meta={"scene_index": 0})

    hit = cache.lookup(key)
    assert hit is not None
    assert hit.read_text() == "second"
