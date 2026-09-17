"""Stem export: Demucs / Spleeter / audio-separator backends + ffmpeg fallback."""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._proc import ffmpeg_available, run

logger = logging.getLogger(__name__)

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
    rc, stdout, stderr = run(cmd, timeout=600.0)
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
    rc, stdout, stderr = run(cmd, timeout=600.0)
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
    rc, stdout, stderr = run(cmd, timeout=600.0)
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
        rc, _, stderr = run(cmd)
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
