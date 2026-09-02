"""Deterministic VJ cue writers (SVG + Lottie).

Generates per-shot SVG thumbnail cards and Lottie JSON marker files
from the melosviz render pipeline's output tree.  Both outputs are
fully deterministic — two identical render runs produce byte-identical
files — so the downstream ``package`` module can compute reproducible
ZIP manifests.

VJ software compatibility
--------------------------
* SVG cards are valid SVG 1.1 and can be imported directly into
  Resolume Avenue, TouchDesigner, VVVV, or any modern browser.
* Lottie JSON uses AE/Lottie spec 5.12.0 and is compatible with
  Resolume Wire, VVVV (vl.io.Animation), and After Effects via the
  bodymovin plugin.  Markers (``lottie["markers"]``) align to frame
  numbers so the DJ can sync their set to the exact beats baked into
  the visuals.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Iterable, Sequence


def _json_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.json")
        if "deliverables" not in path.parts and "vj" not in path.parts
    )


def _load_objects(root: Path) -> list[dict]:
    objects: list[dict] = []
    for path in _json_files(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def _normalize_shot(raw: dict, fallback_index: int) -> dict:
    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    scene_index = int(raw.get("scene_index", raw.get("index", fallback_index)))
    shot_index = int(raw.get("shot_index", 0))
    start = float(
        raw.get("start")
        or raw.get("start_seconds")
        or extra.get("start_seconds")
        or 0.0
    )
    duration = float(
        raw.get("duration_s") or raw.get("duration") or extra.get("duration_s") or 0.0
    )
    if duration <= 0 and raw.get("end") is not None:
        duration = max(0.0, float(raw["end"]) - start)
    if duration <= 0 and extra.get("end_seconds") is not None:
        duration = max(0.0, float(extra["end_seconds"]) - start)
    beats = (
        raw.get("beats")
        or raw.get("beats_in_segment")
        or raw.get("beat_seconds")
        or extra.get("beat_seconds")
        or []
    )
    palette = raw.get("palette") or raw.get("palette_override") or ["#7c6af7"]
    return {
        "scene_index": scene_index,
        "shot_index": shot_index,
        "start": start,
        "duration_s": max(1 / 24, duration),
        "label": str(raw.get("label") or raw.get("scene_name") or f"scene-{scene_index}"),
        "prompt": str(raw.get("prompt") or ""),
        "camera_motion": str(raw.get("camera_motion") or raw.get("camera") or "static"),
        "palette": [str(c) for c in palette],
        "beats": [float(b) for b in beats],
        "width": int(raw.get("width", 1920) or 1920),
        "height": int(raw.get("height", 1080) or 1080),
        "fps": int(raw.get("fps", 24) or 24),
    }


def discover_shots(job_dir: Path, media_paths: Sequence[Path]) -> list[dict]:
    """Discover all shots from a melosviz render job directory.

    Shot sources are consulted in priority order:
    1. Any JSON with a top-level ``shots`` array (multi-shot plan).
    2. Any JSON with a top-level ``scenes`` array (storyboard).
    3. Any JSON with ``artifact_path`` + ``scene_index`` (provenance sidecar).
    4. ``media_paths`` sorted by their relative path as a last resort.

    Args:
        job_dir: Root of the render job output (contains scene_*/ directories).
        media_paths: Fallback list of media files when no JSON plan exists.

    Returns:
        Sorted list of normalized shot dicts (scene_index, shot_index, start,
        duration_s, label, prompt, camera_motion, palette, beats, width, height,
        fps).
    """
    objects = _load_objects(job_dir)
    for key in ("shots", "scenes"):
        for payload in objects:
            values = payload.get(key)
            if isinstance(values, list) and values:
                shots = [
                    _normalize_shot(value, index)
                    for index, value in enumerate(values)
                    if isinstance(value, dict)
                ]
                return sorted(
                    shots, key=lambda item: (item["scene_index"], item["shot_index"])
                )
    provenance = [
        payload for payload in objects
        if "artifact_path" in payload and "scene_index" in payload
    ]
    if provenance:
        return sorted(
            [
                _normalize_shot(value, index)
                for index, value in enumerate(provenance)
            ],
            key=lambda item: (item["scene_index"], item["shot_index"]),
        )
    return [
        _normalize_shot({"index": index, "label": path.stem}, index)
        for index, path in enumerate(sorted(media_paths, key=lambda p: p.as_posix()))
    ]


def _svg(shot: dict) -> str:
    """Render a 960x540 SVG VJ thumbnail card for one shot."""
    label = html.escape(shot["label"][:80], quote=True)
    prompt = html.escape(" ".join(shot["prompt"].split())[:180], quote=True)
    camera = html.escape(shot["camera_motion"][:80], quote=True)
    colors = shot["palette"] or ["#7c6af7"]
    duration = shot["duration_s"]
    beat_lines: list[str] = []
    for beat in shot["beats"]:
        relative = (beat - shot["start"]) / duration
        x = 64 + round(max(0.0, min(1.0, relative)) * 832, 3)
        beat_lines.append(
            f'<line x1="{x}" y1="455" x2="{x}" y2="500" stroke="#ffffff" />'
        )
    swatches = "".join(
        f'<rect x="{64 + index * 96}" y="300" width="80" height="80" '
        f'fill="{html.escape(color, quote=True)}" />'
        for index, color in enumerate(colors[:8])
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" '
        'viewBox="0 0 960 540">\n'
        '<rect width="960" height="540" fill="#0d0d10" />\n'
        f'<text x="64" y="72" fill="#ffffff" font-size="30">{label}</text>\n'
        f'<text x="64" y="120" fill="#ccccd8" font-size="18">{camera}</text>\n'
        f'<text x="64" y="176" fill="#ffffff" font-size="20">{prompt}</text>\n'
        f"{swatches}\n"
        '<line x1="64" y1="480" x2="896" y2="480" stroke="#888899" />\n'
        f'{"".join(beat_lines)}\n'
        f'<text x="64" y="525" fill="#ccccd8" font-size="16">'
        f'{shot["start"]:.3f}s + {duration:.3f}s</text>\n'
        "</svg>\n"
    )


def _lottie(shot: dict) -> dict:
    """Build a Lottie 5.12.0 JSON structure for one shot.

    The file contains:
    * layer 0 (ty=4): palette fill — a solid rectangle in the scene's
      primary colour covering the whole canvas.
    * layer 1 (ty=5): shot label text.
    * layer 2 (ty=5): prompt summary text.
    * markers: ``shot-start``, ``beat-000``..``beat-N``, ``shot-end``
      keyed to frame numbers.
    """
    fps = shot["fps"]
    frames = max(1, round(shot["duration_s"] * fps))
    markers = [{"tm": 0, "cm": "shot-start", "dr": 0}]
    for index, beat in enumerate(shot["beats"]):
        frame = round(max(0.0, beat - shot["start"]) * fps)
        markers.append({"tm": min(frames, frame), "cm": f"beat-{index:03d}", "dr": 0})
    markers.append({"tm": frames, "cm": "shot-end", "dr": 0})
    color = (shot["palette"] or ["#7c6af7"])[0]
    rgb = (
        [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        if len(color) == 7 and color.startswith("#")
        else [0.486, 0.416, 0.969]
    )
    return {
        "v": "5.12.0",
        "fr": fps,
        "ip": 0,
        "op": frames,
        "w": shot["width"],
        "h": shot["height"],
        "nm": f'shot-{shot["scene_index"]:04d}-{shot["shot_index"]:02d}',
        "ddd": 0,
        "assets": [],
        "layers": [
            {
                "ddd": 0,
                "ind": 1,
                "ty": 4,
                "nm": "palette-field",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [shot["width"] / 2, shot["height"] / 2, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]},
                },
                "shapes": [{
                    "ty": "fl",
                    "c": {"a": 0, "k": [*rgb, 1]},
                    "o": {"a": 0, "k": 100},
                    "r": 1,
                    "nm": "palette-fill",
                }],
                "ip": 0,
                "op": frames,
                "st": 0,
                "bm": 0,
            },
            {
                "ddd": 0,
                "ind": 2,
                "ty": 5,
                "nm": "shot-label",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [64, 96, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]},
                },
                "t": {
                    "d": {"k": [{
                        "s": {
                            "sz": [shot["width"] - 128, 180],
                            "ps": [0, 0],
                            "s": 48,
                            "f": "Arial",
                            "t": shot["label"][:80],
                            "j": 0,
                            "tr": 0,
                            "lh": 58,
                            "ls": 0,
                            "fc": [1, 1, 1],
                        },
                        "t": 0,
                    }]},
                    "p": {},
                    "m": {"g": 1, "a": {"a": 0, "k": [0, 0]}},
                },
                "ip": 0,
                "op": frames,
                "st": 0,
                "bm": 0,
            },
            {
                "ddd": 0,
                "ind": 3,
                "ty": 5,
                "nm": "prompt-summary",
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [64, 180, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]},
                },
                "t": {
                    "d": {"k": [{
                        "s": {
                            "sz": [shot["width"] - 128, 280],
                            "ps": [0, 0],
                            "s": 28,
                            "f": "Arial",
                            "t": " ".join(shot["prompt"].split())[:180],
                            "j": 0,
                            "tr": 0,
                            "lh": 36,
                            "ls": 0,
                            "fc": [1, 1, 1],
                        },
                        "t": 0,
                    }]},
                    "p": {},
                    "m": {"g": 1, "a": {"a": 0, "k": [0, 0]}},
                },
                "ip": 0,
                "op": frames,
                "st": 0,
                "bm": 0,
            },
        ],
        "markers": markers,
        "meta": {
            "scene_index": shot["scene_index"],
            "shot_index": shot["shot_index"],
            "label": shot["label"],
            "prompt": " ".join(shot["prompt"].split())[:180],
            "camera_motion": shot["camera_motion"],
        },
    }


def export_vj_cues(shots: Iterable[dict], output_dir: Path) -> list[Path]:
    """Write per-shot VJ cue files (SVG cards + Lottie JSON + manifest).

    Both output formats are fully deterministic — given the same shots
    input the same files are written in the same order every time,
    which is required for reproducible ZIP packaging.

    Args:
        shots: Sequence of normalized shot dicts (see :func:`discover_shots`).
        output_dir: Target directory for ``shot-XXXX-XX.svg``,
            ``shot-XXXX-XX.lottie.json``, and ``manifest.json``.

    Returns:
        List of all written file paths in order.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for raw in shots:
        shot = _normalize_shot(raw, len(written))
        stem = f'shot-{shot["scene_index"]:04d}-{shot["shot_index"]:02d}'
        svg_path = output_dir / f"{stem}.svg"
        lottie_path = output_dir / f"{stem}.lottie.json"
        svg_path.write_text(_svg(shot), encoding="utf-8")
        lottie_path.write_text(
            json.dumps(_lottie(shot), sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        written.extend([svg_path, lottie_path])
    manifest = output_dir / "manifest.json"
    manifest.write_text(
        json.dumps({
            "schema_version": "1.0",
            "cue_count": len(written) // 2,
            "files": [p.name for p in written],
        }, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(manifest)
    return written
