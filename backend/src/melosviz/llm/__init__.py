"""LLM-driven + offline-template storyboarding.

The Director is the *creative brain* of the pipeline. It now also
delegates to two specialist helpers:

* :mod:`melosviz.llm.lyrics`    — LRC parser + per-phrase sentiment
  that snaps scene boundaries to lyric phrases (real music videos
  cut on lyric lines, not just beats).
* :mod:`melosviz.llm.moodboard` — palette + style extraction from a
  user's reference images (the way real art directors work).
"""

from __future__ import annotations

from . import director, lyrics, moodboard  # noqa: F401

from .director import (
    DEFAULT_ASPECT_RATIO,
    DEFAULT_LLM_MODEL,
    ContinuityAnchor,
    Director,
    DirectorRequest,
    Storyboard,
    StoryboardScene,
    list_aspect_ratios,
    resolve_aspect_ratio,
)

__all__ = [
    "DEFAULT_ASPECT_RATIO",
    "DEFAULT_LLM_MODEL",
    "ContinuityAnchor",
    "Director",
    "DirectorRequest",
    "Storyboard",
    "StoryboardScene",
    "list_aspect_ratios",
    "lyrics",
    "moodboard",
    "resolve_aspect_ratio",
]
