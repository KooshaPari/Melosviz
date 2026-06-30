"""Override round-trip helpers for ``RenderSpec``.

``apply_overrides`` merges an ``overrides.yaml`` (or dict) onto a canonical
``RenderSpec``.  ``diff_overrides`` reports which keys in the override diverge
from the canonical spec.

Design:
  - Overrides are *shallow* at the top level: a key present in the override
    replaces the corresponding key in the spec.  Nested dicts are deep-merged.
  - Unknown override keys (not present in the canonical spec) are accepted and
    appended — this allows downstream adapters to inject adapter-specific flags.
  - ``OverrideError`` is raised for structurally invalid overrides (e.g. a
    non-dict YAML root).
"""

from __future__ import annotations

import copy
from typing import Any


class OverrideError(ValueError):
    """Raised when the override payload is structurally invalid."""


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict with ``patch`` deep-merged over ``base``.

    Lists in ``patch`` replace (not extend) lists in ``base``.  Dicts are
    recursively merged.
    """
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _spec_to_dict(spec: Any) -> dict[str, Any]:
    """Return the spec as a plain dict (serialise if it's a Pydantic model)."""
    if isinstance(spec, dict):
        return copy.deepcopy(spec)
    if hasattr(spec, "model_dump"):
        return spec.model_dump()
    raise OverrideError(
        f"spec must be a dict or a Pydantic BaseModel, got {type(spec).__name__}"
    )


def apply_overrides(spec: Any, overrides: Any) -> dict[str, Any]:
    """Return a new spec dict with ``overrides`` merged over ``spec``.

    Args:
        spec:      The canonical ``RenderSpec`` (Pydantic model or dict).
        overrides: Override mapping (dict or YAML-parsed object).  Must be a
                   ``dict``; passing ``None`` is treated as an empty override.

    Returns:
        A plain ``dict`` representing the merged spec.

    Raises:
        OverrideError: If ``overrides`` is not a ``dict`` (or ``None``).
    """
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise OverrideError(
            f"overrides must be a dict (e.g. loaded from YAML), "
            f"got {type(overrides).__name__}"
        )

    base = _spec_to_dict(spec)
    return _deep_merge(base, overrides)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def _collect_diffs(
    canonical: dict[str, Any],
    override: dict[str, Any],
    path: str = "",
) -> list[dict[str, Any]]:
    """Recursively collect keys where ``override`` diverges from ``canonical``."""
    diffs: list[dict[str, Any]] = []
    all_keys = set(canonical) | set(override)
    for key in sorted(all_keys):
        full_path = f"{path}.{key}" if path else key
        if key not in canonical:
            diffs.append({"path": full_path, "canonical": "<missing>", "override": override[key]})
        elif key not in override:
            # Key present in canonical but absent in override — not a divergence
            pass
        elif isinstance(canonical[key], dict) and isinstance(override[key], dict):
            diffs.extend(_collect_diffs(canonical[key], override[key], path=full_path))
        elif canonical[key] != override[key]:
            diffs.append(
                {"path": full_path, "canonical": canonical[key], "override": override[key]}
            )
    return diffs


def diff_overrides(spec: Any, overrides: Any) -> list[dict[str, Any]]:
    """Return a list of differences between ``spec`` and ``overrides``.

    Each entry is a dict ``{"path": str, "canonical": value, "override": value}``.
    An empty list means the overrides do not diverge from the canonical spec
    (or the override is empty).

    Args:
        spec:      Canonical ``RenderSpec`` (Pydantic model or dict).
        overrides: Override mapping to compare against the canonical spec.

    Returns:
        List of ``{"path", "canonical", "override"}`` dicts; empty if no diffs.

    Raises:
        OverrideError: If ``overrides`` is not a ``dict`` (or ``None``).
    """
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise OverrideError(
            f"overrides must be a dict (e.g. loaded from YAML), "
            f"got {type(overrides).__name__}"
        )

    canonical = _spec_to_dict(spec)
    return _collect_diffs(canonical, overrides)
