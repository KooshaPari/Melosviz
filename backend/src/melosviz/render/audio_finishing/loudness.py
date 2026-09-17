"""Loudness analysis: LUFS delivery targets + two-pass normalization."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._proc import run

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LUFS delivery targets
# ---------------------------------------------------------------------------


# Each preset is (integrated_LUFS, true_peak_dBTP, label).
LUFS_TARGETS: Dict[str, Dict[str, Any]] = {
    "club_pa": {
        "label": "Club PA / live venue (-9 LUFS, -1 dBTP)",
        "integrated_lufs": -9.0,
        "true_peak_dbtp": -1.0,
        "lra": "low (compress at +6 dB gain)",
    },
    "youtube": {
        "label": "YouTube / Spotify / Apple Music (-14 LUFS, -1 dBTP)",
        "integrated_lufs": -14.0,
        "true_peak_dbtp": -1.0,
        "lra": "medium",
    },
    "broadcast_ebu_r128": {
        "label": "Broadcast EBU R128 (-23 LUFS, -1 dBTP)",
        "integrated_lufs": -23.0,
        "true_peak_dbtp": -1.0,
        "lra": "high (preserve dynamics)",
    },
    "cinema_pulse": {
        "label": "Cinema / theatrical pulse (-20 LUFS)",
        "integrated_lufs": -20.0,
        "true_peak_dbtp": -2.0,
        "lra": "high",
    },
}


def list_lufs_targets() -> List[Dict[str, Any]]:
    """Return the registered LUFS delivery targets (label + value)."""
    return [
        {"name": name, **{k: v for k, v in meta.items()}}
        for name, meta in LUFS_TARGETS.items()
    ]


def resolve_lufs_target(name: str) -> Dict[str, Any]:
    """Resolve a target name to its LUFS metadata. Falls back to YouTube."""
    meta = LUFS_TARGETS.get(name)
    if meta is None:
        logger.warning("Unknown LUFS target %r, falling back to 'youtube'", name)
        return {"name": "youtube", **LUFS_TARGETS["youtube"]}
    return {"name": name, **meta}


# ---------------------------------------------------------------------------
# Loudness analysis + normalization
# ---------------------------------------------------------------------------


@dataclass
class LoudnessReport:
    """Result of an ``ffmpeg -af loudnorm=print_format=json`` two-pass."""

    input_i: float = 0.0  # integrated loudness (LUFS)
    input_tp: float = 0.0  # true peak (dBTP)
    input_lra: float = 0.0  # loudness range
    input_thresh: float = 0.0
    target_offset: float = 0.0
    output_i: Optional[float] = None
    output_tp: Optional[float] = None
    output_lra: Optional[float] = None
    output_thresh: Optional[float] = None
    target_lufs: float = -14.0
    target_true_peak: float = -1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def analyze_loudness(wav_path: Path) -> LoudnessReport:
    """Run ffmpeg ``loudnorm`` pass 1 (analysis) on a WAV file."""
    report = LoudnessReport()
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(wav_path),
        "-af",
        "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json",
        "-f",
        "null",
        "-",
    ]
    rc, stdout, stderr = run(cmd)
    # ffmpeg writes the JSON block to stderr
    payload = stderr if stderr else stdout
    try:
        start = payload.rindex("{")
        end = payload.rindex("}") + 1
        data = json.loads(payload[start:end])
    except (ValueError, KeyError) as exc:
        logger.warning("loudnorm analysis failed for %s: %s", wav_path, exc)
        return report
    report.input_i = float(data.get("input_i", 0.0))
    report.input_tp = float(data.get("input_tp", 0.0))
    report.input_lra = float(data.get("input_lra", 0.0))
    report.input_thresh = float(data.get("input_thresh", 0.0))
    report.target_offset = float(data.get("target_offset", 0.0))
    return report


def normalize_loudness(
    wav_path: Path,
    out_path: Path,
    target: Dict[str, Any],
    *,
    overwrite: bool = False,
) -> LoudnessReport:
    """Two-pass loudnorm: analyze then apply integrated loudness target."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not overwrite:
        logger.info("normalize_loudness: %s exists, skipping", out_path)
        return LoudnessReport()

    target_i = float(target["integrated_lufs"])
    target_tp = float(target["true_peak_dbtp"])

    # Pass 1 — analyze
    first_pass = analyze_loudness(wav_path)
    first_pass.target_lufs = target_i
    first_pass.target_true_peak = target_tp

    # Pass 2 — apply
    linear = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA=11:"
        f"measured_I={first_pass.input_i}:"
        f"measured_TP={first_pass.input_tp}:"
        f"measured_LRA={first_pass.input_lra}:"
        f"measured_thresh={first_pass.input_thresh}:"
        f"offset={first_pass.target_offset}:"
        f"linear=true:print_format=json"
    )
    cmd = [
        "ffmpeg",
        "-y" if overwrite else "-n",
        "-hide_banner",
        "-nostats",
        "-i",
        str(wav_path),
        "-af",
        linear,
        "-ar",
        "48000",
        "-ac",
        "2",
        str(out_path),
    ]
    rc, _, stderr = run(cmd)
    if rc != 0:
        logger.error("loudnorm pass 2 failed (rc=%d): %s", rc, stderr[:300])
        return first_pass

    # Re-analyze output for verification
    verify = analyze_loudness(out_path)
    first_pass.output_i = verify.input_i
    first_pass.output_tp = verify.input_tp
    first_pass.output_lra = verify.input_lra
    first_pass.output_thresh = verify.input_thresh
    return first_pass

