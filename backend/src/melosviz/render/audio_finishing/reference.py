"""Reference-matched mastering.

The LUFS presets in :mod:`melosviz.render.audio_finishing.loudness` pin
*integrated loudness* only. Real-world masters also carry a signature in two
other dimensions that listeners hear immediately:

* **Loudness range (LRA)** — how much the track breathes. A club master at
  ``LRA 1.6 LU`` is slammed; an orchestral master at ``LRA 12 LU`` is open.
* **True peak (dBTP)** — the intersample ceiling the mastering chain left.

Given a reference master (a track the artist already likes), this module
measures that three-dimensional signature and drives the input toward it with
a joint convergence loop:

===============  ==============================
objective        corrected by
===============  ==============================
integrated LUFS  linear gain trim
LRA              compressor ratio
true peak        limiter ceiling
===============  ==============================

``ebur128`` reports **true** peak (4x oversampled) while ffmpeg's ``alimiter``
works in the sample domain, so the limiter ceiling is deliberately driven below
the requested ceiling to leave headroom for inter-sample peaks. The loop
re-measures after every pass and stops as soon as all three errors are inside
tolerance.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ._proc import run

logger = logging.getLogger(__name__)

__all__ = [
    "ReferenceProfile",
    "ReferenceMatchResult",
    "analyze_reference",
    "match_reference",
]

# A full-length master pass is minutes of CPU on a 4-minute track, so the
# subprocess budget has to be far above the module default.
_RENDER_TIMEOUT_S = 1800.0
_MEASURE_TIMEOUT_S = 1800.0

_RE_LUFS = re.compile(r"I:\s*(-?[\d.]+)\s*LUFS")
_RE_LRA = re.compile(r"LRA:\s*(-?[\d.]+)\s*LU")
_RE_TP = re.compile(r"Peak:\s*(-?[\d.]+)\s*dBFS")

# alimiter works on sample peaks; intersample overshoot runs ~1 dB above the
# sample-domain ceiling, so the limiter is driven this much lower by default.
_ISP_HEADROOM_DB = 1.0

# --- LRA control -----------------------------------------------------------
# LRA is governed by the compressor THRESHOLD, not its ratio. Measured on a
# real EDM master (ZHU - Faded, LRA 8.8 LU):
#
#     threshold -24 dB -> LRA 2.1 LU
#     threshold -50 dB -> LRA 1.0 LU
#
# Raising the ratio at a fixed threshold stalls around LRA 2.1: ratio only
# reduces content *above* the threshold, while LRA is driven by the quiet
# sections sitting *below* it. Lowering the threshold pulls those quiet
# sections into gain reduction, which is what actually narrows the range.
_COMP_RATIO = 8.0
_COMP_ATTACK_MS = 5.0
_COMP_RELEASE_MS = 100.0
_THRESHOLD_MIN_DB = -52.0
_THRESHOLD_MAX_DB = -16.0
_THRESHOLD_SEED_DB = -26.0
# Makeup gain keeps the post-compressor level roughly constant as the
# threshold moves (calibrated: -24 -> 10 dB, -50 -> 36 dB).
_MAKEUP_OFFSET_DB = 14.0
_MAKEUP_MAX_DB = 44.0
# dB of threshold movement per LU of range error.
_THRESHOLD_STEP_DB_PER_LU = 12.0


def _clamp(value: float, low: float, high: float) -> float:
    """Constrain ``value`` to ``[low, high]``."""
    return max(low, min(high, value))


def _makeup_for_threshold(threshold_db: float) -> float:
    """Makeup gain that keeps level roughly constant as threshold moves."""
    return max(0.0, min(_MAKEUP_MAX_DB, -threshold_db - _MAKEUP_OFFSET_DB))


@dataclass
class ReferenceProfile:
    """The three-dimensional loudness signature of a reference master."""

    source: str = ""
    integrated_lufs: float = -14.0
    lra: float = 11.0
    true_peak_dbtp: float = -1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReferenceMatchResult:
    """Outcome of a reference-matched master, with the full convergence trace."""

    input_dir: str = ""
    output_path: str = ""
    source: ReferenceProfile | None = None
    reference: ReferenceProfile | None = None
    achieved: ReferenceProfile | None = None
    converged: bool = False
    iterations: int = 0
    params: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def measure_profile(wav_path: Path) -> ReferenceProfile:
    """Measure integrated LUFS, LRA and true peak via ffmpeg ``ebur128``.

    Parses the final ``Summary:`` block so per-frame traces don't shadow the
    real numbers.
    """
    profile = ReferenceProfile(source=str(wav_path))
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(wav_path),
        "-af",
        "ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    rc, stdout, stderr = run(cmd, timeout=_MEASURE_TIMEOUT_S)
    if rc != 0:
        logger.error("ebur128 measurement failed for %s (rc=%d)", wav_path, rc)
        return profile
    payload = stderr or stdout
    if "Summary:" not in payload:
        logger.warning("ebur128 produced no Summary block for %s", wav_path)
        return profile
    tail = payload.rsplit("Summary:", 1)[-1]
    m_i, m_lra, m_tp = _RE_LUFS.search(tail), _RE_LRA.search(tail), _RE_TP.search(tail)
    if m_i:
        profile.integrated_lufs = float(m_i.group(1))
    if m_lra:
        profile.lra = float(m_lra.group(1))
    if m_tp:
        profile.true_peak_dbtp = float(m_tp.group(1))
    return profile


def analyze_reference(wav_path: Path) -> ReferenceProfile:
    """Measure the loudness signature of a reference master."""
    return measure_profile(wav_path)


def _build_chain(
    ratio: float,
    threshold_db: float,
    makeup_db: float,
    gain_db: float,
    ceiling_db: float,
) -> str:
    """Compose the mastering filtergraph for one convergence pass."""
    ceiling = 10 ** (ceiling_db / 20.0)
    return (
        f"acompressor=threshold={threshold_db}dB:ratio={ratio:.2f}:"
        f"attack=10:release=120:makeup={makeup_db}dB,"
        f"alimiter=limit=0.7:attack=5:release=50:level=disabled,"
        f"volume={gain_db:.3f}dB,"
        f"alimiter=limit={ceiling:.6f}:attack=5:release=50:level=disabled"
    )


def _render(src: Path, out: Path, chain: str) -> bool:
    """Render one pass. Returns True on success."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-af",
        chain,
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
        str(out),
    ]
    rc, _, stderr = run(cmd, timeout=_RENDER_TIMEOUT_S)
    if rc != 0:
        logger.error("reference match render failed (rc=%d): %s", rc, stderr[:400])
        return False
    return True


def match_reference(
    wav_path: Path,
    out_path: Path,
    reference: ReferenceProfile,
    *,
    max_iterations: int = 10,
    tol_lufs: float = 0.15,
    tol_lra: float = 0.25,
    tol_true_peak: float = 0.30,
    isp_headroom_db: float = _ISP_HEADROOM_DB,
) -> ReferenceMatchResult:
    """Master ``wav_path`` so its signature lands on ``reference``.

    Jointly converges integrated loudness, loudness range and true peak. The
    compressor threshold is seeded from how much narrower the target is than
    the source, then nudged each pass; gain and limiter ceiling are corrected
    against the fresh measurement rather than a predicted one.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    source_profile = measure_profile(wav_path)
    result = ReferenceMatchResult(
        input_dir=str(wav_path.parent),
        output_path=str(out_path),
        source=source_profile,
        reference=reference,
    )

    # Seed the threshold from how much narrower the target is than the source.
    # A target at or above the source's own range needs little compression.
    excess = max(0.0, source_profile.lra - reference.lra)
    threshold_db = _clamp(
        _THRESHOLD_SEED_DB - excess * 1.5,
        _THRESHOLD_MIN_DB,
        _THRESHOLD_MAX_DB,
    )
    ratio = _COMP_RATIO
    gain_db = 0.0
    ceiling_db = reference.true_peak_dbtp - isp_headroom_db

    result.log.append(
        f"source signature I={source_profile.integrated_lufs:.2f} "
        f"LRA={source_profile.lra:.2f} TP={source_profile.true_peak_dbtp:.2f}"
    )
    result.log.append(
        f"reference signature I={reference.integrated_lufs:.2f} "
        f"LRA={reference.lra:.2f} TP={reference.true_peak_dbtp:.2f}"
    )

    achieved = source_profile
    for iteration in range(1, max_iterations + 1):
        makeup_db = _makeup_for_threshold(threshold_db)
        chain = _build_chain(ratio, threshold_db, makeup_db, gain_db, ceiling_db)
        if not _render(wav_path, out_path, chain):
            break
        achieved = measure_profile(out_path)
        err_lufs = reference.integrated_lufs - achieved.integrated_lufs
        err_lra = achieved.lra - reference.lra
        err_tp = achieved.true_peak_dbtp - reference.true_peak_dbtp

        result.history.append(
            {
                "iteration": iteration,
                "ratio": round(ratio, 3),
                "threshold_db": round(threshold_db, 3),
                "makeup_db": round(makeup_db, 3),
                "gain_db": round(gain_db, 3),
                "ceiling_db": round(ceiling_db, 3),
                "measured_lufs": achieved.integrated_lufs,
                "measured_lra": achieved.lra,
                "measured_true_peak": achieved.true_peak_dbtp,
                "err_lufs": round(err_lufs, 3),
                "err_lra": round(err_lra, 3),
                "err_true_peak": round(err_tp, 3),
            }
        )
        result.iterations = iteration
        result.log.append(
            f"iter {iteration}: thr={threshold_db:.1f} ratio={ratio:.2f} "
            f"gain={gain_db:+.3f} ceil={ceiling_db:+.2f} -> "
            f"I={achieved.integrated_lufs:.2f} LRA={achieved.lra:.2f} "
            f"TP={achieved.true_peak_dbtp:.2f}"
        )

        if (
            abs(err_lufs) <= tol_lufs
            and abs(err_lra) <= tol_lra
            and abs(err_tp) <= tol_true_peak
        ):
            result.converged = True
            result.log.append(f"converged after {iteration} pass(es)")
            break

        gain_db += err_lufs
        # LRA: too wide -> lower the threshold; too narrow -> raise it.
        if abs(err_lra) > tol_lra:
            threshold_db = _clamp(
                threshold_db - err_lra * _THRESHOLD_STEP_DB_PER_LU,
                _THRESHOLD_MIN_DB,
                _THRESHOLD_MAX_DB,
            )
        if err_tp > tol_true_peak:
            ceiling_db -= err_tp + 0.15

    result.achieved = achieved
    result.params = {
        "compressor_ratio": round(ratio, 3),
        "compressor_threshold_db": round(threshold_db, 3),
        "compressor_makeup_db": round(_makeup_for_threshold(threshold_db), 3),
        "gain_db": round(gain_db, 3),
        "limiter_ceiling_db": round(ceiling_db, 3),
        "isp_headroom_db": isp_headroom_db,
    }
    return result
