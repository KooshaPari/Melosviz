"""Audio analysis helpers for render preparation.

Core design
-----------
* The **stdlib-only** path (``analyze_wav`` + ``spec_from_wav``) is always
  available — no heavy deps required.  CI and minimal envs use this path.
* The **MIR-enriched** path (``analyze_wav_rich`` + ``spec_from_wav_rich``)
  gates each optional dep behind a ``try/import`` guard and falls back
  gracefully.  Heavy deps (librosa, numpy, scipy, Demucs) are *optional* —
  the core test suite must pass without them.

Optional dep strategy
---------------------
* ``librosa`` (+ ``numpy``) — onset detection, beat tracking, spectral
  centroid, spectral contrast, harmonic/percussive separation, chromagram,
  MFCCs.  Graceful fallback to RMS-based estimates if absent.
* ``demucs`` / ``torch`` — stem separation (drums/bass/vocals/other).
  Graceful fallback to zero-filled stem channels if absent.
* ``madmom`` — high-quality downbeat tracking (fallback: every 4th beat).
* ``scipy`` — signal processing helpers (fallback: none / skip).

All optional imports are attempted at analysis call time (not module import)
so the module is always importable regardless of the environment.
"""

from __future__ import annotations

import math
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import audioop as _audioop  # stdlib ≤3.12; removed in 3.13+
    _HAS_AUDIOOP = True
except ImportError:  # pragma: no cover — audioop absent only on Python ≥3.13 without backport
    _audioop = None  # type: ignore[assignment]
    _HAS_AUDIOOP = False

from .models import (
    DenseKeyframe,
    MIRSummary,
    MoodVector,
    RenderSpec,
    SceneSegment,
    StemFrame,
    TimelineEvent,
)

# ---------------------------------------------------------------------------
# AudioAnalysis dataclass (v1 compat)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AudioAnalysis:
    """Compact summary of a WAV file used to seed a render."""

    sample_rate: int
    channels: int
    duration_sec: float
    rms_envelope: list[float]
    peak_rms: float
    estimated_bpm: float | None


# ---------------------------------------------------------------------------
# Stdlib helpers
# ---------------------------------------------------------------------------


def _normalize_samples(samples: array) -> list[float]:  # type: ignore[type-arg]
    if not samples:
        return [0.0]
    peak = max(abs(value) for value in samples) or 1
    return [abs(value) / peak for value in samples]


def _read_wav_mono(path: Path) -> tuple[bytes, int, int, float, int]:
    """Return (mono_bytes, sample_rate, channels, duration_sec, sample_width)."""
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        frame_count = handle.getnframes()
        duration_sec = frame_count / float(sample_rate or 1)
        raw = handle.readframes(frame_count)
        sample_width = handle.getsampwidth()

    if sample_width not in (1, 2, 4):
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    if _HAS_AUDIOOP and _audioop is not None:
        mono = _audioop.tomono(raw, sample_width, 1.0, 1.0) if channels == 2 else raw
    else:
        # Minimal fallback: treat raw bytes directly (stereo interleaving is
        # ignored — acceptable for environments without audioop).
        mono = raw

    return mono, sample_rate, channels, duration_sec, sample_width


# ---------------------------------------------------------------------------
# Public stdlib-only API (v1 — backward compat)
# ---------------------------------------------------------------------------


def analyze_wav(path: str | Path, bucket_count: int = 120) -> AudioAnalysis:
    """Analyze a PCM WAV file with standard-library tooling only."""

    wav_path = Path(path)
    mono, sample_rate, channels, duration_sec, sample_width = _read_wav_mono(wav_path)

    if _HAS_AUDIOOP and _audioop is not None:
        # Align segment_size to a whole number of frames so audioop.rms never
        # raises "not a whole number of frames" (bug: audioop alignment crash).
        raw_size = len(mono) // max(1, bucket_count)
        segment_size = max(sample_width, (raw_size // sample_width) * sample_width)
        envelope: list[float] = []
        peak_rms = 0.0
        for index in range(0, len(mono), segment_size):
            segment = mono[index : index + segment_size]
            if not segment:  # pragma: no cover — range never produces index>=len(mono)
                continue
            rms = _audioop.rms(segment, sample_width)
            peak_rms = max(peak_rms, float(rms))
            envelope.append(float(rms))
        normalized = _normalize_samples(array("f", envelope))
    else:
        # Compute real RMS envelope via pure Python (wave module, no audioop).
        # Each window covers bucket_size samples; result is normalised to [0, 1].
        n_samples = len(mono) // sample_width
        bucket_size = max(1, n_samples // max(1, bucket_count))
        envelope_raw: list[float] = []
        for bucket in range(bucket_count):
            start = bucket * bucket_size * sample_width
            end = start + bucket_size * sample_width
            chunk = mono[start:end]
            if not chunk:
                envelope_raw.append(0.0)
                continue
            total = 0.0
            n_read = 0
            for off in range(0, len(chunk) - sample_width + 1, sample_width):
                val = int.from_bytes(chunk[off : off + sample_width], "little", signed=True)
                total += val * val
                n_read += 1
            envelope_raw.append(math.sqrt(total / max(1, n_read)))
        peak = max(envelope_raw) or 1.0
        normalized = [v / peak for v in envelope_raw]
        peak_rms = 1.0  # already normalised above

    bpm = None
    if duration_sec > 0 and len(normalized) > 4:
        hits = sum(1 for value in normalized if value > 0.65)
        bpm = round((hits / duration_sec) * 60.0, 2)

    return AudioAnalysis(
        sample_rate=sample_rate,
        channels=channels,
        duration_sec=duration_sec,
        rms_envelope=normalized,
        peak_rms=peak_rms,
        estimated_bpm=bpm,
    )


def spec_from_wav(path: str | Path) -> RenderSpec:
    """Build a small ``RenderSpec`` from a WAV file analysis (v1 compat)."""

    analysis = analyze_wav(path)
    return RenderSpec(
        metadata={
            "source_audio": str(Path(path)),
            "sample_rate": analysis.sample_rate,
            "channels": analysis.channels,
            "duration": analysis.duration_sec,
            "fps": 30,
            "width": 1280,
            "height": 720,
            "analysis_peak_rms": analysis.peak_rms,
            "estimated_bpm": analysis.estimated_bpm,
            "amplitude_envelope": analysis.rms_envelope,
        }
    )


# ---------------------------------------------------------------------------
# Optional-dep guards
# ---------------------------------------------------------------------------


def _try_import_librosa() -> Any:  # pragma: no cover — librosa optional; not installed in test env
    """Return the librosa module or None if not installed."""
    try:
        import librosa  # type: ignore[import-not-found]
        return librosa
    except ImportError:
        return None


def _try_import_numpy() -> Any:  # pragma: no cover — numpy optional; not installed in test env
    try:
        import numpy as np  # type: ignore[import-not-found]
        return np
    except ImportError:
        return None


def _try_import_demucs() -> bool:
    try:  # pragma: no cover — demucs optional; not installed in test environment
        from demucs.pretrained import (
            get_model,  # type: ignore[import-not-found]  # noqa: F401
        )
        return True
    except (ImportError, Exception):
        return False


# ---------------------------------------------------------------------------
# MIR helpers (librosa-backed with RMS fallbacks)
# ---------------------------------------------------------------------------


def _rms_fallback_envelope(mono_bytes: bytes, sample_width: int, n_buckets: int) -> list[float]:
    """Produce a normalised RMS envelope without audioop (pure Python)."""
    n = len(mono_bytes) // sample_width
    bucket_size = max(1, n // n_buckets)
    fmt_size = sample_width
    envelope: list[float] = []
    for i in range(n_buckets):
        start = i * bucket_size * fmt_size
        end = start + bucket_size * fmt_size
        chunk = mono_bytes[start:end]
        if not chunk:
            envelope.append(0.0)
            continue
        total = 0.0
        for j in range(0, len(chunk), fmt_size):
            b = chunk[j : j + fmt_size]
            if len(b) < fmt_size:
                break
            val = int.from_bytes(b, "little", signed=True)
            total += val * val
        rms = math.sqrt(total / max(1, len(chunk) // fmt_size))
        envelope.append(rms)
    peak = max(envelope) or 1.0
    return [v / peak for v in envelope]


def _classify_section_label(
    index: int,
    n_segments: int,
    energy_mean: float,
    brightness_mean: float,
) -> str:
    """Heuristic label for a segment based on position + energy/brightness."""
    if index == 0:
        return "intro"
    if index == n_segments - 1:
        return "outro"
    if energy_mean > 0.7 and brightness_mean > 0.6:
        return "drop"
    if energy_mean > 0.5:
        return "chorus"
    frac = index / max(1, n_segments - 1)
    if frac < 0.25:
        return "verse"
    if frac > 0.75:
        return "breakdown"
    return "verse"


def _librosa_segment_boundaries(
    librosa: Any,
    np: Any,
    y: Any,
    sr: int,
    n_segments: int,
    duration_sec: float,
) -> list[tuple[float, float]]:
    """Use librosa's spectral novelty to detect real segment boundaries.

    Returns a list of (start_sec, end_sec) tuples, length == n_segments.
    """
    try:
        from scipy.signal import find_peaks  # type: ignore[import-not-found]

        hop_length = 512
        S = np.abs(librosa.stft(y, hop_length=hop_length)) ** 2
        log_S = librosa.power_to_db(S, ref=np.max)
        novelty = np.diff(np.sum(log_S, axis=0), prepend=0)
        novelty = np.maximum(novelty, 0)
        kernel = np.ones(16) / 16
        novelty_smooth = np.convolve(novelty, kernel, mode="same")
        min_dist = max(1, int(sr * 8 / hop_length))
        peaks, _ = find_peaks(novelty_smooth, distance=min_dist)
        times_all = librosa.frames_to_time(peaks, sr=sr, hop_length=hop_length)
        boundaries = sorted(times_all[: n_segments - 1].tolist())
        edges = [0.0] + boundaries + [duration_sec]
        segments = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
        while len(segments) < n_segments:
            segments.append((duration_sec, duration_sec))
        return segments[:n_segments]
    except Exception:
        step = duration_sec / max(1, n_segments)
        return [(i * step, (i + 1) * step) for i in range(n_segments)]


def _easing_for_energy(energy: float, prev_energy: float) -> str:
    """Pick a CSS-style easing hint based on energy delta."""
    delta = energy - prev_energy
    if delta > 0.15:
        return "ease_in"
    if delta < -0.15:
        return "ease_out"
    return "ease_in_out"


# ---------------------------------------------------------------------------
# Stem separation (Demucs optional; spectral fallback)
# ---------------------------------------------------------------------------


STEM_NAMES = ("drums", "bass", "vocals", "other")


def _separate_stems_demucs(  # pragma: no cover — Demucs/torch optional; not installed in test env
    wav_path: Path, duration_sec: float, n_frames: int
) -> dict[str, list[float]]:
    """Run Demucs HTDemucs stem separation and return per-stem energy envelopes."""
    try:
        import numpy as np  # type: ignore[import-not-found]
        import torch  # type: ignore[import-not-found]
        import torchaudio  # type: ignore[import-not-found]
        from demucs.apply import apply_model  # type: ignore[import-not-found]
        from demucs.pretrained import get_model  # type: ignore[import-not-found]

        model = get_model("htdemucs")
        model.eval()
        waveform, file_sr = torchaudio.load(str(wav_path))
        if file_sr != model.samplerate:
            waveform = torchaudio.functional.resample(waveform, file_sr, model.samplerate)
        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)
        waveform = waveform.unsqueeze(0)
        with torch.no_grad():
            sources = apply_model(model, waveform, device="cpu", progress=False)
        sources_np = sources.squeeze(0).numpy()
        result: dict[str, list[float]] = {}
        for stem_idx, stem_name in enumerate(STEM_NAMES):
            stem_mono = sources_np[stem_idx].mean(axis=0)
            frame_size = max(1, len(stem_mono) // n_frames)
            envelope: list[float] = []
            for i in range(n_frames):
                chunk = stem_mono[i * frame_size : (i + 1) * frame_size]
                envelope.append(float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) > 0 else 0.0)
            peak = max(envelope) or 1.0
            result[stem_name] = [v / peak for v in envelope]
        return result
    except Exception:
        return _zero_stem_channels(n_frames)


def _zero_stem_channels(n_frames: int) -> dict[str, list[float]]:
    """Return all-zero stem channels (fallback when Demucs unavailable)."""
    return {name: [0.0] * n_frames for name in STEM_NAMES}


def _spectral_stem_fallback(  # pragma: no cover — requires librosa/numpy; not installed in test env
    librosa: Any, np: Any, y: Any, sr: int, n_frames: int
) -> dict[str, list[float]]:
    """Estimate per-stem energy via spectral heuristics (no Demucs)."""
    try:
        hop = max(1, len(y) // n_frames)
        y_harmonic, y_percussive = librosa.effects.hpss(y)

        def _env(signal: Any) -> list[float]:
            rms = librosa.feature.rms(y=signal, frame_length=hop * 2, hop_length=hop)[0]
            resampled = np.interp(
                np.linspace(0, len(rms) - 1, n_frames),
                np.arange(len(rms)),
                rms,
            )
            peak = float(resampled.max()) or 1.0
            return (resampled / peak).tolist()

        n_fft = 2048
        S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        def _band_env(mask: Any) -> list[float]:
            band = S.copy()
            band[~mask, :] = 0
            rms = np.sqrt(np.mean(band ** 2, axis=0))
            resampled = np.interp(
                np.linspace(0, len(rms) - 1, n_frames),
                np.arange(len(rms)),
                rms,
            )
            peak = float(resampled.max()) or 1.0
            return (resampled / peak).tolist()

        return {
            "drums": _env(y_percussive),
            "bass": _band_env(freqs < 300),
            "vocals": _band_env((freqs >= 300) & (freqs < 4000)),
            "other": _env(y_harmonic),
        }
    except Exception:
        return _zero_stem_channels(n_frames)


# ---------------------------------------------------------------------------
# Dense keyframe + segment builders
# ---------------------------------------------------------------------------


def _resample_list(arr: list[float], target_len: int) -> list[float]:
    """Linear resample arr to target_len."""
    if not arr:
        return [0.0] * target_len
    n = len(arr)
    if n == target_len:
        return arr
    return [
        arr[min(n - 1, int(round(i * (n - 1) / max(1, target_len - 1))))]
        for i in range(target_len)
    ]


def _build_dense_keyframes(
    n_frames: int,
    duration_sec: float,
    energy_arr: list[float],
    brightness_arr: list[float],
    valence_arr: list[float],
    arousal_arr: list[float],
    onset_arr: list[float],
    beat_arr: list[float],
    spectral_centroid_arr: list[float],
    stem_channels: dict[str, list[float]],
) -> list[dict[str, Any]]:
    """Assemble dense_keyframes list from per-frame arrays."""

    def _at(a: list[float], i: int) -> float:
        return a[min(i, len(a) - 1)] if a else 0.0

    frames: list[dict[str, Any]] = []
    prev_energy = 0.0
    for i in range(n_frames):
        t = (i / max(1, n_frames - 1)) * duration_sec
        energy = _at(energy_arr, i)
        easing = _easing_for_energy(energy, prev_energy)
        prev_energy = energy
        kf = DenseKeyframe(
            t=round(t, 4),
            energy=round(energy, 4),
            brightness=round(_at(brightness_arr, i), 4),
            valence=round(_at(valence_arr, i), 4),
            arousal=round(_at(arousal_arr, i), 4),
            beat_strength=round(_at(beat_arr, i), 4),
            onset_strength=round(_at(onset_arr, i), 4),
            spectral_centroid=round(_at(spectral_centroid_arr, i), 2),
            stems=StemFrame(
                drums=round(_at(stem_channels.get("drums", []), i), 4),
                bass=round(_at(stem_channels.get("bass", []), i), 4),
                vocals=round(_at(stem_channels.get("vocals", []), i), 4),
                other=round(_at(stem_channels.get("other", []), i), 4),
            ),
            easing=easing,
        )
        frames.append(kf.model_dump())
    return frames


def _build_scene_segments(
    librosa: Any,
    np: Any,
    y: Any,
    sr: int,
    duration_sec: float,
    energy_per_sec: list[float],
    brightness_per_sec: list[float],
    valence_per_sec: list[float],
    arousal_per_sec: list[float],
    stem_channels: dict[str, list[float]],
    n_dense_frames: int,
) -> list[dict[str, Any]]:
    """Compute semantically-classified scene segments from real audio novelty."""

    n_segments = max(4, min(8, int(duration_sec / 30)))

    if librosa is not None and np is not None and y is not None:
        segment_boundaries = _librosa_segment_boundaries(
            librosa, np, y, sr, n_segments, duration_sec
        )
    else:
        step = duration_sec / max(1, n_segments)
        segment_boundaries = [(i * step, (i + 1) * step) for i in range(n_segments)]

    def _mean_in_range(arr: list[float], start: float, end: float, total: float) -> float:
        if not arr or total <= 0:  # pragma: no cover — callers always pass valid arrays
            return 0.0
        n = len(arr)
        i0 = int((start / total) * n)
        i1 = max(i0 + 1, int((end / total) * n))
        chunk = arr[i0:i1]
        return sum(chunk) / len(chunk) if chunk else 0.0

    def _dominant_stem(start: float, end: float) -> str:
        best, best_val = "other", 0.0
        for stem_name, ch in stem_channels.items():
            val = _mean_in_range(ch, start, end, n_dense_frames)
            if val > best_val:
                best_val, best = val, stem_name
        return best

    segments: list[dict[str, Any]] = []
    n_real = len(segment_boundaries)
    for idx, (start, end) in enumerate(segment_boundaries):
        if end <= start:
            continue
        em = _mean_in_range(energy_per_sec, start, end, duration_sec)
        bm = _mean_in_range(brightness_per_sec, start, end, duration_sec)
        vm = _mean_in_range(valence_per_sec, start, end, duration_sec)
        am = _mean_in_range(arousal_per_sec, start, end, duration_sec)
        label = _classify_section_label(idx, n_real, em, bm)
        seg = SceneSegment(
            index=idx,
            label=label,
            start=round(start, 3),
            end=round(end, 3),
            energy_mean=round(em, 4),
            brightness_mean=round(bm, 4),
            mood=MoodVector(valence=round(vm, 4), arousal=round(am, 4)),
            dominant_stem=_dominant_stem(start, end),
        )
        segments.append(seg.model_dump())

    return segments


# ---------------------------------------------------------------------------
# Rich analysis entry point
# ---------------------------------------------------------------------------


def analyze_wav_rich(
    path: str | Path,
    *,
    n_dense_fps: int = 15,
    use_demucs: bool = True,
) -> RenderSpec:
    """Full MIR-enriched analysis → RenderSpec v2.

    Parameters
    ----------
    path:
        Path to a PCM WAV file.
    n_dense_fps:
        Dense keyframe rate in frames-per-second (10–30 recommended).
        Clamped to [10, 30].
    use_demucs:
        Whether to attempt Demucs stem separation.  Set to False to
        force the spectral fallback (faster, no GPU required).

    Returns
    -------
    RenderSpec
        Fully populated v2 spec.  v2 fields are empty/minimal when the
        corresponding optional dep is unavailable.
    """

    n_dense_fps = max(10, min(30, n_dense_fps))
    wav_path = Path(path)

    # --- 1. Base stdlib analysis (always available) ----------------------
    base = analyze_wav(wav_path)
    n_dense_frames = max(1, int(base.duration_sec * n_dense_fps))

    # --- 2. Try librosa for rich MIR features ----------------------------
    librosa = _try_import_librosa()
    np = _try_import_numpy()

    y: Any = None
    sr: int = base.sample_rate
    energy_arr: list[float] = _resample_list(base.rms_envelope, n_dense_frames)
    brightness_arr: list[float] = [0.5] * n_dense_frames
    valence_per_frame: list[float] = [0.5] * n_dense_frames
    arousal_per_frame: list[float] = energy_arr[:]
    onset_arr: list[float] = [0.0] * n_dense_frames
    beat_arr: list[float] = [0.0] * n_dense_frames
    spectral_centroid_arr: list[float] = [0.0] * n_dense_frames
    valence_per_sec: list[float] = []
    arousal_per_sec: list[float] = []
    energy_per_sec: list[float] = []
    brightness_per_sec: list[float] = []
    tempo_bpm: float | None = base.estimated_bpm
    tempo_curve: list[float] = []
    danceability: float | None = None
    key: str | None = None
    mode: str | None = None
    beat_times: list[float] = []
    onset_times: list[float] = []
    downbeat_times: list[float] = []

    if librosa is not None and np is not None:  # pragma: no cover — requires librosa/numpy
        try:
            y, sr = librosa.load(str(wav_path), sr=None, mono=True)
            duration_sec = float(len(y) / sr)

            # Beat tracking
            tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            tempo_bpm = float(np.atleast_1d(tempo_raw)[0])
            beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
            if len(beat_times) > 1:
                ibi = np.diff(beat_times)
                tempo_curve = (60.0 / np.maximum(ibi, 1e-6)).tolist()
            else:
                tempo_curve = [tempo_bpm] if tempo_bpm else []

            # Onset detection
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
            onset_times = librosa.frames_to_time(onset_frames, sr=sr).tolist()
            onset_env_raw = librosa.onset.onset_strength(y=y, sr=sr)
            onset_env_norm = (onset_env_raw / (onset_env_raw.max() or 1.0)).tolist()

            # RMS energy (per dense frame)
            hop = max(1, len(y) // n_dense_frames)
            rms_raw = librosa.feature.rms(y=y, hop_length=hop)[0]
            rms_norm = rms_raw / (rms_raw.max() or 1.0)
            energy_arr = np.interp(
                np.linspace(0, len(rms_norm) - 1, n_dense_frames),
                np.arange(len(rms_norm)),
                rms_norm,
            ).tolist()

            # Spectral centroid (Hz + normalised brightness)
            sc_raw = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
            spectral_centroid_arr = np.interp(
                np.linspace(0, len(sc_raw) - 1, n_dense_frames),
                np.arange(len(sc_raw)),
                sc_raw,
            ).tolist()
            sc_max = float(sc_raw.max()) or 1.0
            brightness_arr = [v / sc_max for v in spectral_centroid_arr]

            # Onset envelope → per dense frame
            onset_arr = np.interp(
                np.linspace(0, len(onset_env_norm) - 1, n_dense_frames),
                np.arange(len(onset_env_norm)),
                np.array(onset_env_norm),
            ).tolist()

            # Beat strength per dense frame
            beat_frames_dense: list[float] = [0.0] * n_dense_frames
            for bt in beat_times:
                fi = int((bt / duration_sec) * (n_dense_frames - 1))
                if 0 <= fi < n_dense_frames:
                    beat_frames_dense[fi] = 1.0
            beat_arr = beat_frames_dense

            # Per-second trajectories
            n_secs = max(1, int(duration_sec))
            sec_frames = max(1, len(rms_norm) // n_secs)
            energy_per_sec = [
                float(rms_norm[i * sec_frames : (i + 1) * sec_frames].mean())
                for i in range(n_secs)
            ]
            brightness_per_sec = np.interp(
                np.linspace(0, len(sc_raw) - 1, n_secs),
                np.arange(len(sc_raw)),
                sc_raw / sc_max,
            ).tolist()

            # Valence / Arousal from MFCCs
            try:
                mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
                valence_raw = np.clip(mfcc[1] / (np.abs(mfcc[1]).max() or 1.0) * 0.5 + 0.5, 0, 1)
                valence_per_frame = np.interp(
                    np.linspace(0, len(valence_raw) - 1, n_dense_frames),
                    np.arange(len(valence_raw)),
                    valence_raw,
                ).tolist()
                arousal_per_frame = energy_arr
                valence_per_sec = np.interp(
                    np.linspace(0, len(valence_raw) - 1, n_secs),
                    np.arange(len(valence_raw)),
                    valence_raw,
                ).tolist()
                arousal_per_sec = energy_per_sec[:]
            except Exception:
                valence_per_frame = [0.5] * n_dense_frames
                arousal_per_frame = energy_arr[:]
                valence_per_sec = [0.5] * n_secs
                arousal_per_sec = energy_per_sec[:]

            # Danceability heuristic
            beat_regularity = 1.0
            if len(beat_times) > 2:
                ibi_arr = np.diff(beat_times)
                beat_regularity = max(
                    0.0, 1.0 - float(ibi_arr.std() / (ibi_arr.mean() or 1.0))
                )
            danceability = round(
                min(1.0, 0.5 * float(np.mean(rms_norm)) + 0.5 * beat_regularity), 4
            )

            # Key / mode from chroma
            try:
                chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
                chroma_mean = chroma.mean(axis=1)
                key_idx = int(np.argmax(chroma_mean))
                note_names = [
                    "C", "C#", "D", "D#", "E", "F",
                    "F#", "G", "G#", "A", "A#", "B",
                ]
                key = note_names[key_idx]
                major_3rd = int((key_idx + 4) % 12)
                minor_3rd = int((key_idx + 3) % 12)
                mode = "major" if chroma_mean[major_3rd] >= chroma_mean[minor_3rd] else "minor"
            except Exception:
                pass

            # Downbeats: every 4th beat (madmom fallback)
            if len(beat_times) >= 4:
                downbeat_times = [beat_times[i] for i in range(0, len(beat_times), 4)]

        except Exception:
            y = None

    # --- 3. Stems --------------------------------------------------------
    if use_demucs and _try_import_demucs():  # pragma: no cover — demucs not installed in test env
        stem_channels = _separate_stems_demucs(wav_path, base.duration_sec, n_dense_frames)
    elif librosa is not None and np is not None and y is not None:  # pragma: no cover — librosa not installed
        stem_channels = _spectral_stem_fallback(librosa, np, y, sr, n_dense_frames)
    else:
        stem_channels = _zero_stem_channels(n_dense_frames)

    # --- 4. Dense keyframes ----------------------------------------------
    dense_kfs = _build_dense_keyframes(
        n_frames=n_dense_frames,
        duration_sec=base.duration_sec,
        energy_arr=energy_arr,
        brightness_arr=brightness_arr,
        valence_arr=valence_per_frame,
        arousal_arr=arousal_per_frame,
        onset_arr=onset_arr,
        beat_arr=beat_arr,
        spectral_centroid_arr=spectral_centroid_arr,
        stem_channels=stem_channels,
    )

    # --- 5. Timeline events ----------------------------------------------
    timeline_events: list[dict[str, Any]] = []
    for bt in beat_times:
        ev = TimelineEvent(t=round(bt, 4), type="beat", strength=1.0)
        timeline_events.append(ev.model_dump())
    for bar_i, db in enumerate(downbeat_times):  # pragma: no cover — downbeat_times only set by librosa
        ev = TimelineEvent(t=round(db, 4), type="downbeat", strength=1.0)
        d = ev.model_dump()
        d["bar"] = bar_i + 1
        timeline_events.append(d)
    for ot in onset_times:
        ev = TimelineEvent(t=round(ot, 4), type="onset", strength=0.7)
        timeline_events.append(ev.model_dump())
    timeline_events.sort(key=lambda e: e["t"])

    # --- 6. Per-second trajectories (ensure populated) -------------------
    if not energy_per_sec:
        energy_per_sec = _resample_list(base.rms_envelope, max(1, int(base.duration_sec)))
    if not brightness_per_sec:
        brightness_per_sec = [0.5] * len(energy_per_sec)
    if not valence_per_sec:
        valence_per_sec = [0.5] * len(energy_per_sec)
    if not arousal_per_sec:
        arousal_per_sec = energy_per_sec[:]

    # --- 7. Scene segments -----------------------------------------------
    scene_segs = _build_scene_segments(
        librosa=librosa,
        np=np,
        y=y,
        sr=sr,
        duration_sec=base.duration_sec,
        energy_per_sec=energy_per_sec,
        brightness_per_sec=brightness_per_sec,
        valence_per_sec=valence_per_sec,
        arousal_per_sec=arousal_per_sec,
        stem_channels=stem_channels,
        n_dense_frames=n_dense_frames,
    )

    for seg in scene_segs:
        ev = TimelineEvent(t=seg["start"], type="section", strength=1.0)
        d = ev.model_dump()
        d["label"] = seg["label"]
        d["segment_index"] = seg["index"]
        timeline_events.append(d)
    timeline_events.sort(key=lambda e: e["t"])

    # --- 8. MIR summary --------------------------------------------------
    mir_summary = MIRSummary(
        tempo_bpm=round(tempo_bpm, 2) if tempo_bpm is not None else None,
        tempo_curve=[round(v, 2) for v in tempo_curve],
        danceability=danceability,
        energy_trajectory=[round(v, 4) for v in energy_per_sec],
        brightness_trajectory=[round(v, 4) for v in brightness_per_sec],
        valence_trajectory=[round(v, 4) for v in valence_per_sec],
        arousal_trajectory=[round(v, 4) for v in arousal_per_sec],
        key=key,
        mode=mode,
        chord_sequence=[],
    )

    # --- 9. Assemble RenderSpec v2 ---------------------------------------
    return RenderSpec(
        metadata={
            "source_audio": str(wav_path),
            "sample_rate": base.sample_rate,
            "channels": base.channels,
            "duration": base.duration_sec,
            "fps": 30,
            "width": 1280,
            "height": 720,
            "analysis_peak_rms": base.peak_rms,
            "estimated_bpm": base.estimated_bpm,
            "amplitude_envelope": base.rms_envelope,
            "render_spec_version": 2,
            "n_dense_frames": n_dense_frames,
            "n_dense_fps": n_dense_fps,
        },
        palette=[],
        dense_keyframes=dense_kfs,
        timeline_events=timeline_events,
        scene_segments=scene_segs,
        stem_channels={k: [round(v, 4) for v in ch] for k, ch in stem_channels.items()},
        mir=mir_summary.model_dump(),
    )


def spec_from_wav_rich(path: str | Path, **kwargs: Any) -> RenderSpec:
    """Convenience alias for ``analyze_wav_rich``."""
    return analyze_wav_rich(path, **kwargs)


__all__ = [
    "AudioAnalysis",
    "analyze_wav",
    "analyze_wav_rich",
    "spec_from_wav",
    "spec_from_wav_rich",
    "STEM_NAMES",
]
