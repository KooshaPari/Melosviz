"""Override round-trip — TD param edits ↔ overrides.yaml.

**Problem**: when a VJ tweaks parameters interactively in TouchDesigner
(cone angle, blend curve, edge glow, camera path, etc.) those edits live
only inside the ``.toe`` project file.  This module provides a two-way
bridge so edits *never get trapped in the .toe*:

1. **Export**: read current TD operator params from the running network spec
   (or from a TD ``/ui/overrides_panel`` DAT export) and write them to
   ``overrides.yaml``.

2. **Apply / diff**: load ``overrides.yaml`` and either patch a
   :class:`~melosviz.runtime.touchdesigner.generator.NetworkSpec` dict in
   place, or produce a diff showing what diverges from the canonical spec.

This module is **pure Python** — no TD import required.  The actual export
step (reading live TD params) is handled by a small TD Python snippet
embedded in the bootstrap script's ``/ui/overrides_panel``; this module
processes the result.

Override key format
-------------------
Keys follow a ``group.op_name.param_name`` dotted path matching the network
spec structure::

    scanner.disco_main.shape.cone_angle_deg: 21
    looks.drop_1.edge_emission_gain: 1.8
    shots.bridge.camera.path_id: cam_orbit_b
    fields.scanner_1.beat_pulse_gain: 0.42

YAML file structure::

    overrides:
      fields.scanner_1.cone_angle_deg: 21
      mix.domain_blend.photo_opacity: 0.3
      camera.camera_rig.tz: 5.0

Usage::

    from melosviz.runtime.touchdesigner.overrides import (
        load_overrides, apply_overrides, diff_overrides, export_overrides,
    )

    overrides = load_overrides(Path("overrides.yaml"))
    patched   = apply_overrides(network_spec_dict, overrides)
    delta     = diff_overrides(network_spec_dict, overrides)
    export_overrides(current_params, Path("overrides.yaml"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "load_overrides",
    "apply_overrides",
    "diff_overrides",
    "export_overrides",
    "OverrideKey",
    "OverrideEntry",
]

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

#: A dotted path key: ``"group_name.op_name.param_name"``.
OverrideKey = str

#: Mapping of override key → value.
OverrideEntry = dict[OverrideKey, Any]


# ---------------------------------------------------------------------------
# YAML helpers (no pyyaml required — hand-parse the simple flat format)
# ---------------------------------------------------------------------------


def _parse_overrides_yaml(text: str) -> OverrideEntry:
    """Parse the flat ``overrides:`` block from a YAML string.

    Supports only the subset used here::

        overrides:
          key.path: <scalar>

    Scalars are parsed as int > float > bool > string.

    Args:
        text: Raw YAML string.

    Returns:
        Flat dict of override key → Python value.
    """
    result: OverrideEntry = {}
    in_overrides = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()

        if stripped.startswith("#") or not stripped:
            continue

        if stripped.startswith("overrides:"):
            in_overrides = True
            continue

        if in_overrides:
            # Any top-level key (no leading spaces) exits the block
            if line and not line[0].isspace():
                in_overrides = False
                continue

            if ":" not in stripped:
                continue

            key_part, _, val_part = stripped.partition(":")
            key = key_part.strip()
            val_str = val_part.strip()
            result[key] = _coerce_scalar(val_str)

    return result


def _coerce_scalar(s: str) -> Any:
    """Coerce a YAML scalar string to a Python type."""
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    # Strip surrounding quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _render_overrides_yaml(overrides: OverrideEntry) -> str:
    """Render an :class:`OverrideEntry` dict to a YAML string."""
    lines = ["overrides:"]
    for key in sorted(overrides):
        val = overrides[key]
        if isinstance(val, bool):
            lines.append(f"  {key}: {'true' if val else 'false'}")
        elif isinstance(val, str):
            lines.append(f'  {key}: "{val}"')
        else:
            lines.append(f"  {key}: {val}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_overrides(path: Path) -> OverrideEntry:
    """Load overrides from a YAML file.

    Args:
        path: Path to ``overrides.yaml``.

    Returns:
        Flat :class:`OverrideEntry` dict.  Empty dict if the file does not
        exist or contains no ``overrides:`` block.
    """
    path = Path(path)
    if not path.exists():
        logger.debug("overrides.yaml not found at %s — returning empty overrides", path)
        return {}
    text = path.read_text(encoding="utf-8")
    return _parse_overrides_yaml(text)


def apply_overrides(
    network_dict: dict[str, Any],
    overrides: OverrideEntry,
) -> dict[str, Any]:
    """Patch a network-spec dict in place with override values.

    Keys follow ``"group_name.op_name.param_name"`` — the function walks
    the ``groups`` list to find the matching operator and updates its
    ``params`` dict.

    Args:
        network_dict: Deserialised :class:`~melosviz.runtime.touchdesigner.generator.NetworkSpec`
            dict (as returned by ``NetworkSpec.to_dict()``).
        overrides: :class:`OverrideEntry` mapping.

    Returns:
        The same ``network_dict`` object (mutated in place and returned).
    """
    import copy

    result = copy.deepcopy(network_dict)
    group_index: dict[str, dict[str, Any]] = {
        g["name"]: g for g in result.get("groups", [])
    }

    for key, value in overrides.items():
        parts = key.split(".")
        if len(parts) < 3:
            logger.warning("Override key %r has < 3 parts — skipping", key)
            continue

        group_name = parts[0]
        op_name = parts[1]
        param_path = parts[2:]  # may be multi-level for nested params

        group = group_index.get(group_name)
        if group is None:
            logger.warning("Override group %r not found in network spec", group_name)
            continue

        op_dict: dict[str, Any] | None = None
        for op in group.get("operators", []):
            if op["name"] == op_name:
                op_dict = op
                break

        if op_dict is None:
            logger.warning(
                "Override op %r not found in group %r", op_name, group_name
            )
            continue

        # Walk / create nested param path
        target = op_dict.setdefault("params", {})
        for segment in param_path[:-1]:
            if not isinstance(target.get(segment), dict):
                target[segment] = {}
            target = target[segment]

        leaf_key = param_path[-1]
        old_val = target.get(leaf_key)
        target[leaf_key] = value
        logger.debug(
            "Override %s: %r → %r", key, old_val, value
        )

    return result


def diff_overrides(
    network_dict: dict[str, Any],
    overrides: OverrideEntry,
) -> dict[OverrideKey, dict[str, Any]]:
    """Return a diff of which overrides diverge from the canonical network spec.

    Args:
        network_dict: Canonical :class:`NetworkSpec` dict.
        overrides: :class:`OverrideEntry` to compare against.

    Returns:
        Dict of ``key → {"canonical": <val>, "override": <val>}`` for every
        key where the override value differs from the canonical param value.
        Keys absent from the canonical spec are included with
        ``canonical: None``.
    """
    group_index: dict[str, dict[str, Any]] = {
        g["name"]: g for g in network_dict.get("groups", [])
    }
    diff: dict[OverrideKey, dict[str, Any]] = {}

    for key, override_val in overrides.items():
        parts = key.split(".")
        if len(parts) < 3:
            continue

        group_name, op_name, *param_path = parts
        group = group_index.get(group_name)
        canonical_val: Any = None

        if group is not None:
            for op in group.get("operators", []):
                if op["name"] == op_name:
                    target = op.get("params", {})
                    for segment in param_path[:-1]:
                        target = target.get(segment, {})
                    canonical_val = target.get(param_path[-1]) if param_path else None
                    break

        if canonical_val != override_val:
            diff[key] = {"canonical": canonical_val, "override": override_val}

    return diff


def export_overrides(
    current_params: OverrideEntry,
    path: Path,
) -> None:
    """Write current TD param values to ``overrides.yaml``.

    This is called by the TD ``/ui/overrides_panel`` button or the
    bootstrap cleanup hook.  ``current_params`` is a flat dict of
    ``group.op.param → value`` gathered from live TD operators.

    Args:
        current_params: Flat dict of current TD param values.
        path: Destination path (e.g. ``overrides.yaml``).
    """
    path = Path(path)
    path.write_text(_render_overrides_yaml(current_params), encoding="utf-8")
    logger.info("Exported %d overrides to %s", len(current_params), path)
