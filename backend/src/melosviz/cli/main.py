"""``viz`` command-line entry-point.

Sub-commands
------------
``viz analyze <wav>``          Analyze a WAV file and print the RenderSpec JSON.
``viz build <wav> [--out DIR]``  Run the full conductor pipeline (mock adapters).
``viz render <wav> [--out DIR]`` Run the full conductor pipeline with real adapters.
``viz diff <spec_a> <spec_b>``   Print field-level diff between two RenderSpec JSON files.
``viz apply <spec> <preset>``    Apply a named preset to a RenderSpec JSON and print result.

All sub-commands write to stdout unless ``--out`` is given; errors go to stderr
and exit with a non-zero code.

Optional deps
-------------
``analyze`` and ``build`` use ``melosviz.analysis.audio.spec_from_wav_rich``
(the v2 path that produces scene_segments, dense_keyframes, and timeline_events).
The richer MIR analysis (librosa/demucs/…) is used automatically when those
packages are installed; the dep-light stdlib path is always available.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_analyze(args: argparse.Namespace) -> int:
    """Analyze a WAV file and print the RenderSpec as JSON."""
    from melosviz.analysis.audio import spec_from_wav_rich

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(f"viz analyze: file not found: {wav_path}", file=sys.stderr)
        return 1

    spec = spec_from_wav_rich(wav_path)
    data = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)
    print(json.dumps(data, indent=2, default=str))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    """Analyze a WAV then assemble a render plan (mock adapters by default)."""
    from melosviz.analysis.audio import spec_from_wav_rich
    from melosviz.compose.assemble import assemble_render_plan

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(f"viz build: file not found: {wav_path}", file=sys.stderr)
        return 1

    spec = spec_from_wav_rich(wav_path)
    plan = assemble_render_plan(spec, mock_adapters=not args.real)

    out = json.dumps(plan, indent=2, default=str)
    if args.out:
        out_path = Path(args.out) / "render_plan.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out)
        print(f"viz build: plan written to {out_path}", file=sys.stderr)
    else:
        print(out)
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    """Analyze a WAV then run the real conductor (requires adapters installed)."""
    args.real = True
    return _cmd_build(args)


def _cmd_diff(args: argparse.Namespace) -> int:
    """Print field-level diff between two RenderSpec JSON files."""
    from melosviz.analysis.models import RenderSpec

    path_a, path_b = Path(args.spec_a), Path(args.spec_b)
    for p in (path_a, path_b):
        if not p.exists():
            print(f"viz diff: file not found: {p}", file=sys.stderr)
            return 1

    spec_a = RenderSpec.model_validate_json(path_a.read_text())
    spec_b = RenderSpec.model_validate_json(path_b.read_text())
    d_a = spec_a.model_dump()
    d_b = spec_b.model_dump()

    def _diff(a: object, b: object, prefix: str = "") -> list[str]:
        lines: list[str] = []
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                sub = f"{prefix}.{key}" if prefix else key
                if key not in a:
                    lines.append(f"+ {sub}: {b[key]}")
                elif key not in b:
                    lines.append(f"- {sub}: {a[key]}")
                else:
                    lines.extend(_diff(a[key], b[key], prefix=sub))
        elif a != b:
            lines.append(f"~ {prefix}: {a!r} → {b!r}")
        return lines

    diff_lines = _diff(d_a, d_b)
    if diff_lines:
        print("\n".join(diff_lines))
    else:
        print("(no differences)")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    """Apply a named preset to a RenderSpec JSON and print the result."""
    from melosviz.analysis.models import RenderSpec
    from melosviz.presets import list_presets

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"viz apply: file not found: {spec_path}", file=sys.stderr)
        return 1

    preset_name = args.preset
    available = list_presets()
    if preset_name not in available:
        print(
            f"viz apply: unknown preset {preset_name!r}. "
            f"Available: {available}",
            file=sys.stderr,
        )
        return 1

    import importlib

    spec = RenderSpec.model_validate_json(spec_path.read_text())
    mod = importlib.import_module(f"melosviz.presets.{preset_name}")
    result = mod.apply(spec)
    print(json.dumps(result.model_dump(), indent=2, default=str))
    return 0


def main() -> None:
    """Entry-point for the ``viz`` console script."""
    parser = argparse.ArgumentParser(
        prog="viz",
        description="Melosviz conductor pipeline CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # viz analyze
    p_analyze = sub.add_parser("analyze", help="Analyze a WAV file → RenderSpec JSON")
    p_analyze.add_argument("wav", help="Path to WAV file")

    # viz build
    p_build = sub.add_parser(
        "build", help="Analyze + assemble render plan (mock adapters)"
    )
    p_build.add_argument("wav", help="Path to WAV file")
    p_build.add_argument("--out", metavar="DIR", help="Output directory for plan JSON")
    p_build.add_argument(
        "--real",
        action="store_true",
        help="Use real adapters instead of mocks (requires tool installs)",
    )

    # viz render
    p_render = sub.add_parser(
        "render", help="Analyze + run real conductor (requires adapters)"
    )
    p_render.add_argument("wav", help="Path to WAV file")
    p_render.add_argument("--out", metavar="DIR", help="Output directory")

    # viz diff
    p_diff = sub.add_parser("diff", help="Diff two RenderSpec JSON files")
    p_diff.add_argument("spec_a", help="First RenderSpec JSON")
    p_diff.add_argument("spec_b", help="Second RenderSpec JSON")

    # viz apply
    p_apply = sub.add_parser("apply", help="Apply a named preset to a RenderSpec JSON")
    p_apply.add_argument("spec", help="RenderSpec JSON file")
    p_apply.add_argument("preset", help="Preset name (e.g. cinematic)")

    args = parser.parse_args()
    dispatch = {
        "analyze": _cmd_analyze,
        "build": _cmd_build,
        "render": _cmd_render,
        "diff": _cmd_diff,
        "apply": _cmd_apply,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
