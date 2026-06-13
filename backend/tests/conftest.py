"""Test configuration for melosviz backend tests.

Ensures the local ``src`` package is importable when tests are executed
from a fresh environment without an editable install.

Also installs a session-scoped monkey-patch for
``librosa.beat.beat_track`` because the upstream numba-compiled beat
tracker segfaults on macOS when invoked with both ``y`` and
``onset_envelope`` (the combination used by the engine) on Python 3.14.
The pure-Python replacement returns deterministic, on-grid tempo and
beat-frame estimates that are sufficient for unit-testing the engine's
data flow.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SRC_ROOT_STR = str(SRC_ROOT)

if SRC_ROOT_STR not in sys.path:
    sys.path.insert(0, SRC_ROOT_STR)

# ---------------------------------------------------------------------------
# librosa.beat.beat_track monkey-patch (must run before engine is imported).
# ---------------------------------------------------------------------------
import librosa  # noqa: E402
import numpy as np  # noqa: E402


def _safe_beat_track(  # noqa: D401 - simple stub
    *,
    y=None,
    sr: int = 22050,
    onset_envelope=None,
    hop_length: int = 512,
    **_: object,
):
    """Pure-Python replacement for :func:`librosa.beat.beat_track`.

    Mirrors the upstream API closely enough for the engine: returns a
    ``(tempo_array, beat_frames)`` pair. The tempo is estimated from the
    median inter-onset interval of prominent peaks in the onset
    envelope. If the envelope is empty or has fewer than two peaks the
    function returns ``0.0`` tempo and an empty beat array (matching
    librosa's degenerate behaviour).
    """
    if onset_envelope is None:
        if y is None:
            return np.asarray(0.0), np.array([], dtype=np.int64)
        onset_envelope = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=hop_length
        )

    onset_envelope = np.asarray(onset_envelope, dtype=np.float32)
    if onset_envelope.size < 4:
        return np.asarray(0.0), np.array([], dtype=np.int64)

    # Use scipy's find_peaks for robust peak detection (avoids
    # numba-jit'd librosa internals).
    try:
        from scipy.signal import find_peaks

        peaks, _ = find_peaks(
            onset_envelope,
            distance=max(1, int(hop_length // 64)),
            prominence=0.05,
        )
    except Exception:  # pragma: no cover - fallback path
        peaks = np.array([], dtype=np.int64)

    if peaks.size < 2:
        return np.asarray(0.0), np.array([], dtype=np.int64)

    intervals = np.diff(peaks.astype(np.float64))
    median_interval = float(np.median(intervals))
    if median_interval <= 0:
        return np.asarray(0.0), np.array([], dtype=np.int64)

    bpm = float(60.0 * sr / (median_interval * hop_length))
    return np.asarray(bpm), peaks.astype(np.int64)


# Apply patch eagerly. This runs at conftest import time, which is
# before test modules import ``melosviz.analysis.engine``.
librosa.beat.beat_track = _safe_beat_track
