"""Narrative arc composer — anti-repetition scene assignment.

Given a list of :class:`~melosviz.analysis.models.SceneSegment` dicts
(from RenderSpec v2 ``scene_segments``) and MIR trajectory data, the composer
assigns a **varied** ``scene_type``, ``material``, and ``camera_language`` to
each segment so that:

1. **Novelty constraint** — no two adjacent segments share the same
   (scene_type, material) pair.
2. **Intensity arc** — assignments follow a build → drop → breakdown
   intensity curve derived from the segment energy_mean values; the assigned
   visual complexity tracks the arc.
3. **Determinism** — given the same ``seed``, the same input always produces
   the same plan (reproducible renders, test-friendly).

Usage::

    from melosviz.compose.narrator import NarrativeComposer

    composer = NarrativeComposer(seed=42)
    plan = composer.assign(scene_segments, mir)
    # plan[i] = {"index": i, "scene_type": "...", "material": "...",
    #             "camera_language": "...", "intensity": 0.0..1.0}

Design
------
* Scene-type pool and material pool are fixed palettes; callers may override.
* The camera-language vocabulary maps intensity bands to shot archetypes.
* The novelty constraint is enforced greedily: if the preferred assignment
  repeats the previous (scene_type, material), cycle to the next candidate
  in the shuffled pool.
* The intensity arc is computed from a smoothed energy curve (EMA, α=0.3)
  so brief loud transients do not dominate the structural shape.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

__all__ = [
    "NarrativeComposer",
    "SegmentAssignment",
    "DEFAULT_SCENE_TYPES",
    "DEFAULT_MATERIALS",
    "CAMERA_LANGUAGE_MAP",
]

# ---------------------------------------------------------------------------
# Default palettes
# ---------------------------------------------------------------------------

#: Scene-type pool that the composer draws from (registered in ADAPTER_REGISTRY).
DEFAULT_SCENE_TYPES: list[str] = [
    "procedural_3d_animation",
    "motion_graphics_beat_sync",
    "generative_asset",
    "live_stage",
    "video_export",
]

#: Material palette — visual look families.
DEFAULT_MATERIALS: list[str] = [
    "neon_glow",
    "matte_dark",
    "chrome_reflect",
    "frosted_glass",
    "organic_distort",
    "wireframe_pulse",
    "gradient_wash",
    "grain_film",
]

#: Maps intensity quartile (0–3) → camera-language archetype.
CAMERA_LANGUAGE_MAP: dict[int, str] = {
    0: "slow_reveal",      # intro / outro — wide, patient
    1: "steady_cam",       # verse / bridge — grounded motion
    2: "handheld_push",    # build / pre-chorus — forward energy
    3: "cut_frenzy",       # drop / chorus — rapid intercutting
}


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass
class SegmentAssignment:
    """Composer output for one scene segment."""

    index: int
    label: str
    start: float
    end: float
    scene_type: str
    material: str
    camera_language: str
    intensity: float  # normalised [0, 1] — position in arc

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "scene_type": self.scene_type,
            "material": self.material,
            "camera_language": self.camera_language,
            "intensity": round(self.intensity, 4),
        }


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------

class NarrativeComposer:
    """Deterministic, seed-stable narrative arc composer.

    Args:
        seed: RNG seed for reproducible output.
        scene_types: Override the default scene-type pool.
        materials: Override the default material pool.
        camera_map: Override the camera-language intensity map.
        ema_alpha: Smoothing factor for the energy EMA (0 < alpha ≤ 1).
            Lower = more smoothing.
    """

    def __init__(
        self,
        seed: int = 0,
        scene_types: list[str] | None = None,
        materials: list[str] | None = None,
        camera_map: dict[int, str] | None = None,
        ema_alpha: float = 0.3,
    ) -> None:
        self._seed = seed
        self._scene_types = list(scene_types or DEFAULT_SCENE_TYPES)
        self._materials = list(materials or DEFAULT_MATERIALS)
        self._camera_map = dict(camera_map or CAMERA_LANGUAGE_MAP)
        self._ema_alpha = float(ema_alpha)
        if not (0 < self._ema_alpha <= 1.0):
            raise ValueError(f"ema_alpha must be in (0, 1]; got {self._ema_alpha}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assign(
        self,
        scene_segments: list[dict[str, Any]],
        mir: dict[str, Any] | None = None,
    ) -> list[SegmentAssignment]:
        """Assign visual properties to each segment.

        Args:
            scene_segments: List of scene-segment dicts from RenderSpec v2.
                Each must have ``index``, ``label``, ``start``, ``end``,
                and optionally ``energy_mean``.
            mir: MIR summary dict (RenderSpec v2 ``mir`` field).  Used to
                supplement per-segment energy when ``energy_mean`` is zero.

        Returns:
            List of :class:`SegmentAssignment`, one per segment, in order.

        Raises:
            ValueError: When ``scene_segments`` is empty.
        """
        if not scene_segments:
            raise ValueError("NarrativeComposer.assign: scene_segments is empty")

        rng = random.Random(self._seed)

        # ---- Resolve intensity arc ----------------------------------------
        intensities = self._compute_intensity_arc(scene_segments, mir or {})

        # ---- Shuffle palettes (seeded) -----------------------------------
        scene_pool = list(self._scene_types)
        material_pool = list(self._materials)
        rng.shuffle(scene_pool)
        rng.shuffle(material_pool)

        # ---- Assign per-segment (novelty constraint) ---------------------
        assignments: list[SegmentAssignment] = []
        prev_pair: tuple[str, str] | None = None

        for seg, intensity in zip(scene_segments, intensities, strict=True):
            idx = int(seg.get("index", 0))
            label = str(seg.get("label", "unknown"))
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))

            scene_type, material = self._pick_varied(
                rng, scene_pool, material_pool, prev_pair
            )
            camera_language = self._camera_language(intensity)

            assignment = SegmentAssignment(
                index=idx,
                label=label,
                start=start,
                end=end,
                scene_type=scene_type,
                material=material,
                camera_language=camera_language,
                intensity=intensity,
            )
            assignments.append(assignment)
            prev_pair = (scene_type, material)

        return assignments

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_intensity_arc(
        self,
        segs: list[dict[str, Any]],
        mir: dict[str, Any],
    ) -> list[float]:
        """Return per-segment normalised intensity in [0, 1].

        Pulls ``energy_mean`` from each segment; falls back to a per-second
        sample from ``mir.energy_trajectory`` interpolated at the segment
        midpoint.  Applies an EMA to smooth transients, then normalises to
        [0, 1] over the full track.
        """
        energy_traj: list[float] = list(mir.get("energy_trajectory") or [])

        raw: list[float] = []
        for seg in segs:
            e = float(seg.get("energy_mean") or 0.0)
            if e == 0.0 and energy_traj:
                # Interpolate from per-second trajectory at midpoint
                mid = (float(seg.get("start", 0.0)) + float(seg.get("end", 0.0))) / 2.0
                idx = min(int(math.floor(mid)), len(energy_traj) - 1)
                e = float(energy_traj[idx])
            raw.append(e)

        # EMA smoothing
        smoothed: list[float] = []
        ema = raw[0] if raw else 0.0
        for v in raw:
            ema = self._ema_alpha * v + (1.0 - self._ema_alpha) * ema
            smoothed.append(ema)

        # Normalise to [0, 1]
        lo, hi = min(smoothed), max(smoothed)
        if hi == lo:
            return [0.5] * len(smoothed)
        return [(v - lo) / (hi - lo) for v in smoothed]

    def _pick_varied(
        self,
        rng: random.Random,
        scene_pool: list[str],
        material_pool: list[str],
        prev_pair: tuple[str, str] | None,
    ) -> tuple[str, str]:
        """Pick a (scene_type, material) pair that differs from prev_pair.

        Tries up to len(scene_pool) * len(material_pool) candidates before
        allowing a repeat (guarantees termination for tiny pools).
        """
        n_scene = len(scene_pool)
        n_mat = len(material_pool)
        max_tries = n_scene * n_mat

        scene_offset = rng.randint(0, n_scene - 1)
        mat_offset = rng.randint(0, n_mat - 1)

        for attempt in range(max_tries):
            scene = scene_pool[(scene_offset + attempt) % n_scene]
            mat = material_pool[(mat_offset + attempt // n_scene) % n_mat]
            if prev_pair is None or (scene, mat) != prev_pair:
                return scene, mat

        # Fallback: rotate scene type only (always differs from prev material)
        scene = scene_pool[(scene_offset + 1) % n_scene]
        mat = material_pool[mat_offset % n_mat]
        return scene, mat

    def _camera_language(self, intensity: float) -> str:
        """Map normalised intensity to a camera-language archetype."""
        quartile = min(3, int(intensity * 4))
        return self._camera_map[quartile]
