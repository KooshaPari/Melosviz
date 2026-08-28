"""Lyrics-aware storyboarding.

Real music videos cut on lyric phrases. This module turns an LRC file
(``[mm:ss.xx]lyric text``) into a list of :class:`LyricPhrase` objects
that the Director can use to:

* snap scene boundaries to lyric phrase onsets (instead of just beats),
* label each scene with the lyric phrase it depicts,
* drive scene mood from per-phrase sentiment (``mood`` field),
* prefer on-camera / close-up shots for emotional phrases,
* prefer wide / cinematic shots for descriptive phrases.

Sentiment is computed with a small, dependency-free lexicon — good
enough for art-direction without an LLM call. The LLM refinement
pass (in :mod:`melosviz.llm.director`) will rewrite the prompts in
the user's voice when configured.

Supported input formats
-----------------------

LRC (canonical)::

    [00:00.00]City lights are calling out my name
    [00:04.20]Neon pouring through the doorway
    [00:08.50]I can feel the rhythm take me over

Plain text (no timestamps) is also accepted; lines are spread evenly
across the song's duration.

Public API
----------

* :class:`LyricPhrase`        — one lyric line + start/end + sentiment
* :func:`parse_lrc`           — parse LRC text
* :func:`align_to_segments`   — snap MIR segments to lyric phrase boundaries
* :func:`parse_lyrics_file`   — convenience: read file + parse
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

__all__ = [
    "LyricPhrase",
    "parse_lrc",
    "parse_lyrics_file",
    "align_to_segments",
]


# ---------------------------------------------------------------------------
# Sentiment lexicon (small, dependency-free, English)
# ---------------------------------------------------------------------------

_POSITIVE_WORDS: frozenset[str] = frozenset({
    "love", "loved", "loving", "light", "shine", "shining", "glow", "glowing",
    "dream", "dreams", "dreaming", "free", "freedom", "rise", "rising", "fly",
    "flying", "alive", "fire", "burning", "bright", "golden", "warm", "warmth",
    "kiss", "hold", "holdme", "embrace", "smile", "smiling", "joy", "joyful",
    "hope", "hopeful", "beat", "heartbeat", "dance", "dancing", "win", "won",
    "celebrate", "festival", "rush", "rushing", "wild", "wildlife", "high",
    "lift", "lifted", "save", "saved", "salvation", "bliss", "blissful",
    "magic", "magical", "color", "colors", "colour", "colours", "electric",
    "alive", "vivid", "pulse", "pulsing", "thrill", "thrilling", "starlight",
    "sunrise", "sunset", "aurora", "radiant",
})

_NEGATIVE_WORDS: frozenset[str] = frozenset({
    "lost", "losing", "loss", "gone", "broken", "break", "breaking", "fall",
    "falling", "fall", "dark", "darkness", "shadow", "shadows", "cold",
    "freeze", "freezing", "alone", "lonely", "loneliness", "fear", "afraid",
    "tears", "cry", "crying", "hurt", "pain", "painful", "bleed", "bleeding",
    "die", "dies", "dying", "death", "dead", "fade", "fading", "empty",
    "emptiness", "silence", "silent", "burn", "burnt", "smoke", "smoking",
    "ash", "ashes", "ruin", "ruins", "ruined", "wreck", "wreckage",
    "nightmare", "haunt", "haunted", "ghost", "ghosts", "sorrow", "grief",
    "rain", "storm", "thunder", "drown", "drowning", "sink", "sinking",
    "wound", "wounded", "scars", "scar", "bitter", "poison", "venom",
})

_ENERGY_WORDS: frozenset[str] = frozenset({
    "run", "running", "scream", "screaming", "fight", "fighting", "burn",
    "fire", "explode", "explosion", "shatter", "shattered", "crash", "crashing",
    "whip", "whips", "kick", "kicks", "punch", "punches", "blast", "blasts",
    "rush", "rushes", "storm", "storming", "attack", "attacks", "war", "wars",
    "rage", "fury", "fierce", "savage", "wild", "untamed", "swing", "swings",
})

_CALM_WORDS: frozenset[str] = frozenset({
    "breathe", "breathing", "whisper", "whispers", "still", "stillness",
    "quiet", "silence", "silent", "drift", "drifting", "float", "floating",
    "soft", "softly", "gentle", "gently", "tender", "tenderly", "calm",
    "peace", "peaceful", "rest", "resting", "sleep", "sleeping", "dream",
    "dreams", "slow", "slowly", "linger", "lingering", "fade", "fading",
    "sway", "swaying", "echo", "echoes", "echoing",
})


def _score_sentiment(text: str) -> tuple[float, float]:
    """Return (valence, arousal) in [-1, 1].

    * valence  : negative ↔ positive emotion
    * arousal  : calm ↔ energetic (drives camera motion)
    """
    tokens = re.findall(r"[a-z']+", text.lower())
    if not tokens:
        return 0.0, 0.0
    pos = sum(1 for t in tokens if t in _POSITIVE_WORDS)
    neg = sum(1 for t in tokens if t in _NEGATIVE_WORDS)
    energy = sum(1 for t in tokens if t in _ENERGY_WORDS)
    calm = sum(1 for t in tokens if t in _CALM_WORDS)
    n = max(1, len(tokens))
    valence = max(-1.0, min(1.0, (pos - neg) / max(1, n // 4)))
    arousal = max(-1.0, min(1.0, (energy - calm) / max(1, n // 4)))
    return valence, arousal


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class LyricPhrase:
    """One lyric line with start/end times and a sentiment summary.

    Attributes
    ----------
    index : int
        Order in the lyric file (0-based).
    text : str
        The lyric line (whitespace-normalized, lower-cased for hashing).
    start : float
        Onset in seconds from track start.
    end : float
        Offset in seconds; equals next phrase's start, or +5.0 if last.
    valence : float
        [-1, 1] positive vs negative emotion (drives palette mood).
    arousal : float
        [-1, 1] calm vs energetic (drives camera motion / scene_type).
    """

    index: int
    text: str
    start: float
    end: float
    valence: float = 0.0
    arousal: float = 0.0
    mood_label: str = "neutral"
    # Camera-move suggestion derived from arousal.
    suggested_camera: str = "static_hero"
    # Palette mood derived from valence.
    suggested_palette_mood: str = "neutral"

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "valence": self.valence,
            "arousal": self.arousal,
            "mood_label": self.mood_label,
            "suggested_camera": self.suggested_camera,
            "suggested_palette_mood": self.suggested_palette_mood,
        }


# ---------------------------------------------------------------------------
# LRC parser
# ---------------------------------------------------------------------------

_LRC_TIME_RE = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_TAG_LINE_RE = re.compile(r"\[(ar|ti|al|by|length|offset):[^\]]*\]", re.IGNORECASE)


def parse_lrc(text: str) -> list[LyricPhrase]:
    """Parse LRC-formatted lyrics into timed phrases.

    Lines without timestamps are accepted but their start is set to 0
    and end is left for the alignment step to fill in.
    """
    raw: list[tuple[float, str]] = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if _TAG_LINE_RE.match(line):
            continue
        m = _LRC_TIME_RE.match(line)
        if m:
            mm, ss, ms = m.groups()
            t = int(mm) * 60.0 + int(ss)
            # If a fractional component was captured (``[00:04.50]`` or
            # ``[00:04.500]``) treat it as fractional seconds so phrase
            # onsets land on the right downbeat.
            if ms:
                t += int(ms) / (1000.0 if len(ms) == 3 else 100.0)
            content = _LRC_TIME_RE.sub("", line, count=1).strip()
            if content:
                raw.append((t, content))
        else:
            # Plain line, treat as timestamp-less (start=0)
            stripped = line.strip()
            if stripped:
                raw.append((0.0, stripped))

    # Sort by start time (LRC files occasionally list lines out of order)
    raw.sort(key=lambda p: (p[0], p[1]))

    phrases: list[LyricPhrase] = []
    for i, (start, text_line) in enumerate(raw):
        end = raw[i + 1][0] if i + 1 < len(raw) else start + 5.0
        if end <= start:
            end = start + 1.0
        text_line = re.sub(r"\s+", " ", text_line).strip()
        v, a = _score_sentiment(text_line)
        phrases.append(LyricPhrase(
            index=i,
            text=text_line,
            start=start,
            end=end,
            valence=v,
            arousal=a,
            mood_label=_mood_label(v, a),
            suggested_camera=_camera_for_arousal(a),
            suggested_palette_mood=_palette_for_valence(v),
        ))
    return phrases


def parse_lyrics_file(path: str | Path) -> list[LyricPhrase]:
    """Read + parse a lyrics file. Supports LRC, plain text, JSON list."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    # JSON form: [{"text": "...", "start": 0.0, "end": 4.0}, ...]
    s = text.lstrip()
    if s.startswith("[") or s.startswith("{"):
        import json
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [
                    LyricPhrase(
                        index=i,
                        text=str(item.get("text", "")),
                        start=float(item.get("start", 0.0)),
                        end=float(item.get("end", item.get("start", 0.0) + 5.0)),
                    ) for i, item in enumerate(data)
                ]
        except json.JSONDecodeError:
            pass
    return parse_lrc(text)


def align_to_segments(
    phrases: list[LyricPhrase],
    segments: Iterable[dict],
    *,
    min_segment_s: float = 2.0,
) -> list[dict]:
    """Snap MIR segments to lyric phrase boundaries.

    Each segment is split into one or more sub-segments where a lyric
    phrase begins. Sub-segments shorter than ``min_segment_s`` are
    merged with their neighbour.

    Output segments have an extra ``lyric_index`` field pointing into
    the matching :class:`LyricPhrase`.
    """
    segments = sorted(segments, key=lambda s: float(s.get("start", 0.0)))
    out: list[dict] = []
    for seg in segments:
        s_start = float(seg.get("start", 0.0))
        s_end = float(seg.get("end", s_start + 8.0))
        if s_end <= s_start:
            s_end = s_start + 1.0
        # Find phrases that overlap this segment
        in_seg = [p for p in phrases if p.end > s_start and p.start < s_end]
        if not in_seg:
            out.append({**seg, "lyric_index": -1})
            continue
        # Build sub-segments
        sub: list[dict] = []
        for p in in_seg:
            sub_start = max(s_start, p.start)
            sub_end = min(s_end, p.end)
            if sub_end <= sub_start:
                continue
            sub.append({
                **seg,
                "start": sub_start,
                "end": sub_end,
                "duration": sub_end - sub_start,
                "lyric_index": p.index,
                "lyric_text": p.text,
                "lyric_valence": p.valence,
                "lyric_arousal": p.arousal,
                "lyric_mood": p.mood_label,
                "lyric_camera": p.suggested_camera,
            })
        # Merge short sub-segments with the next one
        merged: list[dict] = []
        for item in sub:
            if merged and float(item["end"] - item["start"]) < min_segment_s:
                merged[-1]["end"] = item["end"]
                merged[-1]["duration"] = merged[-1]["end"] - merged[-1]["start"]
            else:
                merged.append(item)
        out.extend(merged)
    # Re-index
    for i, item in enumerate(out):
        item["index"] = i
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mood_label(valence: float, arousal: float) -> str:
    if valence > 0.2 and arousal > 0.2:
        return "euphoric"
    if valence > 0.2 and arousal <= 0.2:
        return "tender"
    if valence <= -0.2 and arousal > 0.2:
        return "fierce"
    if valence <= -0.2 and arousal <= 0.2:
        return "somber"
    return "neutral"


def _camera_for_arousal(arousal: float) -> str:
    if arousal > 0.5:
        return "whip_pan_burst"
    if arousal > 0.2:
        return "handheld_orbit"
    if arousal < -0.4:
        return "slow_pull_back"
    if arousal < -0.1:
        return "slow_push_in"
    return "slow_dolly_in"


def _palette_for_valence(valence: float) -> str:
    if valence > 0.3:
        return "warm"
    if valence < -0.3:
        return "cold"
    return "neutral"


_VALID_LABELS: frozenset[str] = frozenset({
    "euphoric", "tender", "fierce", "somber", "neutral",
})


def is_lyric_mood(s: str) -> bool:
    return s in _VALID_LABELS
