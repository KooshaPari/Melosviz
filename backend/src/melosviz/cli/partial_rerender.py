"""Partial-scene re-render policy.

Pure functions that decide which scene indices to re-render given a target
scene index + the env-controlled neighbor policy. Used by both the
`viz generate --only-scenes=N` and `viz direct --re-render` flows so a
one-scene edit regenerates its neighbors as well (so the transitions
stay continuous instead of snapping against stale MP4s).

Env var: `MELOSVIZ_DIRECT_NEIGHBORS`
  - unset / empty / "auto" → DEFAULT_NEIGHBORS (1)
  - "0" / "false" / "no" / "off" → 0 (re-render only the target scene)
  - "1" / "true" / "yes" / "on" → 1 (re-render target + 1 neighbor each side)
  - "2" / "3" → ±2 / ±3 neighbors
  - "max" / any int > MAX_NEIGHBORS → MAX_NEIGHBORS (re-render the whole timeline)
  - "-5" / any negative int → clamped to 0
  - anything unparseable → DEFAULT_NEIGHBORS (1)

Pure functions, no I/O. CLI + bridge import this to resolve the
`--only-scenes` flag before invoking the orchestrator.
"""
from __future__ import annotations

import os
from typing import Mapping, Sequence


MAX_NEIGHBORS: int = 5
DEFAULT_NEIGHBORS: int = 1
_ENV_KEY: str = "MELOSVIZ_DIRECT_NEIGHBORS"

# Acceptable truthy / falsy literals for parse_neighbor_policy.
_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_FALSY: frozenset[str] = frozenset({"0", "false", "no", "off"})


def parse_neighbor_policy(raw: str | None) -> int:
    """Resolve the `MELOSVIZ_DIRECT_NEIGHBORS` env value to an int.

    Returns DEFAULT_NEIGHBORS (1) on missing/empty/"auto"/unparseable.
    Clamps negative -> 0 and > MAX_NEIGHBORS -> MAX_NEIGHBORS.
    "max" -> MAX_NEIGHBORS.
    """
    if raw is None or raw == "" or raw == "auto":
        return DEFAULT_NEIGHBORS
    s = raw.strip().lower()
    if s in _TRUTHY:
        return 1
    if s in _FALSY:
        return 0
    if s == "max":
        return MAX_NEIGHBORS
    try:
        n = int(s)
    except ValueError:
        return DEFAULT_NEIGHBORS
    if n < 0:
        return 0
    if n > MAX_NEIGHBORS:
        return MAX_NEIGHBORS
    return n


def expand_scene_indices_with_neighbors(
    target_scene_index: int,
    total_scenes: int,
    neighbor_count: int,
) -> list[int]:
    """Return the sorted, deduplicated scene indices to re-render.

    `target_scene_index` is clamped to [0, max(total_scenes - 1, 0)].
    `total_scenes` <= 0 collapses to 1 (single-target fallback).
    `neighbor_count` <= 0 returns just the (clamped) target.
    `neighbor_count` >= MAX_NEIGHBORS is the caller's responsibility; we
    trust whatever value the policy gave us.
    """
    total = total_scenes if total_scenes > 0 else 1
    t = max(0, min(target_scene_index, total - 1))
    n = max(0, neighbor_count)
    if n == 0:
        return [t]
    lo = max(0, t - n)
    hi = min(total - 1, t + n)
    return sorted(set(range(lo, hi + 1)))


def resolve_only_scenes(
    target_scene_index: int,
    total_scenes: int,
    env: Sequence[tuple[str, str]] | Mapping[str, str] | None = None,
) -> list[int]:
    """Resolve the env-controlled policy + target → list[int] scene indices.

    `env` is read like a list of `(key, value)` tuples (the same shape
    that `os.environ.items()` returns) — this keeps the function pure
    and trivially testable without touching real env state.

    Resolution order:
      1. Look up `MELOSVIZ_DIRECT_NEIGHBORS` in `env`.
      2. parse_neighbor_policy(value) -> n.
      3. expand_scene_indices_with_neighbors(target, total, n).
    """
    raw: str | None = None
    if env is None:
        raw = os.environ.get(_ENV_KEY)
    elif isinstance(env, Mapping):
        raw = env.get(_ENV_KEY)
    else:
        for k, v in env:
            if k == _ENV_KEY:
                raw = v
                break
    n = parse_neighbor_policy(raw)
    return expand_scene_indices_with_neighbors(target_scene_index, total_scenes, n)


__all__ = [
    "MAX_NEIGHBORS",
    "DEFAULT_NEIGHBORS",
    "expand_scene_indices_with_neighbors",
    "parse_neighbor_policy",
    "resolve_only_scenes",
]


def parse_scene_indices(raw_indices: str, total_scenes: int) -> list[int]:
    """Parse a comma-separated scene-index string like "3,5,7" into sorted unique ints.

    Used by the `--only-scenes` argparse `type=` callback in
    ``cli/main.py``. Out-of-range indices are clamped into [0, total-1],
    negatives drop, duplicates dedupe.
    """
    if not raw_indices:
        return []
    out: list[int] = []
    for part in raw_indices.split(","):
        s = part.strip()
        if not s:
            continue
        try:
            n = int(s)
        except ValueError:
            continue
        if n < 0:
            continue
        out.append(n)
    if total_scenes <= 0:
        return sorted(set(out))
    upper = max(0, total_scenes - 1)
    return sorted(set(n for n in out if n <= upper))


__all__ = [
    "MAX_NEIGHBORS",
    "DEFAULT_NEIGHBORS",
    "expand_scene_indices_with_neighbors",
    "parse_neighbor_policy",
    "parse_scene_indices",
    "resolve_only_scenes",
]
