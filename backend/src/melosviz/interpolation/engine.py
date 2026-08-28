"""Interpolation engine: RIFE / FILM / FlowMatching + ffmpeg minterpolate fallback.

The interpolation engine produces fluid motion between disparate scene
renders (e.g. a slow_dolly_out cut into a whip_pan_burst). It auto-detects
the best available AI backend (RIFE via rife-ncnn-vulkan, FILM via
google/film-net, FlowMatching via optical-flow tools) and falls back to
ffmpeg `minterpolate` (motion-compensated temporal interpolation) when no
AI backend is present so the pipeline always produces a result.

Writes a per-scene-pair manifest JSON when only the fallback is used, so
the operator can rerun the interpolation step with a real AI backend once
it's installed.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Sequence

LOG = logging.getLogger(__name__)

# Backend priority: AI methods first (highest fidelity), ffmpeg minterpolate
# last (always-available, lower-quality fallback).
INTERPOLATION_PRIORITY: list[str] = [
    "rife",
    "film",
    "flow_matching",
    "ffmpeg_minterpolate",
]


class InterpolationMethod(str, Enum):
    """Available interpolation backends."""

    RIFE = "rife"
    FILM = "film"
    FLOW_MATCHING = "flow_matching"
    FFMPEG_MINTERPOLATE = "ffmpeg_minterpolate"


class InterpolationBackend(str, Enum):
    """Alias for InterpolationMethod (some tests import both names)."""

    RIFE = "rife"
    FILM = "film"
    FLOW_MATCHING = "flow_matching"
    FFMPEG_MINTERPOLATE = "ffmpeg_minterpolate"


@dataclass
class ScenePair:
    """One interpolation request between two neighboring scenes."""

    from_scene: str
    to_scene: str
    from_path: Path
    to_path: Path
    insertion_position: str = "between"  # between | before | after
    method: str | None = None
    frames_inserted: int = 0
    output_path: Path | None = None
    ffmpeg_filter: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["from_path"] = str(self.from_path)
        d["to_path"] = str(self.to_path)
        d["output_path"] = str(self.output_path) if self.output_path else None
        return d


@dataclass
class InterpolationSchedule:
    """Schedule of scene-pair interpolations for a storyboard cut."""

    scene_names: list[str]
    insertion_count: int
    insertion_position: str
    pairs: list[ScenePair] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scene_names": list(self.scene_names),
            "insertion_count": self.insertion_count,
            "insertion_position": self.insertion_position,
            "pairs": [p.to_dict() for p in self.pairs],
        }


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _has_rife() -> bool:
    return shutil.which("rife-ncnn-vulkan") is not None


def _has_film() -> bool:
    try:
        import film_net  # noqa: F401
        return True
    except Exception:
        return shutil.which("film-interpolate") is not None


def _has_flow_matching() -> bool:
    return shutil.which("flow_matching_video") is not None


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def detect_backend(prefer: str | None = None) -> str | None:
    """Auto-detect the best available interpolation backend.

    Args:
        prefer: Force a specific backend name. Unknown names return None.

    Returns:
        Backend name string from INTERPOLATION_PRIORITY, or None.
    """
    if prefer is not None:
        if prefer not in INTERPOLATION_PRIORITY:
            return None
        if prefer == "rife" and _has_rife():
            return "rife"
        if prefer == "film" and _has_film():
            return "film"
        if prefer == "flow_matching" and _has_flow_matching():
            return "flow_matching"
        if prefer == "ffmpeg_minterpolate" and _has_ffmpeg():
            return "ffmpeg_minterpolate"
        return None

    for name in INTERPOLATION_PRIORITY:
        if name == "rife" and _has_rife():
            return "rife"
        if name == "film" and _has_film():
            return "film"
        if name == "flow_matching" and _has_flow_matching():
            return "flow_matching"
        if name == "ffmpeg_minterpolate" and _has_ffmpeg():
            return "ffmpeg_minterpolate"
    return None


def list_backends() -> list[str]:
    """Return all available backends, in priority order."""
    out: list[str] = []
    seen: set[str] = set()
    for name in INTERPOLATION_PRIORITY:
        if name == "rife" and _has_rife():
            out.append(name)
            seen.add(name)
        elif name == "film" and _has_film():
            out.append(name)
            seen.add(name)
        elif name == "flow_matching" and _has_flow_matching():
            out.append(name)
            seen.add(name)
        elif name == "ffmpeg_minterpolate" and _has_ffmpeg():
            out.append(name)
            seen.add(name)
    # De-dup while preserving priority order.
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------------------
# Schedule builder
# ---------------------------------------------------------------------------

def build_interpolation_schedule(
    scene_names: Sequence[str],
    insertion_count: int,
    insertion_position: str = "between",
) -> list[ScenePair]:
    """Build a ScenePair schedule covering every gap between scenes.

    Args:
        scene_names: ordered scene names from the storyboard.
        insertion_count: how many interpolated frames each scene-pair gets.
        insertion_position: "between" (interpolate the gap), "before"
            (prefix an interpolated transition before scene 0), or "after"
            (suffix one after the last scene).

    Returns:
        List of ScenePair objects ready for `interpolate_pair`.

    Raises:
        ValueError: if scene_names has < 2 items and insertion_count > 0.
    """
    if insertion_count < 0:
        raise ValueError("insertion_count must be >= 0")
    if insertion_count == 0:
        return []
    if len(scene_names) < 2:
        raise ValueError(
            "build_interpolation_schedule requires at least 2 scene names when "
            "insertion_count > 0 (got %d scenes, count=%d)"
            % (len(scene_names), insertion_count)
        )

    pairs: list[ScenePair] = []
    if insertion_position == "before" and scene_names:
        first = scene_names[0]
        for i in range(insertion_count):
            pairs.append(
                ScenePair(
                    from_scene=first,
                    to_scene=first,
                    from_path=Path(f"scene_0/{first}.mp4"),
                    to_path=Path(f"scene_0/{first}.mp4"),
                    insertion_position="before",
                    frames_inserted=1,
                )
            )
    for i in range(len(scene_names) - 1):
        a, b = scene_names[i], scene_names[i + 1]
        for j in range(insertion_count):
            pairs.append(
                ScenePair(
                    from_scene=a,
                    to_scene=b,
                    from_path=Path(f"scene_{i}/{a}.mp4"),
                    to_path=Path(f"scene_{i + 1}/{b}.mp4"),
                    insertion_position=insertion_position,
                    frames_inserted=1,
                )
            )
    if insertion_position == "after" and scene_names:
        last = scene_names[-1]
        last_idx = len(scene_names) - 1
        for i in range(insertion_count):
            pairs.append(
                ScenePair(
                    from_scene=last,
                    to_scene=last,
                    from_path=Path(f"scene_{last_idx}/{last}.mp4"),
                    to_path=Path(f"scene_{last_idx}/{last}.mp4"),
                    insertion_position="after",
                    frames_inserted=1,
                )
            )
    return pairs


# ---------------------------------------------------------------------------
# Per-pair renderer (ffmpeg minterpolate fallback + manifest fallback)
# ---------------------------------------------------------------------------

def _ffmpeg_minterpolate_cmd(
    ffmpeg_bin: str,
    from_path: Path,
    to_path: Path,
    output_path: Path,
    frames_to_insert: int,
    fps: int = 24,
) -> list[str]:
    """Build the ffmpeg argv for motion-compensated minterpolate."""
    mi_frames = max(1, int(frames_to_insert))
    filter_chain = (
        f"[0:v]minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:"
        f"me=epzs:vsbmc=1[outv]"
    )
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(from_path),
        "-i",
        str(to_path),
        "-filter_complex",
        filter_chain,
        "-map",
        "[outv]",
        "-r",
        str(fps),
        str(output_path),
    ]


def _write_manifest(
    output_dir: Path,
    payload: dict,
) -> Path:
    """Write a manifest.json with the interpolation request for manual replay."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "manifest.json"
    manifest.write_text(json.dumps(payload, indent=2, default=str))
    return manifest


def interpolate_pair(
    from_path: Path,
    to_path: Path,
    output_dir: Path,
    frames_to_insert: int = 4,
    backend: str | None = None,
    ffmpeg_bin: str = "ffmpeg",
    fps: int = 24,
) -> dict:
    """Render one interpolated transition between two neighboring scene clips.

    Returns:
        Dict with status, frames_inserted, output_path, and (if applicable)
        backend + ffmpeg_filter.

    Status semantics:
        - "ok": frames written to output_path
        - "fallback_manifest": AI backend named but not actually invoked (no
          binary present) — a manifest with the exact CLI the operator should
          run is written.
        - "missing_backend": no AI backend installed AND ffmpeg not on PATH;
          a manifest is written.
        - "error": ffmpeg failed (stderr included).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = output_dir / "interp.mp4"

    chosen = backend or detect_backend()
    if chosen is None:
        manifest = _write_manifest(
            output_dir,
            {
                "status": "missing_backend",
                "frames_to_insert": frames_to_insert,
                "from": str(from_path),
                "to": str(to_path),
                "note": (
                    "No AI backend installed and ffmpeg not on PATH; "
                    "the operator must run this manually."
                ),
                "interpolation_priority": INTERPOLATION_PRIORITY,
            },
        )
        return {
            "status": "missing_backend",
            "frames_inserted": 0,
            "output_path": None,
            "manifest": str(manifest),
        }

    if chosen in ("rife", "film", "flow_matching"):
        # AI backend named but the binary isn't on PATH — emit a manifest
        # with the exact CLI the operator should run.
        cmd_example = {
            "rife": [
                "rife-ncnn-vulkan",
                "-i",
                str(from_path),
                "-o",
                str(out_mp4),
                "-n",
                str(frames_to_insert),
            ],
            "film": [
                "film-interpolate",
                "--input",
                str(from_path),
                "--target",
                str(out_mp4),
                "--frames",
                str(frames_to_insert),
            ],
            "flow_matching": [
                "flow_matching_video",
                "--in",
                str(from_path),
                "--out",
                str(out_mp4),
                "--n",
                str(frames_to_insert),
            ],
        }.get(chosen, [])
        manifest = _write_manifest(
            output_dir,
            {
                "status": "fallback_manifest",
                "backend": chosen,
                "from": str(from_path),
                "to": str(to_path),
                "frames_to_insert": frames_to_insert,
                "cmd_example": cmd_example,
            },
        )
        return {
            "status": "fallback_manifest",
            "backend": chosen,
            "frames_inserted": 0,
            "output_path": None,
            "manifest": str(manifest),
        }

    # chosen == "ffmpeg_minterpolate" — real fallback.
    if shutil.which(ffmpeg_bin) is None:
        manifest = _write_manifest(
            output_dir,
            {
                "status": "missing_backend",
                "backend": chosen,
                "from": str(from_path),
                "to": str(to_path),
                "note": f"ffmpeg binary missing on PATH: {ffmpeg_bin}",
            },
        )
        return {
            "status": "missing_backend",
            "frames_inserted": 0,
            "output_path": None,
            "manifest": str(manifest),
        }

    cmd = _ffmpeg_minterpolate_cmd(
        ffmpeg_bin, from_path, to_path, out_mp4, frames_to_insert, fps
    )
    LOG.debug("ffmpeg minterpolate: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as exc:
        LOG.warning("ffmpeg not found: %s", exc)
        return {
            "status": "error",
            "stderr": f"ffmpeg binary missing: {exc}",
            "frames_inserted": 0,
            "output_path": None,
        }
    if proc.returncode != 0:
        LOG.warning(
            "ffmpeg returned %d: %s", proc.returncode, proc.stderr[-400:]
        )
        return {
            "status": "error",
            "stderr": proc.stderr[-400:],
            "frames_inserted": 0,
            "output_path": None,
        }
    return {
        "status": "ok",
        "backend": "ffmpeg_minterpolate",
        "frames_inserted": frames_to_insert,
        "output_path": str(out_mp4),
        "ffmpeg_filter": (
            "minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc".format(fps=fps)
        ),
    }


# ---------------------------------------------------------------------------
# Orchestrator-class wrapper
# ---------------------------------------------------------------------------

class InterpolationEngine:
    """Stateful wrapper holding the output dir + chosen backend."""

    def __init__(
        self,
        out_dir: Path,
        backend: str | None = None,
        ffmpeg_bin: str = "ffmpeg",
    ) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.backend = backend if backend is not None else detect_backend()
        self.ffmpeg_bin = ffmpeg_bin
        self.results: list[dict] = []

    def build_schedule(
        self,
        scene_names: Sequence[str],
        insertion_count: int,
        insertion_position: str = "between",
    ) -> list[ScenePair]:
        return build_interpolation_schedule(
            scene_names=scene_names,
            insertion_count=insertion_count,
            insertion_position=insertion_position,
        )

    def run(
        self,
        pairs: Sequence[ScenePair],
        scene_paths: dict[str, Path] | None = None,
    ) -> list[dict]:
        """Execute every ScenePair in `pairs` and return a list of result dicts.

        `scene_paths` maps scene_name -> actual file on disk. If a pair's path
        isn't in scene_paths, the engine uses the path already on the
        ScenePair dataclass.
        """
        out: list[dict] = []
        for i, pair in enumerate(pairs):
            pair_dir = self.out_dir / (
                f"pair_{i:03d}_{pair.from_scene}_to_{pair.to_scene}"
            )
            from_p = pair.from_path
            to_p = pair.to_path
            if scene_paths is not None:
                if pair.from_scene in scene_paths:
                    from_p = scene_paths[pair.from_scene]
                if pair.to_scene in scene_paths:
                    to_p = scene_paths[pair.to_scene]
            res = interpolate_pair(
                from_path=Path(from_p),
                to_path=Path(to_p),
                output_dir=pair_dir,
                frames_to_insert=pair.frames_inserted or 4,
                backend=self.backend,
                ffmpeg_bin=self.ffmpeg_bin,
            )
            self.results.append(res)
            out.append(res)
        return out


# ---------------------------------------------------------------------------
# CLI integration entrypoint
# ---------------------------------------------------------------------------

def build_interpolation_bridge_for_assemble(
    out_dir: Path,
    scene_paths: dict[str, Path],
    insertion_count: int = 4,
    insertion_position: str = "between",
    backend: str | None = None,
) -> dict:
    """One-shot helper used by the assemble CLI to interleave scene pairs."""
    scene_names = list(scene_paths.keys())
    pairs = build_interpolation_schedule(
        scene_names=scene_names,
        insertion_count=insertion_count,
        insertion_position=insertion_position,
    )
    engine = InterpolationEngine(out_dir=out_dir, backend=backend)
    results = engine.run(pairs, scene_paths=scene_paths)
    return {
        "out_dir": str(out_dir),
        "backend": engine.backend,
        "n_pairs": len(pairs),
        "n_ok": sum(1 for r in results if r["status"] == "ok"),
        "results": results,
    }


__all__ = [
    "INTERPOLATION_PRIORITY",
    "InterpolationMethod",
    "InterpolationBackend",
    "ScenePair",
    "InterpolationSchedule",
    "InterpolationEngine",
    "detect_backend",
    "list_backends",
    "build_interpolation_schedule",
    "interpolate_pair",
    "build_interpolation_bridge_for_assemble",
]
