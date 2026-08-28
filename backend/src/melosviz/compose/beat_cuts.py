"""Beat-aligned cut planning for the assembly stage.

When the assembler concatenates per-scene renders, the transitions between
scenes normally land wherever the scene boundary happens to be. For music
videos the convention is to cut on the beat — every cut lands on (or very
near) a snare / kick / downbeat so the edit feels "musical."

This module takes a storyboard + the MIR-derived beat grid (which is already
on every spec) and returns an :class:`AssembleEffectsPlan` with:

* `transition_at_boundary[i]` — what kind of transition to use between
  scene ``i`` and scene ``i + 1`` (``"hard_cut"`` / ``"whip_pan"`` /
  ``"dip_to_black"`` / ``"crossfade"``).
* `internal_cuts[scene_i]` — list of in-scene cut timestamps where we
  should hard-cut to a different camera angle even though the scene
  hasn't ended yet (drives a 3-5 second average shot length instead of
  one shot per scene).
* `cut_points` — flat list of every absolute second in the timeline that
  should land a cut, used downstream by the ffmpeg concat filter.
* `risk_report` — list of warnings (e.g. boundary too far from any beat,
  no lyrics + no MIR cues to align to).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable


# ----------------------------- types ----------------------------- #


@dataclass
class TransitionAtBoundary:
    """How to cut from scene i to scene i + 1."""

    at_scene: int               # index of the scene we're leaving
    at_time: float              # absolute seconds in the timeline
    kind: str                   # "hard_cut" / "whip_pan" / "dip_to_black" / "crossfade"
    nearest_beat: float         # closest beat-grid timestamp
    beat_offset_ms: float       # signed distance to nearest beat (negative = landed early)
    rational: str               # human-readable explanation ("on downbeat", "0.18 s after beat")


@dataclass
class InternalCut:
    """A hard cut within a single scene (camera change)."""

    scene_index: int
    at_time: float
    nearest_beat: float
    beat_offset_ms: float
    target_shot: str = "b-roll"  # "b-roll" / "close-up" / "wide" / "insert"


@dataclass
class AssembleEffectsPlan:
    """Effects / transitions plan the assembler consumes."""

    schema_version: str = "1.0"
    target_avg_shot_length_s: float = 3.5
    transitions: list[TransitionAtBoundary] = field(default_factory=list)
    internal_cuts: list[InternalCut] = field(default_factory=list)
    cut_points: list[float] = field(default_factory=list)
    risk_report: list[str] = field(default_factory=list)

    # convenience -------------------
    @property
    def transition_kinds(self) -> list[str]:
        return [t.kind for t in self.transitions]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target_avg_shot_length_s": self.target_avg_shot_length_s,
            "transitions": [asdict(t) for t in self.transitions],
            "internal_cuts": [asdict(c) for c in self.internal_cuts],
            "cut_points": self.cut_points,
            "risk_report": self.risk_report,
        }


# --------------------------- helpers ---------------------------- #


def _safe_beats(storyboard: dict[str, Any]) -> list[float]:
    """Return a sorted beat list from a storyboard, robust to missing fields."""
    raw = storyboard.get("downbeat_times") or storyboard.get("beat_times") or []
    out: list[float] = []
    for v in raw:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _safe_scenes(storyboard: dict[str, Any]) -> list[dict[str, Any]]:
    """Return scene list, accommodating several historical key names."""
    scenes = storyboard.get("scenes") or storyboard.get("scene_segments") or []
    return [s for s in scenes if isinstance(s, dict)]


def _scene_start(scene: dict[str, Any]) -> float:
    for k in ("start", "start_s", "start_time", "begin"):
        if k in scene:
            try:
                return float(scene[k])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _scene_end(scene: dict[str, Any]) -> float:
    for k in ("end", "end_s", "end_time"):
        if k in scene:
            try:
                return float(scene[k])
            except (TypeError, ValueError):
                return 0.0
    # fall back to start + duration
    dur = scene.get("duration")
    if isinstance(dur, (int, float)):
        return _scene_start(scene) + float(dur)
    return _scene_start(scene)


def _nearest(beats: list[float], t: float) -> tuple[float, float]:
    """Return (nearest_beat, signed_offset_seconds)."""
    if not beats:
        return (t, 0.0)
    best = beats[0]
    best_off = best - t
    for b in beats[1:]:
        off = b - t
        if abs(off) < abs(best_off):
            best = b
            best_off = off
    return best, best_off


# --------------------------- core plan ---------------------------- #


def _pick_transition(scene_a: dict[str, Any], scene_b: dict[str, Any], beat_off_ms: float) -> tuple[str, str]:
    """Choose transition kind + rationale between two consecutive scenes."""
    cam_a = (scene_a.get("camera") or scene_a.get("camera_motion") or "").lower()
    cam_b = (scene_b.get("camera_b") or scene_b.get("camera") or scene_b.get("camera_motion") or "").lower()

    on_beat = abs(beat_off_ms) <= 60.0

    # Same camera + on beat → soft crossfade to avoid jarring seam
    if cam_a and cam_a == cam_b and on_beat:
        return "crossfade", "same camera on beat → 6f crossfade"

    # Whip-pan boundary → whip_pan transition
    if "whip" in cam_a or "whip" in cam_b:
        return "whip_pan", "whip pan camera → whip-pan transition"

    # Drop / chorus boundary → dip to black
    mood = (scene_b.get("lyric", {}) or {}).get("mood_label") if isinstance(scene_b.get("lyric"), dict) else None
    if mood in ("drop", "chorus") or "drop" in (scene_b.get("name", "") or "").lower():
        return "dip_to_black", "drop / chorus boundary → 0.4s dip to black"

    if on_beat:
        return "hard_cut", "on beat → hard cut"
    return "hard_cut", f"nearest beat {beat_off_ms:+.0f} ms → hard cut"


def _plan_internal_cuts(
    scenes: list[dict[str, Any]],
    beats: list[float],
    target_avg_shot_length_s: float,
) -> list[InternalCut]:
    """One cut per (scene) every ~target_avg_shot_length_s, snapped to beat."""
    out: list[InternalCut] = []
    for i, sc in enumerate(scenes):
        start = _scene_start(sc)
        end = _scene_end(sc)
        if end - start <= target_avg_shot_length_s * 1.4:
            continue  # scene is already short, leave it alone
        # place internal cuts every target_avg_shot_length_s, but never in the first
        # 0.8 s (let the scene breathe) or the last 0.5 s (avoid colliding with boundary)
        t = start + target_avg_shot_length_s
        while t + 0.5 < end - 0.5:
            nb, off = _nearest(beats, t)
            # only place if within 200 ms of a beat, otherwise skip (would look arbitrary)
            if abs(off * 1000) <= 200.0:
                out.append(
                    InternalCut(
                        scene_index=i,
                        at_time=t,
                        nearest_beat=nb,
                        beat_offset_ms=off * 1000,
                        target_shot="b-roll" if i % 2 else "close-up",
                    )
                )
            t += target_avg_shot_length_s
    return out


def build_assemble_effects_plan(
    storyboard: dict[str, Any],
    *,
    target_avg_shot_length_s: float = 3.5,
    beat_tolerance_ms: float = 60.0,
) -> AssembleEffectsPlan:
    """Return the effects plan for a storyboard."""
    plan = AssembleEffectsPlan(target_avg_shot_length_s=target_avg_shot_length_s)
    beats = _safe_beats(storyboard)
    scenes = _safe_scenes(storyboard)

    if not beats:
        plan.risk_report.append(
            "No MIR downbeat grid in storyboard — every boundary will fall where the scene ends, "
            "not on a beat. Run 'viz analyze' against a clean WAV first."
        )
    if not scenes:
        plan.risk_report.append("Storyboard contains no scenes.")
        return plan

    # 1. transitions between scenes
    for i, sc in enumerate(scenes):
        if i + 1 >= len(scenes):
            break
        boundary_t = _scene_end(sc)
        nb, off = _nearest(beats, boundary_t)
        kind, rationale = _pick_transition(sc, scenes[i + 1], off * 1000)
        plan.transitions.append(
            TransitionAtBoundary(
                at_scene=i,
                at_time=boundary_t,
                kind=kind,
                nearest_beat=nb,
                beat_offset_ms=off * 1000,
                rational=rationale,
            )
        )
        if beats and abs(off * 1000) > beat_tolerance_ms:
            plan.risk_report.append(
                f"Scene {i}→{i + 1} boundary {boundary_t:.2f}s is {abs(off * 1000):.0f} ms from nearest beat — "
                f"edit will feel unmusical."
            )

    # 2. internal cuts
    plan.internal_cuts = _plan_internal_cuts(scenes, beats, target_avg_shot_length_s)

    # 3. flat cut-points list (boundaries + internal cuts)
    plan.cut_points = sorted(
        [t.at_time for t in plan.transitions] + [c.at_time for c in plan.internal_cuts]
    )

    if plan.transitions:
        kinds = [t.kind for t in plan.transitions]
        plan.risk_report.append(
            "Transition mix: "
            + ", ".join(f"{k}:{v}" for k, v in sorted(
                ((k, kinds.count(k)) for k in set(kinds)),
                key=lambda kv: -kv[1],
            ))
        )

    return plan


# --------------------------- I/O helpers ---------------------------- #


def plan_to_ffmpeg_filter(plan: AssembleEffectsPlan) -> str:
    """Return a human-readable ffmpeg concat+xfade filter sketch."""
    parts = ["ffmpeg -f concat -safe 0 -i list.txt -filter_complex \"[0:v]"]
    if any(t.kind == "crossfade" for t in plan.transitions):
        parts.append("xfade=transition=fade:duration=0.25")
    parts.append("\" -c:v libx264 -preset fast out.mp4")
    return "".join(parts)


def write_effects_plan(plan: AssembleEffectsPlan, out_path: Path) -> Path:
    """Persist the plan to disk as JSON."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan.to_dict(), indent=2, default=str))
    return out_path


def load_storyboard_for_plan(path: Path) -> dict[str, Any]:
    """Load a storyboard.json with a helpful error if the key is missing."""
    if not path.exists():
        raise FileNotFoundError(f"storyboard not found: {path}")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"storyboard is not a JSON object: {path}")
    return data


def summarize_plan(plan: AssembleEffectsPlan) -> str:
    """One-line human summary used by the CLI for stdout."""
    return (
        f"effects plan v{plan.schema_version}: "
        f"{len(plan.transitions)} transitions, "
        f"{len(plan.internal_cuts)} internal cuts, "
        f"{len(plan.cut_points)} total cut points, "
        f"{len(plan.risk_report)} risk notes"
    )