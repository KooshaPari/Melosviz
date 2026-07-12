#!/usr/bin/env python3
"""Validate docs/fr-status.yaml (machine FR/NFR status SoT).

Checks:
  * YAML parses (PyYAML if present, else constrained stdlib subset)
  * each requirement has id + status in {done, partial, planned}
  * every evidence path exists relative to repo root

Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FR_STATUS = REPO / "docs" / "fr-status.yaml"
ALLOWED = frozenset({"done", "partial", "planned"})


def _load_yaml(text: str) -> object:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _load_yaml_subset(text)


def _load_yaml_subset(text: str) -> object:
    """Minimal loader for the fr-status.yaml shape (stdlib-only CI)."""
    root: dict[str, object] = {}
    requirements: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    in_evidence = False
    in_requirements = False

    def _scalar(raw: str) -> object:
        raw = raw.strip()
        if raw.startswith('"') and raw.endswith('"'):
            return raw[1:-1]
        if raw.startswith("'") and raw.endswith("'"):
            return raw[1:-1]
        if raw in {"true", "false", "null", "~"}:
            return {"true": True, "false": False, "null": None, "~": None}[raw]
        return raw

    for lineno, raw_line in enumerate(text.splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if indent == 0 and line.startswith("requirements:"):
            in_requirements = True
            root["requirements"] = requirements
            current = None
            in_evidence = False
            continue

        if indent == 0 and ":" in line and not line.startswith("-"):
            key, _, val = line.partition(":")
            root[key.strip()] = _scalar(val) if val.strip() else None
            in_requirements = False
            current = None
            in_evidence = False
            continue

        if not in_requirements:
            raise ValueError(f"L{lineno}: unexpected content outside requirements")

        if indent == 2 and line.startswith("- "):
            current = {}
            requirements.append(current)
            in_evidence = False
            rest = line[2:].strip()
            if ":" in rest:
                key, _, val = rest.partition(":")
                if key.strip() == "evidence":
                    current["evidence"] = []
                    in_evidence = True
                else:
                    current[key.strip()] = _scalar(val)
            continue

        if current is None:
            raise ValueError(f"L{lineno}: mapping field without list item")

        # Nested list under `evidence:` is typically indent 6 (2 spaces past the key).
        if indent >= 4 and line.startswith("- ") and in_evidence:
            evidence = current.setdefault("evidence", [])
            if not isinstance(evidence, list):
                raise ValueError(f"L{lineno}: evidence is not a list")
            evidence.append(_scalar(line[2:]))
            continue

        if indent == 4 and ":" in line and not line.startswith("-"):
            key, _, val = line.partition(":")
            key = key.strip()
            if key == "evidence":
                current["evidence"] = []
                in_evidence = True
                # Inline form: evidence: [a, b] — rare; treat empty as list start.
                if val.strip():
                    in_evidence = False
                    current["evidence"] = [_scalar(val)]
            else:
                in_evidence = False
                current[key] = _scalar(val)
            continue

        raise ValueError(f"L{lineno}: unsupported YAML shape: {raw_line!r}")

    return root


def main() -> int:
    if not FR_STATUS.is_file():
        print(f"FAIL: missing {FR_STATUS}", file=sys.stderr)
        return 1

    try:
        data = _load_yaml(FR_STATUS.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — surface parse errors cleanly
        print(f"FAIL: YAML parse error: {exc}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print("FAIL: fr-status root must be a mapping", file=sys.stderr)
        return 1

    reqs = data.get("requirements")
    if not isinstance(reqs, list) or not reqs:
        print("FAIL: requirements must be a non-empty list", file=sys.stderr)
        return 1

    errors: list[str] = []
    for i, item in enumerate(reqs):
        if not isinstance(item, dict):
            errors.append(f"requirements[{i}]: expected mapping")
            continue
        rid = item.get("id")
        status = item.get("status")
        evidence = item.get("evidence")
        if not isinstance(rid, str) or not rid.strip():
            errors.append(f"requirements[{i}]: missing id")
        if status not in ALLOWED:
            errors.append(f"{rid or i}: invalid status {status!r}")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{rid or i}: evidence must be a non-empty list")
            continue
        for path in evidence:
            if not isinstance(path, str) or not path.strip():
                errors.append(f"{rid or i}: empty evidence path")
                continue
            target = REPO / path
            if not target.exists():
                errors.append(f"{rid or i}: missing evidence path {path!r}")

    if errors:
        print("FAIL: fr-status lint:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"PASS: {len(reqs)} FR/NFR rows in docs/fr-status.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
