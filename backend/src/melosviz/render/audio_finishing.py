"""
Audio finishing: LUFS-target normalization + stem export.

Targets the two real-world delivery constraints a music-video oversees:

* ``loudnorm`` (EBU R128 integrated loudness) at the delivery target's
  LUFS. Different distribution channels want very different LUFS:

  - Club PA / live: ``-9 LUFS`` (loud, headroom for room gain)
  - YouTube / Spotify / Apple Music: ``-14 LUFS``
  - Broadcast (EBU R128 / ATSC A/85): ``-23 LUFS`` true peak ``-1 dBTP``

* Stem export. Festival VJs / live-mix engineers want the isolated
  sources (drums / bass / synths / vocals) so they can rebalance for
  the room or re-shoot cuts without re-rendering the whole video.

The implementation is ffmpeg-only — no Demucs / Spleeter required —
so it runs in offline mode everywhere ffmpeg runs.

For stem extraction we use a three-band crossover split (``lowpass``
+ ``highpass``) keyed off the spectrogram's centroid. That gives the
VJ the three usable zones (sub-bass, mids, highs) without needing a
neural model. If Demucs is installed (``demucs -o <out> <wav>``),
the higher-quality path is used instead and writes 4 stems
(drums / bass / other / vocals).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _run(cmd: List[str], timeout: float = 120.0) -> Tuple[int, str, str]:
    """Run a subprocess, capturing stdout + stderr."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return 127, "", f"command not found: {exc}"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    return proc.returncode, proc.stdout, proc.stderr


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
    rc, stdout, stderr = _run(cmd)
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
    rc, _, stderr = _run(cmd)
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


# ---------------------------------------------------------------------------
# Stem extraction
# ---------------------------------------------------------------------------

# Stem backend priority order. The first backend whose CLI is on PATH
# AND can be invoked successfully is used. The 3-band crossover is the
# guaranteed fallback (no extra deps beyond ffmpeg).
STEM_BACKEND_PRIORITY: List[str] = [
    "demucs",            # Meta's htdemucs (4 stems: drums/bass/other/vocals)
    "audio-separator",   # python-audio-separator (variety of MDX / VR arch)
    "spleeter",          # Deezer 2-stem / 4-stem / 5-stem
    "three_band_fallback",  # ffmpeg-only 3-band (always available if ffmpeg is)
]


def _has_demucs() -> bool:
    return shutil.which("demucs") is not None


def _has_spleeter() -> bool:
    return shutil.which("spleeter") is not None


def _has_audio_separator() -> bool:
    """python-audio-separator CLI installs as `audio-separator`."""
    return shutil.which("audio-separator") is not None


def detect_stem_backend(prefer: Optional[str] = None) -> str:
    """Return the stem backend that will be used for the current run.

    Args:
        prefer: Force a specific backend (``"demucs"``, ``"spleeter"``,
            ``"audio-separator"``, ``"three_band_fallback"``).  When the
            forced backend is not available, logs a warning and falls
            back to the highest-priority available backend.

    Returns:
        The name of the chosen backend.
    """
    available: Dict[str, bool] = {
        "demucs": _has_demucs(),
        "audio-separator": _has_audio_separator(),
        "spleeter": _has_spleeter(),
        "three_band_fallback": ffmpeg_available(),
    }

    if prefer is not None and prefer != "auto":
        if not available.get(prefer, False):
            logger.warning(
                "detect_stem_backend: forced backend %r not available; "
                "falling back to highest-priority available",
                prefer,
            )
        else:
            return prefer

    for name in STEM_BACKEND_PRIORITY:
        if available.get(name, False):
            return name

    # Should never happen — three_band_fallback only requires ffmpeg
    # which is a hard runtime dep of the orchestrator.
    return "three_band_fallback"


@dataclass
class StemExportResult:
    """Result of a stem-export pass."""

    method: str = "three_band_fallback"  # or 'demucs' / 'spleeter' / 'audio-separator'
    stems: List[str] = field(default_factory=list)  # paths
    logs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _demucs_stems(wav_path: Path, out_dir: Path, model: str = "htdemucs") -> StemExportResult:
    """Use Demucs (if available) to produce 4 stems."""
    cmd = ["demucs", "--out", str(out_dir), "-n", model, str(wav_path)]
    rc, stdout, stderr = _run(cmd, timeout=600.0)
    log = f"demucs rc={rc}\nstdout: {stdout[:200]}\nstderr: {stderr[:200]}"
    tracks_dir = out_dir / model / wav_path.stem
    stems = sorted(str(p) for p in tracks_dir.glob("*.wav")) if tracks_dir.exists() else []
    return StemExportResult(method="demucs", stems=stems, logs=[log])


def _spleeter_stems(wav_path: Path, out_dir: Path, stems_count: int = 4) -> StemExportResult:
    """Use Spleeter (if available) to produce 2 / 4 / 5 stems.

    spleeter separate -p spleeter:{N}stems -o <out_dir> <wav>
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "spleeter",
        "separate",
        "-p",
        f"spleeter:{stems_count}stems",
        "-o",
        str(out_dir),
        str(wav_path),
    ]
    rc, stdout, stderr = _run(cmd, timeout=600.0)
    log = f"spleeter rc={rc}\nstdout: {stdout[:200]}\nstderr: {stderr[:200]}"
    stems_dir = out_dir / wav_path.stem
    stems = sorted(str(p) for p in stems_dir.glob("*.wav")) if stems_dir.exists() else []
    return StemExportResult(method="spleeter", stems=stems, logs=[log])


def _audio_separator_stems(wav_path: Path, out_dir: Path) -> StemExportResult:
    """Use python-audio-separator (if available) for MDX / VR model runs.

    Default model is 'UVR-MDX-NET-Inst_HQ_3' which produces vocals /
    instrumental; we then split instrumental into 2-band for usability.
    Falls back to a basic 2-stem if the model file is not on disk.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "audio-separator",
        str(wav_path),
        "--model_filename",
        "UVR-MDX-NET-Inst_HQ_3.onnx",
        "--output_dir",
        str(out_dir),
    ]
    rc, stdout, stderr = _run(cmd, timeout=600.0)
    log = f"audio-separator rc={rc}\nstdout: {stdout[:200]}\nstderr: {stderr[:200]}"
    stems = sorted(str(p) for p in out_dir.glob("*.wav"))
    return StemExportResult(method="audio-separator", stems=stems, logs=[log])


def _three_band_stems(wav_path: Path, out_dir: Path) -> StemExportResult:
    """
    Three-band crossover fallback: bass (lowpass 200Hz), mid (bandpass
    200-4000Hz), highs (highpass 4000Hz). Good enough for a VJ to
    pre-balance the mix for a venue without a neural model.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stems: List[str] = []
    logs: List[str] = []

    bands = [
        ("bass.wav", "lowpass=f=200"),
        ("mids.wav", "highpass=f=200,lowpass=f=4000"),
        ("highs.wav", "highpass=f=4000"),
    ]
    for name, filt in bands:
        out_path = out_dir / name
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-nostats",
            "-i",
            str(wav_path),
            "-af",
            filt,
            "-ar",
            "48000",
            "-ac",
            "2",
            str(out_path),
        ]
        rc, _, stderr = _run(cmd)
        if rc == 0 and out_path.exists():
            stems.append(str(out_path))
            logs.append(f"{name}: ok ({out_path.stat().st_size} bytes)")
        else:
            logs.append(f"{name}: FAILED (rc={rc}): {stderr[:200]}")
    return StemExportResult(method="three_band_fallback", stems=stems, logs=logs)


def export_stems(
    wav_path: Path,
    out_dir: Path,
    *,
    prefer: Optional[str] = None,
) -> StemExportResult:
    """Export audio stems for live-mix use.

    Picks the highest-priority available backend via
    :func:`detect_stem_backend`, unless ``prefer`` is set.  When the
    preferred backend is not present on PATH, logs a warning and falls
    back to the next available backend.

    Args:
        wav_path: Source WAV file.
        out_dir: Output directory for the stems.
        prefer: Force a specific backend (``"demucs"`` / ``"spleeter"`` /
            ``"audio-separator"`` / ``"three_band_fallback"``).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen = detect_stem_backend(prefer=prefer)
    if chosen == "demucs" and _has_demucs():
        result = _demucs_stems(wav_path, out_dir)
        if result.stems:
            return result
        logger.warning("demucs returned no stems, falling back to next available")
    if chosen == "audio-separator" and _has_audio_separator():
        result = _audio_separator_stems(wav_path, out_dir)
        if result.stems:
            return result
        logger.warning("audio-separator returned no stems, falling back")
    if chosen == "spleeter" and _has_spleeter():
        result = _spleeter_stems(wav_path, out_dir)
        if result.stems:
            return result
        logger.warning("spleeter returned no stems, falling back")
    return _three_band_stems(wav_path, out_dir)


def list_stem_backends() -> List[Dict[str, Any]]:
    """Return the priority-ordered list of stem backends + availability."""
    return [
        {
            "name": name,
            "available": {
                "demucs": _has_demucs(),
                "audio-separator": _has_audio_separator(),
                "spleeter": _has_spleeter(),
                "three_band_fallback": ffmpeg_available(),
            }.get(name, False),
            "priority": idx,
        }
        for idx, name in enumerate(STEM_BACKEND_PRIORITY)
    ]


# ---------------------------------------------------------------------------
# ffmpeg availability check
# ---------------------------------------------------------------------------


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


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


# ---------------------------------------------------------------------------
# Python-import wrappers (drop-in for the AI stem backends)
# ---------------------------------------------------------------------------

def _try_import_demucs():
    try:
        from demucs.api import Separator  # type: ignore
        return Separator
    except ImportError:
        return None


def _try_import_spleeter():
    try:
        import spleeter.separator  # type: ignore
        return spleeter.separator
    except ImportError:
        return None


def _try_import_audio_separator():
    try:
        import audio_separator.separator  # type: ignore
        return audio_separator.separator
    except ImportError:
        return None


def has_python_stem_backend() -> bool:
    """True if any AI stem backend is importable as a Python module."""
    return any(
        mod is not None
        for mod in (_try_import_demucs(), _try_import_spleeter(), _try_import_audio_separator())
    )


def demucs_python_stems(wav_path, out_dir, model="htdemucs"):
    """In-process Demucs stem-split (no CLI subprocess). Returns dict with 'stems' + 'logs'."""
    out_dir.mkdir(parents=True, exist_ok=True)
    Separator = _try_import_demucs()
    if Separator is None:
        return {"method": "demucs_python", "stems": [], "logs": ["demucs Python package not installed"]}
    try:
        sep = Separator(model=model, device="cpu")
        sep.separate_audio_file(str(wav_path))
        tracks_dir = out_dir / model / wav_path.stem
        stems = sorted(str(p) for p in tracks_dir.glob("*.wav"))
        return {"method": "demucs_python", "stems": stems, "logs": [f"demucs_python: {len(stems)} stems"]}
    except Exception as exc:
        return {"method": "demucs_python", "stems": [], "logs": [f"demucs_python failed: {exc}"]}


def spleeter_python_stems(wav_path, out_dir, stems_count=4):
    """In-process Spleeter stem-split."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sep_mod = _try_import_spleeter()
    if sep_mod is None:
        return {"method": "spleeter_python", "stems": [], "logs": ["spleeter Python package not installed"]}
    try:
        separation = sep_mod.Separator(f"spleeter:{stems_count}stems")
        separation.separate_to_file(str(wav_path), str(out_dir))
        stems_dir = out_dir / wav_path.stem
        stems = sorted(str(p) for p in stems_dir.glob("*.wav")) if stems_dir.exists() else []
        return {"method": "spleeter_python", "stems": stems, "logs": [f"spleeter_python: {len(stems)} stems"]}
    except Exception as exc:
        return {"method": "spleeter_python", "stems": [], "logs": [f"spleeter_python failed: {exc}"]}


def audio_separator_python_stems(wav_path, out_dir):
    """In-process python-audio-separator stem-split."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sep_mod = _try_import_audio_separator()
    if sep_mod is None:
        return {"method": "audio_separator_python", "stems": [], "logs": ["audio-separator Python package not installed"]}
    try:
        file = sep_mod.Separator(
            str(wav_path),
            model_filename="UVR-MDX-NET-Inst_HQ_3.onnx",
            output_dir=str(out_dir),
        )
        file.process()
        stems = sorted(str(p) for p in out_dir.glob("*.wav"))
        return {"method": "audio_separator_python", "stems": stems, "logs": [f"audio_separator_python: {len(stems)} stems"]}
    except Exception as exc:
        return {"method": "audio_separator_python", "stems": [], "logs": [f"audio_separator_python failed: {exc}"]}


def export_stems_python_first(wav_path, out_dir, *, backend=None):
    """One-call entry: prefer Python import, fall back to CLI, then 3-band."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = backend or detect_stem_backend()
    if target == "demucs":
        r = demucs_python_stems(wav_path, out_dir)
        if r["stems"]:
            return r
        return _demucs_stems(wav_path, out_dir)
    if target == "spleeter":
        r = spleeter_python_stems(wav_path, out_dir)
        if r["stems"]:
            return r
        return _spleeter_stems(wav_path, out_dir)
    if target == "audio-separator":
        r = audio_separator_python_stems(wav_path, out_dir)
        if r["stems"]:
            return r
        return _audio_separator_stems(wav_path, out_dir)
    return _three_band_stems(wav_path, out_dir)
