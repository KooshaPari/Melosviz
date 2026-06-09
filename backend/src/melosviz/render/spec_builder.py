"""Specification builder for rendering specs."""

from __future__ import annotations

import colorsys
import math
import random
import re
from typing import Any, Dict, List

from melosviz.analysis.models import (
    AnalysisResult,
    CameraState,
    RenderStyle,
    ShotSpec,
    TimelineEvent,
    ThemePreset,
)


class VisualizationSpecBuilder:
    """Construct deterministic visual specs from analysis results."""

    _HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

    @staticmethod
    def _compute_bpm_curve(bpm: float, frame_count: int, fps: int) -> List[float]:
        if bpm <= 0:
            return [0.0] * frame_count
        period = 60.0 / bpm
        return [(float(i) / fps) % period / period for i in range(frame_count)]

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _hex_to_hue(color: str) -> float:
        match = VisualizationSpecBuilder._HEX_COLOR_RE.match(color.strip())
        if not match:
            return 0.0
        hex_value = match.group(1)
        if len(hex_value) == 3:
            hex_value = "".join(c * 2 for c in hex_value)
        red = int(hex_value[0:2], 16) / 255.0
        green = int(hex_value[2:4], 16) / 255.0
        blue = int(hex_value[4:6], 16) / 255.0
        hue, _, _ = colorsys.rgb_to_hsv(red, green, blue)
        return round(hue * 360.0, 4)

    @staticmethod
    def _section_name(time_value: float, bpm: float, duration_sec: float) -> str:
        if duration_sec <= 0:
            return "intro"
        if time_value < duration_sec * 0.18:
            return "intro"
        if time_value < duration_sec * 0.45:
            return "verse"
        if time_value < duration_sec * 0.72:
            return "chorus"
        if time_value < duration_sec * 0.88:
            return "bridge"
        return "outro"

    @staticmethod
    def _scene_boundaries(
        duration_sec: float,
        beat_positions: List[float],
        downbeat_positions: List[float] | None = None,
    ) -> List[float]:
        boundaries = {0.0, round(max(0.0, duration_sec), 4)}
        for ratio in (0.18, 0.45, 0.72, 0.88):
            boundaries.add(round(max(0.0, duration_sec * ratio), 4))
        if downbeat_positions:
            for downbeat_time in downbeat_positions:
                if 0.0 <= downbeat_time <= duration_sec:
                    boundaries.add(round(float(downbeat_time), 4))
        elif beat_positions:
            beat_stride = 4 if len(beat_positions) >= 4 else 1
            for index in range(beat_stride, len(beat_positions), beat_stride):
                beat_time = beat_positions[index]
                if 0.0 <= beat_time <= duration_sec:
                    boundaries.add(round(float(beat_time), 4))
        ordered = sorted(boundaries)
        if duration_sec > 0 and len(ordered) >= 2:
            refined = [ordered[0]]
            for boundary in ordered[1:]:
                previous = refined[-1]
                if boundary - previous > max(2.5, duration_sec / 5.0):
                    midpoint = round((previous + boundary) / 2.0, 4)
                    if midpoint > previous:
                        refined.append(midpoint)
                refined.append(boundary)
            ordered = sorted({round(v, 4) for v in refined if 0.0 <= v <= duration_sec})
        if not ordered or ordered[-1] != round(duration_sec, 4):
            ordered.append(round(duration_sec, 4))
        return ordered

    @staticmethod
    def _camera_for_section(
        section: str, energy: float, intensity: float, beat_phase: float
    ) -> Dict[str, float]:
        zoom_base = {
            "intro": 1.0,
            "verse": 1.03,
            "chorus": 1.08,
            "bridge": 1.04,
            "outro": 0.98,
        }.get(section, 1.0)
        pan_x = math.sin(beat_phase * math.tau) * 0.04 * (0.4 + energy)
        pan_y = math.cos(beat_phase * math.tau * 0.5) * 0.03 * (0.4 + intensity)
        rotation = (beat_phase - 0.5) * 6.0 * (0.2 + intensity)
        return {
            "zoom": round(zoom_base + energy * 0.08 + intensity * 0.04, 4),
            "pan_x": round(pan_x, 4),
            "pan_y": round(pan_y, 4),
            "rotation": round(rotation, 4),
        }

    @staticmethod
    def _shot_type_for_section(section: str, energy: float, beat_phase: float) -> str:
        if section == "intro":
            return "establishing"
        if section == "verse":
            return "performance"
        if section == "chorus":
            return "anthem"
        if section == "bridge":
            return "interlude"
        return "outro"

    @staticmethod
    def _motif_for_shot(section: str, accent: str, beat_phase: float) -> str:
        motif_index = int(beat_phase * 4.0) % 4
        motif_lookup = {
            "intro": ["wide_establish", "silhouette", "street_glide", "crowd_reveal"],
            "verse": ["performance_close", "dancer_pass", "handheld_push", "lens_flare"],
            "chorus": ["crowd_surge", "hero_spin", "neon_burst", "strobe_hit"],
            "bridge": ["slow_turn", "dream_layer", "soft_focus", "split_screen"],
            "outro": ["fade_walkout", "final_pose", "afterglow", "skyline_pullback"],
        }
        motifs = motif_lookup.get(section, ["performance_close"])
        return f"{motifs[motif_index % len(motifs)]}:{accent.lstrip('#').lower()}"

    @staticmethod
    def _movement_for_shot(
        section: str, energy: float, beat_phase: float
    ) -> Dict[str, Any]:
        speed = round(0.25 + energy * 0.9, 4)
        movement_type = (
            "handheld" if section in {"bridge", "verse"} else "crane"
        )
        if section == "chorus":
            movement_type = "orbit"
        elif section == "intro":
            movement_type = "push_in"
        else:
            movement_type = "tracking"
        pattern = round(beat_phase, 4)
        return {
            "speed": speed,
            "type": movement_type,
            "pattern": pattern,
            "beat_lock": round(beat_phase, 4),
        }

    @staticmethod
    def _energy_profile_for_shot(
        start_energy: float, end_energy: float, beat_phase: float
    ) -> List[float]:
        mid_energy = max(
            0.0,
            min(
                1.0,
                (start_energy + end_energy) / 2.0
                + (beat_phase - 0.5) * 0.15,
            ),
        )
        return [
            round(max(0.0, min(1.0, value)), 4)
            for value in (start_energy, mid_energy, end_energy)
        ]

    @staticmethod
    def _transition_for_shot(
        index: int, section: str, energy: float, beat_phase: float
    ) -> Dict[str, Any]:
        if index == 0:
            return {"type": "cold_open", "duration": 0.35, "intensity": 1.0}
        if section == "chorus" and energy >= 0.55:
            return {
                "type": "smash_cut",
                "duration": round(0.08 + energy * 0.05, 3),
                "intensity": round(0.85 + beat_phase * 0.15, 3),
            }
        if section == "chorus":
            return {
                "type": "beat_cut",
                "duration": round(0.12 + energy * 0.07, 3),
                "intensity": round(0.8 + beat_phase * 0.18, 3),
            }
        if section == "bridge":
            return {
                "type": "dissolve",
                "duration": 0.42,
                "intensity": round(0.55 + energy * 0.25, 3),
            }
        if section == "outro":
            return {
                "type": "fade",
                "duration": round(0.28 + energy * 0.12, 3),
                "intensity": round(0.45 + beat_phase * 0.1, 3),
            }
        if energy >= 0.7:
            return {
                "type": "whip_pan",
                "duration": round(0.12 + energy * 0.05, 3),
                "intensity": round(0.75 + beat_phase * 0.15, 3),
            }
        return {
            "type": "match_cut",
            "duration": round(0.18 + energy * 0.12, 3),
            "intensity": round(0.6 + beat_phase * 0.15, 3),
        }

    @staticmethod
    def _overlay_for_shot(
        index: int,
        section: str,
        accent: str,
        bpm: float,
        energy: float,
        intensity: float,
    ) -> List[Dict[str, Any]]:
        overlays = [
            {
                "type": "section_label",
                "text": section.upper(),
                "accent": accent,
            },
            {
                "type": "audio_signature",
                "text": (
                    f"{round(bpm):.0f} BPM" if bpm > 0 else "Tempo free"
                ),
                "accent": accent,
                "energy": round(energy, 4),
                "intensity": round(intensity, 4),
            },
            {
                "type": "motion_hint",
                "text": (
                    f"{section} energy {round(energy * 100):.0f}%"
                ),
                "accent": accent,
            },
        ]
        if index == 0:
            overlays.insert(
                0,
                {
                    "type": "title_card",
                    "text": "Melosviz Scene",
                    "accent": accent,
                },
            )
        return overlays

    @staticmethod
    def _palette_shift_for_shot(
        accent: str,
        next_accent: str,
        start_time: float,
        mid_time: float,
        energy: float,
        intensity: float,
    ) -> List[Dict[str, Any]]:
        return [
            {
                "time": round(start_time, 4),
                "color": accent,
                "energy": round(energy, 4),
                "intensity": round(intensity, 4),
            },
            {
                "time": round(mid_time, 4),
                "color": next_accent,
                "energy": round(
                    max(0.0, min(1.0, energy * 0.85 + 0.1)), 4
                ),
                "intensity": round(
                    max(0.0, min(1.0, intensity * 0.9 + 0.05)), 4
                ),
            },
        ]

    @staticmethod
    def _timeline_sort_key(event: Dict[str, Any]) -> tuple[float, int, str]:
        priority = {
            "shot_change": 0,
            "section_start": 1,
            "camera_move": 2,
            "palette_shift": 3,
            "downbeat": 4,
            "beat": 5,
            "onset": 6,
        }.get(event.get("type", ""), 9)
        return (float(event["time"]), priority, event.get("type", ""))

    def build_spec(
        self,
        analysis: AnalysisResult,
        style: RenderStyle,
        preset: ThemePreset,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        duration_sec: float = 0.0,
        seed: int = 0,
    ) -> dict[str, Any]:
        rng = random.Random(seed)
        palette = list(style.colors) if style.colors else list(preset.colors)
        if not palette:
            palette = [preset.glow_color]
        frame_count = max(1, int(math.floor(duration_sec * fps)))
        bpm = analysis.bpm.bpm if analysis.bpm else 120.0
        beat_positions = (
            list(analysis.bpm.beat_positions) if analysis.bpm else []
        )
        downbeats = (
            list(analysis.bpm.downbeat_positions) if analysis.bpm else []
        )
        onsets = (
            list(analysis.bpm.onset_positions) if analysis.bpm else []
        )
        waveform = analysis.waveform.samples if analysis.waveform else []
        dominant_bins = (
            analysis.frequency.dominant_bins if analysis.frequency else {}
        )
        dominant_items = list(dominant_bins.items())
        bpm_curve = self._compute_bpm_curve(float(bpm), frame_count, fps)
        layers = [
            {
                "type": "background",
                "visible": True,
                "opacity": 1.0,
                "transform": {
                    "scale": 1.0,
                    "rotation": 0.0,
                    "offset": [0.0, 0.0],
                },
            },
            {
                "type": "shapes",
                "visible": True,
                "opacity": 0.9,
                "transform": {
                    "scale": 1.0 + rng.uniform(0.5, 1.0) * 0.05,
                    "rotation": rng.uniform(-10.0, 10.0),
                    "offset": [
                        rng.uniform(-0.2, 0.2),
                        rng.uniform(-0.2, 0.2),
                    ],
                },
            },
            {
                "type": "particles",
                "visible": True,
                "opacity": 0.8,
                "transform": {
                    "scale": 1.0,
                    "rotation": 0.0,
                    "offset": [0.0, 0.0],
                },
            },
            {
                "type": "text",
                "visible": True,
                "opacity": 0.75,
                "transform": {
                    "scale": 0.75,
                    "rotation": 0.0,
                    "offset": [0.0, 0.9],
                },
            },
        ]
        timeline: List[Dict[str, Any]] = []
        shots: List[Dict[str, Any]] = []
        scene_boundaries = self._scene_boundaries(
            duration_sec, beat_positions, downbeats
        )
        waveform_length = len(waveform)
        for idx, start_time in enumerate(scene_boundaries[:-1]):
            end_time = scene_boundaries[idx + 1]
            mid_time = (start_time + end_time) / 2.0
            section = self._section_name(mid_time, float(bpm), duration_sec)
            next_mid_time = (
                (end_time + scene_boundaries[idx + 2]) / 2.0
                if idx + 2 < len(scene_boundaries)
                else duration_sec
            )
            next_section = self._section_name(
                next_mid_time, float(bpm), duration_sec
            )
            beat_phase = (
                (mid_time * float(bpm) / 60.0) % 1.0 if bpm > 0 else 0.0
            )
            waveform_index = (
                min(waveform_length - 1, int(mid_time * fps))
                if waveform_length
                else 0
            )
            energy_sample = (
                waveform[waveform_index] if waveform_length else 0.0
            )
            energy = self._clamp01(
                abs(float(energy_sample))
                + min(0.25, len(beat_positions) / max(1, frame_count * 2.0))
            )
            intensity = self._clamp01(
                0.32
                + energy * 0.42
                + beat_phase * 0.18
                + (0.1 if section == "chorus" else 0.0)
            )
            camera = self._camera_for_section(
                section, energy, intensity, beat_phase
            )
            accent = palette[idx % len(palette)]
            next_accent = (
                palette[(idx + 1) % len(palette)]
                if len(palette) > 1
                else accent
            )
            shot_type = self._shot_type_for_section(
                section, energy, beat_phase
            )
            motif = self._motif_for_shot(section, accent, beat_phase)
            movement = self._movement_for_shot(
                section, energy, beat_phase
            )
            energy_profile = self._energy_profile_for_shot(
                energy,
                self._clamp01(energy * 0.9 + intensity * 0.1),
                beat_phase,
            )
            cut_style = self._transition_for_shot(
                idx, section, energy, beat_phase
            )["type"]
            shots.append(
                {
                    "id": f"shot-{idx + 1}",
                    "section": section,
                    "start_time": round(start_time, 4),
                    "end_time": round(end_time, 4),
                    "shot_type": shot_type,
                    "motif": motif,
                    "beat_anchor": round(beat_phase, 4),
                    "energy_profile": energy_profile,
                    "movement": movement,
                    "cut_style": cut_style,
                    "camera": camera,
                    "transition_in": self._transition_for_shot(
                        idx, section, energy, beat_phase
                    ),
                    "transition_out": self._transition_for_shot(
                        idx + 1, next_section, energy, beat_phase
                    ),
                    "overlay": self._overlay_for_shot(
                        idx, section, accent, float(bpm), energy, intensity
                    ),
                    "palette_shift": self._palette_shift_for_shot(
                        accent, next_accent, start_time, mid_time, energy, intensity
                    ),
                }
            )
            timeline.append(
                {
                    "time": round(start_time, 4),
                    "type": "shot_change",
                    "data": {
                        "shot_id": f"shot-{idx + 1}",
                        "section": section,
                        "shot_type": shot_type,
                        "motif": motif,
                        "cut_style": cut_style,
                    },
                }
            )
            timeline.append(
                {
                    "time": round(start_time, 4),
                    "type": "section_start",
                    "data": {
                        "section": section,
                        "shot_type": shot_type,
                    },
                }
            )
            if idx > 0:
                timeline.append(
                    {
                        "time": round(start_time, 4),
                        "type": "camera_move",
                        "data": {
                            "shot_id": f"shot-{idx + 1}",
                            "camera": camera,
                            "movement": movement,
                        },
                    }
                )
            timeline.append(
                {
                    "time": round(mid_time, 4),
                    "type": "palette_shift",
                    "data": {
                        "accent": accent,
                        "next_accent": next_accent,
                        "energy": round(energy, 4),
                        "intensity": round(intensity, 4),
                        "motif": motif,
                    },
                }
            )
        for beat_time in beat_positions:
            if 0.0 <= beat_time <= duration_sec:
                timeline.append(
                    {
                        "time": round(float(beat_time), 4),
                        "type": "beat",
                        "data": {"strength": 1.0},
                    }
                )
        for downbeat_time in downbeats:
            if 0.0 <= downbeat_time <= duration_sec:
                timeline.append(
                    {
                        "time": round(float(downbeat_time), 4),
                        "type": "downbeat",
                        "data": {"strength": 1.0},
                    }
                )
        for onset_time in onsets:
            if 0.0 <= onset_time <= duration_sec:
                timeline.append(
                    {
                        "time": round(float(onset_time), 4),
                        "type": "onset",
                        "data": {"strength": 0.75},
                    }
                )
        keyframes: List[Dict[str, Any]] = []
        for frame in range(frame_count):
            time = frame / float(fps)
            index = min(len(waveform) - 1, frame) if waveform else 0
            amplitude = float(waveform[index]) if waveform else 0.0
            color_index = int((frame + seed) % len(palette))
            color_shift = palette[color_index]
            bpm_sync = round(bpm_curve[frame], 4)
            energy = self._clamp01(abs(amplitude))
            intensity = self._clamp01(
                0.35 + energy * 0.5 + bpm_sync * 0.3
            )
            section = self._section_name(time, float(bpm), duration_sec)
            keyframes.append(
                {
                    "time": round(time, 4),
                    "bpm_sync": bpm_sync,
                    "amplitude": amplitude,
                    "frequency": {"dominant": dominant_items[:3]},
                    "color_shift": color_shift,
                    "energy": energy,
                    "hue": self._hex_to_hue(color_shift),
                    "intensity": intensity,
                    "section": section,
                    "camera": self._camera_for_section(
                        section, energy, intensity, bpm_sync
                    ),
                }
            )
        timeline.sort(key=self._timeline_sort_key)
        return {
            "metadata": {
                "width": width,
                "height": height,
                "fps": fps,
                "duration": round(duration_sec, 4),
                "seed": seed,
                "style": style.template,
                "geometry": preset.geometry,
            },
            "palette": palette,
            "layers": layers,
            "shots": [
                ShotSpec(**shot) for shot in shots
            ],
            "timeline": [
                TimelineEvent(**event) for event in timeline
            ],
            "keyframes": keyframes,
            "analysis": {
                "duration_seconds": analysis.duration_seconds,
                "sample_rate": analysis.sample_rate,
                "channels": analysis.channels,
                "analysis": analysis.analysis.value,
                "has_bpm": analysis.bpm is not None,
                "has_waveform": analysis.waveform is not None,
                "has_frequency": analysis.frequency is not None,
            },
        }
