"""viz — Melosviz CLI.

Subcommands
-----------
  analyze <wav>              Run audio analysis → print RenderSpec v2 JSON.
  build   <spec>             Route + plan a spec → print the RenderPlan summary.
  render  <spec>             Route + dispatch adapters → produce segment outputs.
  diff    <spec> <overrides> Report keys in overrides that diverge from canonical.
  apply   <spec> <overrides> Merge overrides → print merged spec JSON.

All subcommands accept ``-`` as a path to read from stdin.

Exit codes: 0 = success, 1 = usage error, 2 = runtime error.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path_or_dash: str) -> Any:
    """Load JSON from a file path or ``-`` (stdin)."""
    if path_or_dash == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path_or_dash).read_text(encoding="utf-8"))


def _load_overrides(path_or_dash: str) -> dict[str, Any]:
    """Load overrides from YAML or JSON, falling back to JSON-only if PyYAML absent."""
    if path_or_dash == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path_or_dash).read_text(encoding="utf-8")

    # Try YAML first (superset of JSON); fall back to json.loads
    try:
        import yaml  # type: ignore[import-not-found]
        data = yaml.safe_load(raw)
    except ImportError:
        data = json.loads(raw)

    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"error: overrides file must be a YAML/JSON mapping, got {type(data).__name__}", file=sys.stderr)
        sys.exit(1)
    return data


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_analyze(args: argparse.Namespace) -> int:
    """``viz analyze <wav>`` — analyse audio and emit RenderSpec v2 JSON."""
    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(f"error: audio file not found: {wav_path}", file=sys.stderr)
        return 2

    from melosviz.analysis.audio import spec_from_wav_rich  # type: ignore[import]

    try:
        spec = spec_from_wav_rich(str(wav_path))
    except Exception:
        # Fallback to stdlib-only path if rich deps unavailable
        from melosviz.analysis.audio import spec_from_wav  # type: ignore[import]
        try:
            spec = spec_from_wav(str(wav_path))
        except Exception as exc2:
            print(f"error: analysis failed: {exc2}", file=sys.stderr)
            return 2

    data = spec.model_dump() if hasattr(spec, "model_dump") else spec

    if args.output:
        Path(args.output).write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"wrote spec to {args.output}")
    else:
        print(json.dumps(data, indent=2))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """``viz build <spec>`` — route spec and print the RenderPlan."""
    spec_data = _load_json(args.spec)

    from melosviz.conductor.orchestrator import build_plan

    plan = build_plan(spec_data)
    print(plan.summary())
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """``viz render <spec>`` — dispatch adapters and produce segment outputs."""
    spec_data = _load_json(args.spec)
    output_dir = Path(args.output_dir) if args.output_dir else Path("melosviz-output")

    from melosviz.conductor.orchestrator import orchestrate

    result = orchestrate(
        spec=spec_data,
        output_dir=output_dir,
        skip_unimplemented=args.skip_unimplemented,
        export_format=args.format,
    )

    if result.final_output:
        print(f"final output: {result.final_output}")
    elif result.rendered_paths:
        print(f"rendered {len(result.rendered_paths)} segment(s):")
        for p in result.rendered_paths:
            print(f"  {p}")
    else:
        print("no segments rendered")

    if result.skipped_count:
        print(f"skipped {result.skipped_count} unimplemented segment(s)")

    if not result.success:
        failed = [r for r in result.segment_results if r.error]
        for r in failed:
            print(f"error in segment {r.segment_index} ({r.scene_type.value}): {r.error}", file=sys.stderr)
        return 2

    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """``viz diff <spec> <overrides>`` — report overrides diverging from canonical."""
    spec_data = _load_json(args.spec)
    overrides = _load_overrides(args.overrides)

    from melosviz.conductor.overrides import diff_overrides

    diffs = diff_overrides(spec_data, overrides)
    if not diffs:
        print("no differences")
    else:
        print(json.dumps(diffs, indent=2, default=str))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """``viz apply <spec> <overrides>`` — merge overrides and emit merged spec."""
    spec_data = _load_json(args.spec)
    overrides = _load_overrides(args.overrides)

    from melosviz.conductor.overrides import apply_overrides

    merged = apply_overrides(spec_data, overrides)

    if args.output:
        Path(args.output).write_text(json.dumps(merged, indent=2), encoding="utf-8")
        print(f"wrote merged spec to {args.output}")
    else:
        print(json.dumps(merged, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="viz",
        description="Melosviz — spec-first music-video orchestration CLI.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = sub.add_parser("analyze", help="Analyse a WAV file → RenderSpec v2 JSON")
    p_analyze.add_argument("wav", help="Path to the input audio file (.wav, .mp3, etc.)")
    p_analyze.add_argument("-o", "--output", default="", help="Write spec JSON to this path instead of stdout")

    # build
    p_build = sub.add_parser("build", help="Route a RenderSpec and print the plan")
    p_build.add_argument("spec", help="Path to RenderSpec JSON (or - for stdin)")

    # render
    p_render = sub.add_parser("render", help="Render a RenderSpec via dispatched adapters")
    p_render.add_argument("spec", help="Path to RenderSpec JSON (or - for stdin)")
    p_render.add_argument("-o", "--output-dir", default="", dest="output_dir", help="Output directory (default: melosviz-output)")
    p_render.add_argument("--format", default="mp4", choices=["mp4", "webm"], help="Export format (default: mp4)")
    p_render.add_argument(
        "--skip-unimplemented",
        action="store_true",
        default=False,
        dest="skip_unimplemented",
        help="Skip segments whose adapter is not yet implemented instead of raising",
    )

    # diff
    p_diff = sub.add_parser("diff", help="Report overrides that diverge from the canonical spec")
    p_diff.add_argument("spec", help="Canonical RenderSpec JSON path (or -)")
    p_diff.add_argument("overrides", help="Overrides YAML/JSON path (or -)")

    # apply
    p_apply = sub.add_parser("apply", help="Merge overrides onto a spec and emit the merged spec")
    p_apply.add_argument("spec", help="Canonical RenderSpec JSON path (or -)")
    p_apply.add_argument("overrides", help="Overrides YAML/JSON path (or -)")
    p_apply.add_argument("-o", "--output", default="", help="Write merged spec to this path instead of stdout")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_HANDLERS = {
    "analyze": cmd_analyze,
    "build": cmd_build,
    "render": cmd_render,
    "diff": cmd_diff,
    "apply": cmd_apply,
}


def cli(argv: list[str] | None = None) -> None:
    """Console-scripts entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )

    handler = _HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    rc = handler(args)
    sys.exit(rc)


if __name__ == "__main__":
    cli()
