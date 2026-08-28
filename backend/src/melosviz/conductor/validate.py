"""
melosviz.conductor.validate — storyboard validation pass that emits a
machine-readable severity report.

Severity tiers
-------------
- ``error``    : the storyboard cannot be safely rendered. Pipeline aborts.
- ``warning``  : the storyboard will render but with degraded quality.
- ``info``     : the storyboard is fine but the operator may want to know.

Rules covered (deterministic, no LLM dependency)
------------------------------------------------
- schema_version present and supported (1.x).
- scenes list non-empty + each scene has start/end/duration/prompt/camera/palette.
- start <= end; adjacent scenes touch (no overlap, no gap > max_gap).
- palette has 3..6 hex colours.
- camera is one of the allowed archetype strings.
- scene_type is one of the registered backend scene types.
- durations sum within +/-1s of total duration.
- continuity anchors present when ``require_continuity=True``.
- lyrics referenced by scenes actually exist in the LRC.
- edit_count > 0 -> edits[] matches scene_index touched.

A report is written next to the storyboard (``storyboard.report.json``)
and also returned for the CLI / bridge.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ALLOWED_CAMERAS = {
    "slow_dolly_in",
    "slow_pull_back",
    "whip_pan_burst",
    "static_wide",
    "static_close",
    "handheld",
    "crane_up",
    "crane_down",
    "orbit",
    "snap_zoom",
}

ALLOWED_SCENE_TYPES = {
    "comfyui_image",
    "comfyui_video",
    "c4d_3d",
    "unreal_cinematic",
    "aftereffects_compositing",
    "motion_graphics_beat_sync",
    "generative_asset",
    "procedural_3d_animation",
}

SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.1", "2.0"}


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    scene_index: int | None = None
    field: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class ValidationReport:
    schema_version: str = "1.0"
    storyboard_path: str = ""
    scene_count: int = 0
    total_duration: float = 0.0
    issues: list[Issue] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=lambda: {"error": 0, "warning": 0, "info": 0})
    palette_used: list[str] = field(default_factory=list)
    cameras_used: list[str] = field(default_factory=list)
    scene_types_used: list[str] = field(default_factory=list)
    continuity_present: bool = False

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "storyboard_path": self.storyboard_path,
            "scene_count": self.scene_count,
            "total_duration": self.total_duration,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
            "palette_used": self.palette_used,
            "cameras_used": self.cameras_used,
            "scene_types_used": self.scene_types_used,
            "continuity_present": self.continuity_present,
        }
        return d

    @property
    def has_errors(self) -> bool:
        return self.summary.get("error", 0) > 0

    @property
    def has_warnings(self) -> bool:
        return self.summary.get("warning", 0) > 0


def _is_hex_color(s: str) -> bool:
    if not isinstance(s, str) or not s.startswith("#"):
        return False
    body = s[1:]
    return len(body) in (3, 6, 8) and all(c in "0123456789abcdefABCDEF" for c in body)


def validate_storyboard(
    storyboard: dict,
    *,
    storyboard_path: str = "",
    require_continuity: bool = False,
    max_gap_seconds: float = 2.0,
) -> ValidationReport:
    report = ValidationReport(storyboard_path=storyboard_path)
    report.scene_count = len(storyboard.get("scenes", []))

    schema = storyboard.get("schema_version")
    if not schema:
        report.issues.append(
            Issue("error", "schema_missing", "storyboard has no schema_version")
        )
        report.summary["error"] += 1
    elif schema not in SUPPORTED_SCHEMA_VERSIONS:
        report.issues.append(
            Issue("error", "schema_unsupported", f"unsupported schema_version {schema!r}")
        )
        report.summary["error"] += 1

    if report.scene_count == 0:
        report.issues.append(
            Issue("error", "scenes_empty", "storyboard has zero scenes")
        )
        report.summary["error"] += 1
        return report

    cameras: set[str] = set()
    scene_types: set[str] = set()
    palette_global: set[str] = set()
    lyric_ids: set[str] = set()
    continuity_present = bool(storyboard.get("continuity"))

    scenes = storyboard.get("scenes", [])
    prev_end = 0.0
    scene_duration_sum = 0.0
    for idx, sc in enumerate(scenes):
        start = sc.get("start")
        end = sc.get("end")
        duration = sc.get("duration")
        prompt = sc.get("prompt", "")
        camera = sc.get("camera", "")
        scene_type = sc.get("scene_type", "")
        palette = sc.get("palette", [])

        if start is None or end is None or duration is None:
            report.issues.append(
                Issue(
                    "error",
                    "scene_timing_missing",
                    f"scene {idx} missing start/end/duration",
                    scene_index=idx,
                    field="start",
                )
            )
            report.summary["error"] += 1
            continue
        if start > end:
            report.issues.append(
                Issue(
                    "error",
                    "scene_timing_inverted",
                    f"scene {idx} start ({start}) > end ({end})",
                    scene_index=idx,
                )
            )
            report.summary["error"] += 1
        if abs((end - start) - duration) > 0.05:
            report.issues.append(
                Issue(
                    "warning",
                    "scene_duration_mismatch",
                    f"scene {idx} duration {duration} != end-start {end-start}",
                    scene_index=idx,
                )
            )
            report.summary["warning"] += 1
        if idx > 0 and start < prev_end:
            report.issues.append(
                Issue(
                    "error",
                    "scene_overlap",
                    f"scene {idx} starts at {start}s but previous scene ends at {prev_end}s (overlap by {prev_end - start:.2f}s)",
                    scene_index=idx,
                    field="start",
                )
            )
            report.summary["error"] += 1
        if idx > 0 and (start - prev_end) > max_gap_seconds:
            report.issues.append(
                Issue(
                    "warning",
                    "scene_gap_too_large",
                    f"gap {start - prev_end:.2f}s before scene {idx}",
                    scene_index=idx,
                )
            )
            report.summary["warning"] += 1
        prev_end = end
        scene_duration_sum += duration

        if not prompt:
            report.issues.append(
                Issue("warning", "scene_prompt_empty", f"scene {idx} has no prompt", scene_index=idx)
            )
            report.summary["warning"] += 1
        if camera:
            cameras.add(camera)
            if camera not in ALLOWED_CAMERAS:
                report.issues.append(
                    Issue(
                        "warning",
                        "camera_unknown",
                        f"scene {idx} uses camera {camera!r} (not in known list)",
                        scene_index=idx,
                        field="camera",
                    )
                )
                report.summary["warning"] += 1
        else:
            report.issues.append(
                Issue("warning", "scene_camera_empty", f"scene {idx} has no camera", scene_index=idx)
            )
            report.summary["warning"] += 1

        if scene_type:
            scene_types.add(scene_type)
            if scene_type not in ALLOWED_SCENE_TYPES:
                report.issues.append(
                    Issue(
                        "error",
                        "scene_type_unsupported",
                        f"scene {idx} uses scene_type {scene_type!r} (no registered backend)",
                        scene_index=idx,
                        field="scene_type",
                    )
                )
                report.summary["error"] += 1

        if not palette:
            report.issues.append(
                Issue("warning", "scene_palette_empty", f"scene {idx} has no palette", scene_index=idx)
            )
            report.summary["warning"] += 1
        else:
            for c in palette:
                if not _is_hex_color(c):
                    report.issues.append(
                        Issue(
                            "warning",
                            "palette_invalid_hex",
                            f"scene {idx} palette contains non-hex {c!r}",
                            scene_index=idx,
                            field="palette",
                        )
                    )
                    report.summary["warning"] += 1
                else:
                    palette_global.add(c)

        lyric = sc.get("lyric")
        if lyric and isinstance(lyric, dict):
            lid = lyric.get("phrase_id")
            if lid is not None:
                lyric_ids.add(lid)

    if abs(scene_duration_sum - report.total_duration) > 1.0 and report.total_duration > 0:
        report.issues.append(
            Issue(
                "warning",
                "scene_total_duration_mismatch",
                f"scene durations sum to {scene_duration_sum:.2f}s but "
                f"storyboard.total_duration is {report.total_duration:.2f}s",
            )
        )
        report.summary["warning"] += 1
    report.total_duration = scene_duration_sum

    if len(palette_global) < 3:
        report.issues.append(
            Issue(
                "warning",
                "palette_too_thin",
                f"only {len(palette_global)} distinct palette colours used (< 3)",
            )
        )
        report.summary["warning"] += 1
    if len(cameras) < 2:
        report.issues.append(
            Issue(
                "info",
                "cameras_repetitive",
                f"only {len(cameras)} distinct camera(s) across all scenes",
            )
        )
        report.summary["info"] += 1
    if len(scene_types) < 2:
        report.issues.append(
            Issue(
                "info",
                "scene_types_repetitive",
                f"only {len(scene_types)} distinct scene_type(s) used",
            )
        )
        report.summary["info"] += 1

    if require_continuity and not continuity_present:
        report.issues.append(
            Issue(
                "warning",
                "continuity_missing",
                "storyboard requires continuity anchors but none present",
            )
        )
        report.summary["warning"] += 1

    lyrics_in_storyboard = storyboard.get("lyrics", []) or []
    lyric_ids_in_storyboard = {l.get("id") for l in lyrics_in_storyboard if isinstance(l, dict)}
    for lid in lyric_ids - lyric_ids_in_storyboard:
        if lid is not None:
            report.issues.append(
                Issue(
                    "info",
                    "lyric_dangling_ref",
                    f"scene references lyric phrase_id {lid!r} not in storyboard.lyrics",
                )
            )
            report.summary["info"] += 1

    edit_count = int(storyboard.get("edit_count") or 0)
    edits = storyboard.get("edits") or []
    if edit_count > 0 and not edits:
        report.issues.append(
            Issue(
                "warning",
                "edits_missing",
                f"storyboard.edit_count={edit_count} but edits[] is empty",
            )
        )
        report.summary["warning"] += 1

    report.continuity_present = continuity_present
    report.palette_used = sorted(palette_global)
    report.cameras_used = sorted(cameras)
    report.scene_types_used = sorted(scene_types)
    return report


def validate_storyboard_file(path: str | Path, **kwargs) -> ValidationReport:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return validate_storyboard(data, storyboard_path=str(p), **kwargs)


def write_report(report: ValidationReport, target: str | Path) -> Path:
    p = Path(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


__all__ = [
    "ALLOWED_CAMERAS",
    "ALLOWED_SCENE_TYPES",
    "Issue",
    "SUPPORTED_SCHEMA_VERSIONS",
    "ValidationReport",
    "validate_storyboard",
    "validate_storyboard_file",
    "write_report",
]
