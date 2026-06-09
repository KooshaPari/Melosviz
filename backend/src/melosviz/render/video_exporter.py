"""Video export helpers for music-video style previews."""

from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
    "FFMpegNotFoundError",
    "RenderExportError",
    "export_music_video",
]


class RenderExportError(RuntimeError):
    """Raised when video rendering or muxing fails."""


class FFMpegNotFoundError(RenderExportError):
    """Raised when ffmpeg binary cannot be located."""


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _hex_to_bgr(color: str) -> tuple[int, int, int]:
    clean = color.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(channel * 2 for channel in clean)
    if len(clean) != 6:
        return (255, 255, 255)
    red = int(clean[0:2], 16)
    green = int(clean[2:4], 16)
    blue = int(clean[4:6], 16)
    return (blue, green, red)


def _mix_color(
    first: tuple[int, int, int], second: tuple[int, int, int], amount: float
) -> tuple[int, int, int]:
    ratio = _clamp(amount, 0.0, 1.0)
    return tuple(
        int(round(a + (b - a) * ratio)) for a, b in zip(first, second)
    )


def _frame_keyframe_at_time(
    keyframes: list[dict[str, Any]], time_sec: float, fps: int
) -> dict[str, Any]:
    if not keyframes:
        return {
            "energy": 0.5,
            "hue": 190.0,
            "intensity": 0.6,
            "color_shift": "#00f5ff",
        }
    index = min(len(keyframes) - 1, max(0, int(time_sec * fps)))
    if 0 <= index < len(keyframes):
        return keyframes[index]
    return keyframes[-1]


def _shot_at_time(
    shots: list[dict[str, Any]], time_sec: float
) -> dict[str, Any] | None:
    if not shots:
        return None
    for shot in shots:
        if hasattr(shot, "model_dump"):
            start = float(shot.start_time)
            end = float(shot.end_time)
        else:
            start = float(shot.get("start_time", 0.0))
            end = float(shot.get("end_time", 0.0))
        if start <= time_sec < end:
            return shot
    return shots[-1]


def _shot_transition(
    shot: dict[str, Any] | None, time_sec: float
) -> tuple[str, float]:
    if not shot:
        return ("match_cut", 0.0)
    if hasattr(shot, "model_dump"):
        start_time = float(shot.start_time)
        end_time = float(shot.end_time)
        transition_in = shot.transition_in
        transition_out = shot.transition_out
        cut_style = shot.cut_style
    else:
        start_time = float(shot.get("start_time", 0.0))
        end_time = float(shot.get("end_time", 0.0))
        transition_in = shot.get("transition_in")
        transition_out = shot.get("transition_out")
        cut_style = shot.get("cut_style", "match_cut")
    duration = max(end_time - start_time, 0.001)
    progress = (time_sec - start_time) / duration
    if progress < 0.18:
        phase = transition_in
    elif progress > 0.82:
        phase = transition_out
    else:
        phase = None
    raw = str(
        (phase if phase else {}).get("type")
        or (phase if phase else {}).get("kind")
        or cut_style
        or "match_cut"
    ).lower()
    intensity = float(
        (phase if phase else {}).get("intensity")
        or (phase if phase else {}).get("strength")
        or 0.0
    )
    if "whip" in raw:
        return ("whip_pan", intensity if intensity else 0.88)
    if "smash" in raw or "snap" in raw:
        return ("smash_cut", intensity if intensity else 0.92)
    if "fade" in raw:
        return ("fade", intensity if intensity else 0.7)
    if "dissolve" in raw or "drift" in raw:
        return ("dissolve", intensity if intensity else 0.62)
    if "hard" in raw or "cut" in raw:
        return ("hard_cut", intensity if intensity else 0.8)
    return ("match_cut", intensity if intensity else 0.45)


def _draw_text_box(
    frame: np.ndarray,
    lines: list[str],
    origin: tuple[int, int],
    accent: tuple[int, int, int],
) -> None:
    x, y = origin
    padding_x = 18
    padding_y = 14
    line_height = 28
    width = 0
    for line in lines:
        (line_width, _) = cv2.getTextSize(
            line, cv2.FONT_HERSHEY_SIMPLEX, 0.66, 2
        )[0]
        width = max(width, line_width)
    height = padding_y * 2 + line_height * len(lines)
    cv2.rectangle(
        frame,
        (x, y),
        (x + width + padding_x * 2, y + height),
        (8, 8, 8),
        -1,
    )
    cv2.rectangle(
        frame,
        (x, y),
        (x + width + padding_x * 2, y + height),
        accent,
        2,
    )
    for index, line in enumerate(lines):
        baseline_y = y + padding_y + (index + 1) * line_height - 6
        cv2.putText(
            frame,
            line,
            (x + padding_x, baseline_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.66,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )


def _render_frame(
    width: int,
    height: int,
    time_sec: float,
    duration_sec: float,
    keyframe: dict[str, Any],
    shot: dict[str, Any] | None,
    palette: list[str],
) -> np.ndarray:
    base = _hex_to_bgr(
        palette[0] if palette else "#00f5ff"
    )
    secondary = _hex_to_bgr(
        palette[1]
        if len(palette) > 1
        else palette[0]
        if palette
        else "#ff2fd5"
    )
    tertiary = _hex_to_bgr(
        palette[2]
        if len(palette) > 2
        else palette[1]
        if len(palette) > 1
        else palette[0]
        if palette
        else "#8a75ff"
    )
    accent = _hex_to_bgr(
        str(
            keyframe.get("color_shift")
            if keyframe and keyframe.get("color_shift")
            else palette[0]
            if palette
            else "#00f5ff"
        )
    )
    energy = _clamp(
        float(keyframe.get("energy", 0.5)), 0.0, 1.0
    )
    intensity = _clamp(
        float(keyframe.get("intensity", 0.6)), 0.0, 1.0
    )
    hue = _clamp(
        float(keyframe.get("hue", 190.0)) / 360.0, 0.0, 1.0
    )
    beat_sync = _clamp(
        float(keyframe.get("bpm_sync", 0.0)), 0.0, 1.0
    )
    bg = _mix_color(base, secondary, 0.25 + energy * 0.3)
    bg = _mix_color(bg, tertiary, 0.12 + intensity * 0.2)
    bg = _mix_color(bg, accent, 0.08 + hue * 0.12)
    frame = np.full(
        (height, width, 3), bg, dtype=np.uint8
    )
    overlay = frame.copy()
    if shot and hasattr(shot, "model_dump"):
        if hasattr(shot.camera, "model_dump"):
            camera = shot.camera.model_dump()
        else:
            camera = shot.camera
        if isinstance(shot.movement, dict):
            movement = shot.movement
        elif hasattr(shot.movement, "model_dump"):
            movement = shot.movement.model_dump()
        else:
            movement = {}
        section = shot.section
        shot_type = shot.shot_type
        motif = shot.motif
        cut_style = shot.cut_style
        beat_anchor = shot.beat_anchor
    else:
        camera = shot.get("camera", {}) if shot else {}
        movement = shot.get("movement", {}) if shot else {}
        section = shot.get("section", "intro") if shot else "intro"
        shot_type = shot.get("shot_type", "performance") if shot else "performance"
        motif = shot.get("motif", "motion") if shot else "motion"
        cut_style = shot.get("cut_style", "match_cut") if shot else "match_cut"
        beat_anchor = shot.get("beat_anchor", 0.5) if shot else 0.5
    movement_speed = float(
        (movement if isinstance(movement, dict) else {}).get("speed", 0.55)
        if isinstance(movement, dict)
        else getattr(movement, "speed", 0.55)
    )
    beat_lock = float(
        (movement if isinstance(movement, dict) else {}).get("beat_lock", 0.5)
        if isinstance(movement, dict)
        else getattr(movement, "beat_lock", 0.5)
    )
    camera_zoom = float(
        (camera if isinstance(camera, dict) else {}).get("zoom", 1.0)
        if isinstance(camera, dict)
        else getattr(camera, "zoom", 1.0)
    )
    pan_x = float(
        (camera if isinstance(camera, dict) else {}).get("pan_x", 0.0)
        if isinstance(camera, dict)
        else getattr(camera, "pan_x", 0.0)
    )
    pan_y = float(
        (camera if isinstance(camera, dict) else {}).get("pan_y", 0.0)
        if isinstance(camera, dict)
        else getattr(camera, "pan_y", 0.0)
    )
    rotation = float(
        (camera if isinstance(camera, dict) else {}).get("rotation", 0.0)
        if isinstance(camera, dict)
        else getattr(camera, "rotation", 0.0)
    )
    movement_type = str(
        (movement if isinstance(movement, dict) else {}).get("type", "crane")
        if isinstance(movement, dict)
        else getattr(movement, "type", "crane")
    )
    transition_kind, transition_strength = _shot_transition(shot, time_sec)
    transition_strength = _clamp(
        float(transition_strength), 0.0, 1.0
    )
    transition_phase = (
        math.sin(time_sec * 10.0 + transition_strength * 2.0) * 0.5 + 0.5
    )
    if transition_kind == "fade":
        overlay[:, :] = _mix_color(
            bg, (0, 0, 0), 0.35 + transition_strength * 0.35
        )
    elif transition_kind == "dissolve":
        overlay[:, :] = _mix_color(
            bg, accent, 0.08 + transition_strength * 0.1
        )
    elif transition_kind == "smash_cut":
        overlay[:, :] = _mix_color(
            bg, accent, 0.15 + transition_strength * 0.14
        )
    elif transition_kind == "whip_pan":
        overlay[:, :] = _mix_color(
            bg, secondary, 0.12 + transition_strength * 0.08
        )
    center_x = int(
        width * 0.5
        + pan_x * width * 0.18
        + math.sin(time_sec * 0.8)
        * width
        * 0.025
        * transition_strength
    )
    center_y = int(
        height * 0.5
        + pan_y * height * 0.14
        + math.cos(time_sec * 0.9)
        * height
        * 0.02
        * transition_strength
    )
    center = (center_x, center_y)
    max_radius = int(
        min(width, height)
        * (0.14 + intensity * 0.15)
        * camera_zoom
    )
    for ring_index in range(4):
        radius = int(
            max_radius
            * (
                0.45
                + ring_index * 0.22
                + math.sin(time_sec * 1.5 + ring_index * 0.3)
                * 0.03
            )
        )
        ring_color = _mix_color(
            accent, tertiary, ring_index / 4.0
        )
        ring_color = _mix_color(
            ring_color,
            secondary,
            0.18 + transition_phase * 0.12,
        )
        cv2.circle(
            overlay,
            center,
            max(8, radius),
            ring_color,
            2,
            cv2.LINE_AA,
        )
    bar_count = 18
    for index in range(bar_count):
        angle = (
            index / bar_count * math.tau
            + time_sec * (0.7 + movement_speed * 0.45)
            + rotation * 0.02
        )
        length = int(
            max_radius
            * (
                0.75
                + 0.3
                * math.sin(
                    time_sec * 1.8
                    + index * 0.5
                    + beat_sync * math.tau
                )
            )
        )
        end_x = int(center_x + math.cos(angle) * length)
        end_y = int(center_y + math.sin(angle) * length)
        line_color = _mix_color(
            accent,
            secondary,
            index / max(1, bar_count - 1),
        )
        line_color = _mix_color(
            line_color, tertiary, transition_strength * 0.2
        )
        cv2.line(
            overlay,
            center,
            (end_x, end_y),
            line_color,
            2 if transition_kind != "fade" else 1,
            cv2.LINE_AA,
        )
    burst_size = int(
        max_radius
        * (0.45 + intensity * 0.35 + transition_strength * 0.08)
    )
    cv2.circle(
        overlay, center, burst_size, accent, 2, cv2.LINE_AA
    )
    cv2.circle(
        overlay,
        center,
        max(6, int(burst_size * 0.63)),
        secondary,
        2,
        cv2.LINE_AA,
    )
    cv2.circle(
        overlay,
        center,
        max(4, int(burst_size * 0.3)),
        tertiary,
        1,
        cv2.LINE_AA,
    )
    beat_bars = 16
    bar_width = max(10, int(width * 0.03))
    gap = max(4, int(width * 0.006))
    total_width = beat_bars * bar_width + (beat_bars - 1) * gap
    start_x = max(24, int((width - total_width) / 2))
    base_y = height - 58
    for index in range(beat_bars):
        phase = (
            time_sec * (2.0 + movement_speed * 0.5)
            + index * 0.5
        )
        amplitude = (
            0.16
            + energy * 0.48
            + intensity * 0.16
            + math.sin(phase) * 0.1
        )
        bar_height = int(
            height * 0.11 * _clamp(amplitude, 0.08, 1.0)
        )
        x1 = start_x + index * (bar_width + gap)
        x2 = x1 + bar_width
        bar_color = _mix_color(
            secondary,
            accent,
            index / max(1, beat_bars - 1),
        )
        cv2.rectangle(
            overlay,
            (x1, base_y - bar_height),
            (x2, base_y),
            bar_color,
            -1,
        )
    shot_section = str(section).upper()
    cut_style_str = str(cut_style).replace("_", " ")
    timeline = f"{time_sec:05.1f}s / {duration_sec:05.1f}s"
    _draw_text_box(
        overlay,
        [
            f"{shot_section} - {shot_type} - {movement_type}",
            f"{motif}",
            f"{cut_style_str} - beat {beat_anchor:.2f}",
            timeline,
        ],
        (32, 32),
        accent,
    )
    progress = (
        0.0
        if duration_sec <= 0
        else _clamp(time_sec / duration_sec, 0.0, 1.0)
    )
    cv2.rectangle(
        overlay,
        (32, height - 34),
        (width - 32, height - 24),
        (255, 255, 255),
        1,
    )
    cv2.rectangle(
        overlay,
        (32, height - 34),
        (
            32 + int((width - 64) * progress),
            height - 24,
        ),
        accent,
        -1,
    )
    if transition_kind == "whip_pan":
        cv2.line(
            overlay,
            (0, int(height * 0.15)),
            (width, int(height * 0.42)),
            tertiary,
            2,
            cv2.LINE_AA,
        )
    elif transition_kind == "smash_cut":
        cv2.line(
            overlay,
            (int(width * 0.1), 0),
            (int(width * 0.92), height),
            accent,
            3,
            cv2.LINE_AA,
        )
    elif transition_kind == "dissolve":
        cv2.circle(
            overlay,
            (
                int(width * 0.82),
                int(height * 0.2),
            ),
            int(min(width, height) * 0.08),
            tertiary,
            2,
            cv2.LINE_AA,
        )
    alpha = 0.78 if transition_kind in {"dissolve", "fade"} else 0.66
    cv2.addWeighted(
        overlay, alpha, frame, 1.0 - alpha, 0.0, frame
    )
    return frame


def _resolve_ffmpeg_binary() -> str:
    candidates = [
        os.environ.get("MELOSVIZ_FFMPEG_BIN"),
        "/opt/homebrew/Cellar/ffmpeg-full/8.1.1/bin/ffmpeg",
        "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
        shutil.which("ffmpeg"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if not candidate_path.exists():
            continue
        try:
            probe = subprocess.run(
                [candidate, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if probe.returncode == 0:
                logger.info("ffmpeg resolved: %s", candidate)
                return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    raise FFMpegNotFoundError(
        "Unable to locate a working ffmpeg binary for video export. "
        "Set MELOSVIZ_FFMPEG_BIN environment variable or install ffmpeg."
    )


def _validate_ffmpeg_available() -> bool:
    try:
        _resolve_ffmpeg_binary()
        return True
    except FFMpegNotFoundError:
        return False


def export_music_video(
    spec: dict[str, Any],
    audio_path: str | Path,
    output_dir: str | Path,
    export_format: str = "mp4",
) -> tuple[Path, float, float, int]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not _validate_ffmpeg_available():
        raise FFMpegNotFoundError(
            "ffmpeg not available. Video export requires ffmpeg to be installed."
        )
    metadata = (
        spec.get("metadata", {})
        if isinstance(spec, dict)
        else {}
    )
    width = int(metadata.get("width", 1920))
    height = int(metadata.get("height", 1080))
    fps = max(1, int(round(metadata.get("fps", 30))))
    duration_sec = float(metadata.get("duration", 30.0))
    duration_sec = max(duration_sec, 0.001)
    palette = [
        str(color)
        for color in spec.get(
            "palette", ["#00f5ff", "#ff2fd5", "#8a75ff"]
        )
    ]
    shots = list(spec.get("shots", []))
    keyframes = list(spec.get("keyframes", []))
    output_ext = "webm" if export_format.lower() == "webm" else "mp4"
    output_video = output_dir / f"melosviz-export.{output_ext}"
    if export_format.lower() == "webm":
        video_codec = "libvpx-vp9"
        audio_codec = "libopus"
    else:
        video_codec = "libx264"
        audio_codec = "aac"
    total_frames = max(1, int(round(duration_sec * fps)))
    render_start = time.monotonic()
    ffmpeg = _resolve_ffmpeg_binary()
    mux_start = time.monotonic()
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "bgr24",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        "-i",
        str(audio_path),
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        video_codec,
        "-c:a",
        audio_codec,
        "-b:a",
        "192k",
    ]
    if export_format.lower() == "mp4":
        cmd.extend(
            [
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+dash+disable_chaining",
            ]
        )
    else:
        cmd.extend(["-pix_fmt", "yuv420p"])
    cmd.append(str(output_video))
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        try:
            for frame_index in range(total_frames):
                time_sec = frame_index / float(fps)
                keyframe = _frame_keyframe_at_time(
                    keyframes, time_sec, fps
                )
                shot = _shot_at_time(shots, time_sec)
                frame = _render_frame(
                    width=width,
                    height=height,
                    time_sec=time_sec,
                    duration_sec=duration_sec,
                    keyframe=keyframe,
                    shot=shot,
                    palette=palette,
                )
                proc.stdin.write(frame.tobytes())
        except BrokenPipeError:
            pass
        proc.stdin.close()
        render_duration = time.monotonic() - render_start
        completed = proc.wait(timeout=300)
        mux_duration = time.monotonic() - mux_start
        stderr = b""
        while True:
            stderr_bytes = proc.stderr.read()
            if not stderr_bytes:
                break
            stderr = stderr_bytes.decode(
                "utf-8", errors="replace"
            ).strip()
        if completed != 0:
            error_msg = (
                stderr
                if stderr
                else f"ffmpeg exited with code {completed}"
            )
            raise RenderExportError(
                f"Video muxing failed: {error_msg}. "
                f"Output format: {export_format.upper()}"
            )
        if not output_video.exists():
            raise RenderExportError(
                f"Output file not created: {output_video}"
            )
        output_size = output_video.stat().st_size
        if output_size < 1024:
            raise RenderExportError(
                f"Output file suspiciously small ({output_size} bytes): "
                f"{output_video}. Video may be corrupted."
            )
        if export_format.lower() == "mp4":
            with open(output_video, "rb") as fh:
                header = fh.read(8)
            needs_reorder = (
                len(header) >= 8 and header[4:8] == b"mdat"
            )
            if needs_reorder:
                reordered = (
                    output_dir / "melosviz-export-reordered.mp4"
                )
                reorder_cmd = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(output_video),
                    "-c:v",
                    "copy",
                    "-c:a",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(reordered),
                ]
                reorder_proc = subprocess.run(
                    reorder_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if (
                    reorder_proc.returncode == 0
                    and reordered.exists()
                    and reordered.stat().st_size >= 1024
                ):
                    output_video.unlink()
                    reordered.rename(output_video)
                else:
                    logger.warning(
                        "MP4 atom reorder failed, file may not play in some browsers: %s",
                        "\n".join(
                            reorder_proc.stderr.splitlines()[:3]
                        ),
                    )
        logger.info(
            "Export complete: format=%s resolution=%dx%d fps=%d "
            "frames=%d size=%.2fMB render=%.2fs mux=%.2fs path=%s",
            export_format,
            width,
            height,
            fps,
            total_frames,
            output_size / 1048576,
            render_duration,
            mux_duration,
            output_video,
        )
        return (
            output_video,
            render_duration,
            mux_duration,
            total_frames,
        )
    except OSError as exc:
        raise FFMpegNotFoundError(
            f"Failed to start ffmpeg: {exc}"
        ) from exc
    except Exception:
        pass
