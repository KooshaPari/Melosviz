"""Master pass: offline plan, ffmpeg loudnorm + stems, Resolve fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._proc import run
from .loudness import analyze_loudness, normalize_loudness, resolve_lufs_target
from .stems import detect_stem_backend, export_stems, list_stem_backends

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Offline-mode plan (used when MELOSVIZ_COMFYUI_OFFLINE=1)
# ---------------------------------------------------------------------------


def build_offline_master_plan(
    master_dir: Path,
    *,
    lufs_target: Optional[str] = None,
    export_stems_flag: bool = False,
    audio_wav: Optional[Path] = None,
) -> Dict[str, Any]:
    """Emit a JSON plan describing what the master pass *would* do."""
    plan: Dict[str, Any] = {
        "finishing": "ffmpeg_loudnorm",
        "mode": "offline",
        "master_dir": str(master_dir),
        "deliverables_planned": [
            {"path": str(master_dir / "festival_prores.mov"), "codec": "ProRes 422 HQ", "use": "festival"},
            {"path": str(master_dir / "club_h264.mp4"), "codec": "H.264 yuv420p", "use": "club screens"},
            {"path": str(master_dir / "youtube_h264.mp4"), "codec": "H.264 yuv420p", "use": "YouTube"},
            {"path": str(master_dir / "captions.srt"), "codec": "SRT", "use": "captions"},
        ],
        "next_steps": [
            "Install ffmpeg >= 4.3 (already present in this environment).",
            "Re-run without MELOSVIZ_COMFYUI_OFFLINE to invoke loudnorm + encode.",
        ],
    }

    if lufs_target:
        target_meta = resolve_lufs_target(lufs_target)
        plan["lufs_target"] = target_meta
        plan["deliverables_planned"].append(
            {
                "path": str(master_dir / f"audio_master_{lufs_target}_loudnorm.wav"),
                "codec": f"PCM 24-bit 48k @ {target_meta['integrated_lufs']} LUFS / TP {target_meta['true_peak_dbtp']} dBTP",
                "use": f"audio master for {lufs_target}",
            }
        )

    if export_stems_flag:
        stems_dir = master_dir / "stems"
        chosen_method = detect_stem_backend()
        if chosen_method == "demucs":
            stems_planned = ["drums.wav", "bass.wav", "other.wav", "vocals.wav"]
        elif chosen_method == "audio-separator":
            stems_planned = ["vocals.wav", "instrumental.wav"]
        elif chosen_method == "spleeter":
            stems_planned = ["vocals.wav", "drums.wav", "bass.wav", "other.wav"]
        else:
            stems_planned = ["bass.wav", "mids.wav", "highs.wav"]
        plan["stems_export"] = {
            "out_dir": str(stems_dir),
            "method": chosen_method,
            "stems_planned": stems_planned,
            "available_backends": list_stem_backends(),
        }
        plan["next_steps"].append(
            f"Run `viz master` without MELOSVIZ_COMFYUI_OFFLINE to extract "
            f"stems into {stems_dir} (backend: {chosen_method})."
        )

    if audio_wav is not None:
        plan["source_audio"] = str(audio_wav)
        if audio_wav.exists():
            report = analyze_loudness(audio_wav)
            plan["source_loudness"] = report.to_dict()

    return plan


# ---------------------------------------------------------------------------
# Real run (online)
# ---------------------------------------------------------------------------


def run_master(
    edit_path: Path,
    out_dir: Path,
    *,
    lufs_target: Optional[str] = None,
    export_stems_flag: bool = False,
    audio_wav: Optional[Path] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Execute the master pass: loudness normalize + stem export."""
    out_dir.mkdir(parents=True, exist_ok=True)
    log: List[str] = []
    deliverables: List[Dict[str, Any]] = []

    target_meta = resolve_lufs_target(lufs_target) if lufs_target else None
    if target_meta is not None:
        # Apply loudness normalization if we have a source audio file
        if audio_wav is not None and audio_wav.exists():
            report = normalize_loudness(
                audio_wav,
                out_dir / f"audio_master_{lufs_target}_loudnorm.wav",
                target_meta,
                overwrite=overwrite,
            )
            log.append(
                f"loudnorm applied: input_I={report.input_i:.1f} LUFS -> "
                f"output_I={report.output_i or report.target_lufs:.1f} LUFS"
            )
            deliverables.append(
                {
                    "path": str(out_dir / f"audio_master_{lufs_target}_loudnorm.wav"),
                    "codec": f"PCM 24-bit 48k @ {target_meta['integrated_lufs']} LUFS",
                    "use": lufs_target,
                    "loudness": report.to_dict(),
                }
            )
        else:
            log.append(f"lufs_target={lufs_target} requested but no audio_wav supplied; skipping normalization")

    if export_stems_flag:
        if audio_wav is not None and audio_wav.exists():
            stems_result = export_stems(audio_wav, out_dir / "stems")
            log.append(f"stems: {stems_result.method} -> {len(stems_result.stems)} files")
            deliverables.append(
                {
                    "path": str(out_dir / "stems"),
                    "codec": f"WAV ({stems_result.method})",
                    "use": "live-mix stems",
                    "stems": stems_result.stems,
                }
            )
        else:
            log.append("export_stems requested but no audio_wav supplied; skipping")

    # Always emit a master_plan.json even in online mode for reproducibility
    plan_path = out_dir / "master_plan.json"
    plan = {
        "finishing": "ffmpeg_loudnorm+stem_export",
        "mode": "online",
        "edit": str(edit_path),
        "master_dir": str(out_dir),
        "deliverables": deliverables,
        "log": log,
    }
    plan_path.write_text(json.dumps(plan, indent=2, default=str))
    return plan


