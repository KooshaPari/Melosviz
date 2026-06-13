"""Input/output helpers for Melosviz.

This package provides thin, dependency-free adapters between Melosviz's
domain models and common file formats. Currently it exposes:

* :mod:`melosviz.io.midi` — Standard MIDI File parser/writer built on
  top of the :class:`melosviz.analysis.models.NoteStream` model.
"""

from __future__ import annotations

import os
import sys

# Ensure ``melosviz`` is importable as a top-level package even when this
# package is loaded via the ``backend.src.melosviz.io`` path. Several
# existing modules in the codebase (notably ``melosviz.analysis`` and
# ``melosviz.presets``) use absolute ``from melosviz.X`` style imports,
# so ``backend/src`` must be on ``sys.path`` for those to resolve under
# that loading scheme.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
if _SRC_ROOT not in sys.path:
    sys.path.insert(0, _SRC_ROOT)

from .midi import parse_midi, write_midi  # noqa: E402,F401

__all__ = ["parse_midi", "write_midi"]
