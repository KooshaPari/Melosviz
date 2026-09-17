"""Audio finishing: loudness targets, reference-matched mastering, stem export.

Public API is re-exported here so existing imports keep working::

    from melosviz.render.audio_finishing import run_master, normalize_loudness

Submodules:

``loudness``
    LUFS delivery presets + two-pass ``loudnorm`` normalization.
``reference``
    Reference-matched mastering. Measures a reference master's
    (LUFS, LRA, true peak) signature and converges the input onto it.
``stems``
    Demucs / Spleeter / audio-separator backends plus an ffmpeg 3-band
    crossover fallback that always works.
``master``
    The master pass itself, plus the offline plan used when
    ``MELOSVIZ_COMFYUI_OFFLINE=1``.
"""

from __future__ import annotations

from ._proc import ffmpeg_available, run
from .loudness import (
    LUFS_TARGETS,
    LoudnessReport,
    analyze_loudness,
    list_lufs_targets,
    normalize_loudness,
    resolve_lufs_target,
)
from .master import build_offline_master_plan, run_master
from .reference import (
    ReferenceMatchResult,
    ReferenceProfile,
    analyze_reference,
    match_reference,
    measure_profile,
)
from .stems import (
    STEM_BACKEND_PRIORITY,
    StemExportResult,
    audio_separator_python_stems,
    demucs_python_stems,
    detect_stem_backend,
    export_stems,
    export_stems_python_first,
    has_python_stem_backend,
    list_stem_backends,
    spleeter_python_stems,
)
from .stems import (
    _audio_separator_stems as _audio_separator_stems,
)
from .stems import (
    _demucs_stems as _demucs_stems,
)
from .stems import (
    _has_audio_separator as _has_audio_separator,
)
from .stems import (
    _has_demucs as _has_demucs,
)
from .stems import (
    _has_spleeter as _has_spleeter,
)
from .stems import (
    _spleeter_stems as _spleeter_stems,
)
from .stems import (
    _three_band_stems as _three_band_stems,
)
from .stems import (
    _try_import_audio_separator as _try_import_audio_separator,
)
from .stems import (
    _try_import_demucs as _try_import_demucs,
)
from .stems import (
    _try_import_spleeter as _try_import_spleeter,
)

__all__ = [
    # subprocess
    "run",
    "ffmpeg_available",
    # loudness targets
    "LUFS_TARGETS",
    "LoudnessReport",
    "analyze_loudness",
    "list_lufs_targets",
    "normalize_loudness",
    "resolve_lufs_target",
    # reference-matched mastering
    "ReferenceProfile",
    "ReferenceMatchResult",
    "analyze_reference",
    "match_reference",
    "measure_profile",
    # stems
    "STEM_BACKEND_PRIORITY",
    "StemExportResult",
    "audio_separator_python_stems",
    "demucs_python_stems",
    "detect_stem_backend",
    "export_stems",
    "export_stems_python_first",
    "has_python_stem_backend",
    "list_stem_backends",
    "spleeter_python_stems",
    # master
    "build_offline_master_plan",
    "run_master",
]
