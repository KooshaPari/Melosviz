"""``melosviz`` / ``viz`` command-line entry-point.

Sub-commands
------------
``melosviz analyze <wav>``          Analyze a WAV file and print the RenderSpec JSON.
``melosviz build <wav> [--out DIR]``  Run the full conductor pipeline (mock adapters).
``melosviz render <wav> [--out DIR]`` Run the full conductor pipeline with real adapters.
``melosviz diff <spec_a> <spec_b>``   Print field-level diff between two RenderSpec JSON files.
``melosviz apply <spec> <preset>``    Apply a named preset to a RenderSpec JSON and print result.
``melosviz serve [--host H] [--port P]``  Start the FastAPI bridge server (uvicorn).
``melosviz presets``                  List available presets.
``melosviz version``                  Print the package version.

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
                elif (
                    key not in b
                ):  # pragma: no cover — RenderSpec.model_dump() always yields symmetric keys
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


def _cmd_serve(args: argparse.Namespace) -> int:
    """Start the FastAPI bridge server via uvicorn."""
    try:
        import uvicorn  # type: ignore[import-untyped]
    except ImportError:
        print(
            "viz serve: uvicorn is not installed. "
            'Install it with: pip install "melosviz[bridge]"',
            file=sys.stderr,
        )
        return 1

    uvicorn.run(
        "melosviz.bridge.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )
    return 0


def _cmd_presets(_args: argparse.Namespace) -> int:
    """List all available presets."""
    from melosviz.presets import list_presets

    for name in list_presets():
        print(name)
    return 0


def _cmd_version(_args: argparse.Namespace) -> int:
    """Print the package version."""
    try:
        from importlib.metadata import version

        print(version("melosviz"))
    except Exception:  # pragma: no cover
        print("0.1.0")
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
            f"viz apply: unknown preset {preset_name!r}. Available: {available}",
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
    from melosviz.i18n import t

    parser = argparse.ArgumentParser(
        prog="viz",
        description=t("cli.description"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # viz analyze
    p_analyze = sub.add_parser("analyze", help=t("cli.analyze.help"))
    p_analyze.add_argument("wav", help="Path to WAV file")

    # viz build
    p_build = sub.add_parser("build", help=t("cli.build.help"))
    p_build.add_argument("wav", help="Path to WAV file")
    p_build.add_argument("--out", metavar="DIR", help="Output directory for plan JSON")
    p_build.add_argument(
        "--real",
        action="store_true",
        help="Use real adapters instead of mocks (requires tool installs)",
    )

    # viz render
    p_render = sub.add_parser("render", help=t("cli.render.help"))
    p_render.add_argument("wav", help="Path to WAV file")
    p_render.add_argument("--out", metavar="DIR", help="Output directory")

    # viz diff
    p_diff = sub.add_parser("diff", help=t("cli.diff.help"))
    p_diff.add_argument("spec_a", help="First RenderSpec JSON")
    p_diff.add_argument("spec_b", help="Second RenderSpec JSON")

    # viz apply
    p_apply = sub.add_parser("apply", help=t("cli.apply.help"))
    p_apply.add_argument("spec", help="RenderSpec JSON file")
    p_apply.add_argument("preset", help="Preset name (e.g. cinematic)")

    # melosviz serve
    p_serve = sub.add_parser("serve", help=t("cli.serve.help"))
    p_serve.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help="Bind host (default: 127.0.0.1)",
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=8000,
        metavar="PORT",
        help="Bind port (default: 8000)",
    )

    # melosviz presets
    sub.add_parser("presets", help=t("cli.presets.help"))

    # melosviz version
    sub.add_parser("version", help=t("cli.version.help"))

    args = parser.parse_args()
    dispatch = {
        "analyze": _cmd_analyze,
        "build": _cmd_build,
        "render": _cmd_render,
        "diff": _cmd_diff,
        "apply": _cmd_apply,
        "serve": _cmd_serve,
        "presets": _cmd_presets,
        "version": _cmd_version,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":  # pragma: no cover
    main()
