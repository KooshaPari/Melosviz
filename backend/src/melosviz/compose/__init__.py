"""Narrative composer — anti-repetition arc assignment for music-video segments.

This package contains:

* :mod:`~melosviz.compose.narrator` — the seeded, deterministic arc-composer
  that assigns varied scene_type / material / camera-language per segment.
* :mod:`~melosviz.compose.assemble` — end-to-end assembly pipeline that
  sequences composer output through conductor adapters and produces an MP4
  plan timeline.
"""
