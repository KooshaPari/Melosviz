"""``melosviz`` / ``viz`` command-line entry-point.

Sub-commands
------------
``melosviz analyze <wav>``          Analyze a WAV file and print the RenderSpec JSON.
``melosviz build <wav> [--out DIR]``  Run the full conductor pipeline (mock adapters).
``melosviz render <wav> [--out DIR]`` Run the full conductor pipeline with real adapters.
``melosviz storyboard <wav> --concept "..." [--bpm B] [--palette "..."] [--lyrics file.lrc] [--aspect-ratio preset] [--continuity-character "..."] [--continuity-environment "..."] [--out PATH]``  Storyboard a WAV + LRC + palette + continuity into a scene JSON.
``melosviz generate  <wav> --storyboard <sb.json> [--out DIR] [--job-id ID] [--only-scenes 2,3]`` Run ComfyUI / C4D / Unreal / AE per scene (or a subset).
``melosviz assemble  <out-dir>``      Concat per-scene clips into a master timeline (MediaEncoder / ffmpeg).
``melosviz master    <edit> --out DIR`` DaVinci Resolve colour + audio mix + master encode.
``melosviz ship      <job-dir>``      Package final deliverables (MP4, ProRes, audio stems, captions).
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
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from melosviz.cli.partial_rerender import (
    DEFAULT_NEIGHBORS,
    MAX_NEIGHBORS,
    parse_neighbor_policy,
    resolve_only_scenes,
)
from typing import Optional


class _CliReferenceImageError(RuntimeError):
    """Raised by ``_resolve_reference_image`` when validation fails.

    Carries the localized error message so the calling CLI handler can
    print it to stderr and exit 1. v2 (WBS-2) ContinuityAnchor validation
    surfaces this via the ``cli.error.reference_image_not_found`` i18n
    key rather than silently dropping the path.
    """


def _resolve_reference_image(args: argparse.Namespace, *, cmd: str) -> Optional[Path]:
    """Validate ``--reference-image`` on the CLI and return an expanded Path.

    Implements the v2 (WBS-2) validation rule for the
    ``--reference-image PATH`` flag shared by ``viz storyboard`` /
    ``viz generate`` / ``viz direct``. When the user passes the flag, the
    path is expanded (handles ``~``) and checked against the filesystem —
    a missing path raises :class:`_CliReferenceImageError` whose message
    is the localized ``cli.error.reference_image_not_found`` template;
    handlers should ``except _CliReferenceImageError`` and ``return 1``.

    Args:
        args: Parsed argparse namespace with ``args.reference_image``.
        cmd: Sub-command name (``"storyboard"`` / ``"generate"`` /
            ``"direct"``) used to localize the error message.

    Returns:
        The expanded :class:`pathlib.Path` when supplied and present on
        disk, or ``None`` when the flag was not passed.
    """
    from melosviz.i18n import t

    raw = getattr(args, "reference_image", None)
    if not raw:
        return None
    ref_path = Path(raw).expanduser()
    if not ref_path.is_file():
        raise _CliReferenceImageError(
            t("cli.error.reference_image_not_found", cmd=cmd, path=ref_path)
        )
    return ref_path


def _cmd_analyze(args: argparse.Namespace) -> int:
    """Analyze a WAV file and print the RenderSpec as JSON."""
    from melosviz.analysis.audio import spec_from_wav_rich
    from melosviz.i18n import t

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(t("cli.error.file_not_found", cmd="analyze", path=wav_path), file=sys.stderr)
        return 1

    spec = spec_from_wav_rich(wav_path)
    data = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)
    print(json.dumps(data, indent=2, default=str))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    """Analyze a WAV then assemble a render plan (mock adapters by default)."""
    from melosviz.analysis.audio import spec_from_wav_rich
    from melosviz.compose.assemble import assemble_render_plan
    from melosviz.i18n import t

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(t("cli.error.file_not_found", cmd="build", path=wav_path), file=sys.stderr)
        return 1

    spec = spec_from_wav_rich(wav_path)
    plan = assemble_render_plan(spec, mock_adapters=not args.real)

    out = json.dumps(plan, indent=2, default=str)
    if args.out:
        out_path = Path(args.out) / "render_plan.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out)
        print(t("cli.msg.plan_written", path=out_path), file=sys.stderr)
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
    from melosviz.i18n import t

    path_a, path_b = Path(args.spec_a), Path(args.spec_b)
    for p in (path_a, path_b):
        if not p.exists():
            print(t("cli.error.file_not_found", cmd="diff", path=p), file=sys.stderr)
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
        print(t("cli.msg.no_diff"))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Start the FastAPI bridge server via uvicorn."""
    from melosviz.i18n import t

    try:
        import uvicorn  # type: ignore[import-untyped]
    except ImportError:
        print(t("cli.error.uvicorn_missing"), file=sys.stderr)
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
    from melosviz.i18n import t
    from melosviz.presets import list_presets

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(t("cli.error.file_not_found", cmd="apply", path=spec_path), file=sys.stderr)
        return 1

    preset_name = args.preset
    available = list_presets()
    if preset_name not in available:
        print(
            t(
                "cli.error.unknown_preset",
                preset=preset_name,
                available=available,
            ),
            file=sys.stderr,
        )
        return 1

    import importlib

    spec = RenderSpec.model_validate_json(spec_path.read_text())
    mod = importlib.import_module(f"melosviz.presets.{preset_name}")
    result = mod.apply(spec)
    print(json.dumps(result.model_dump(), indent=2, default=str))
    return 0


def _cmd_storyboard(args: argparse.Namespace) -> int:
    """Generate a beat-synced storyboard JSON from a track + concept."""
    from melosviz.analysis.audio import spec_from_wav_rich
    from melosviz.i18n import t
    from melosviz.llm import ContinuityAnchor, Director, DirectorRequest
    from melosviz.llm.lyrics import parse_lyrics_file
    from melosviz.llm.moodboard import mood_board_summary

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(t("cli.error.file_not_found", cmd="storyboard", path=wav_path), file=sys.stderr)
        return 1

    # v2 (WBS-2): ``--reference-image`` is validated up-front so a
    # typo'd path aborts the command instead of silently threading a
    # broken path through every scene.
    try:
        ref_path = _resolve_reference_image(args, cmd="storyboard")
    except _CliReferenceImageError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    spec = spec_from_wav_rich(wav_path)
    spec_dict = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)
    bpm = float(args.bpm) if args.bpm else float(spec_dict.get("bpm") or 120.0)
    key = str(args.key or spec_dict.get("key_signature") or "C")
    duration = float(spec_dict.get("duration_s") or 0.0)
    segments = list(spec_dict.get("scene_segments") or [])

    # Optional lyrics — LRC / plain text / JSON. Snaps scene boundaries
    # to lyric phrase onsets and labels each scene with the lyric line.
    lyrics = []
    if args.lyrics:
        try:
            lyrics = parse_lyrics_file(args.lyrics)
        except Exception as exc:
            print(t("cli.error.lyrics_parse_failed", path=args.lyrics, error=str(exc)), file=sys.stderr)
            return 1

    # Optional mood board — extract palette + style from 1-5 reference
    # images via PIL median-cut (or keyword fallback).
    mood_board_paths = list(args.mood_board or [])
    mood_board_summary_data: dict = {}
    if mood_board_paths:
        mood_board_summary_data = mood_board_summary(mood_board_paths)
        mb_palette = mood_board_summary_data.get("palette") or []
        if mb_palette and not args.palette:
            args.palette = mb_palette

    # Optional continuity anchor — explicit subject/environment pinned
    # across every scene so the music video tells ONE story instead of
    # N unrelated AI clips.
    continuity_anchor: ContinuityAnchor | None = None
    if args.continuity_character or args.continuity_environment:
        continuity_anchor = ContinuityAnchor(
            subject_token=(args.continuity_character or "").strip(),
            env_token=(args.continuity_environment or "").strip(),
        )
    elif args.reference_image:
        # v2 (WBS-2): allow --reference-image without explicit character /
        # environment pins so the user can just "pin a face / style" and
        # let the Director derive subject/env tokens from the concept.
        continuity_anchor = ContinuityAnchor(
            reference_image=Path(args.reference_image).expanduser(),
        )

    req = DirectorRequest(
        concept=args.concept or "abstract music visual",
        duration_s=duration,
        bpm=bpm,
        key=key,
        segments=segments,
        palette=list(args.palette) if args.palette else [],
        seed=args.seed,
        lyrics=lyrics,
        mood_board=mood_board_paths,
        aspect_ratio=args.aspect_ratio or "youtube_16x9_1080p",
        continuity=continuity_anchor,
        # WBS-108: opt-in to audio-conditioned scene routing even when
        # no character anchor is pinned.
        audio_conditioned_video=bool(getattr(args, "audio_conditioned_video", False)),
    )
    board = Director(seed=args.seed).storyboard(req)
    payload = board.to_dict()
    if mood_board_summary_data:
        payload["mood_board"] = mood_board_summary_data
    if lyrics:
        payload["lyrics"] = [p.to_dict() for p in lyrics]

    # v2 (WBS-101..106): forward --character-root + --character onto the
    # storyboard payload so a downstream `viz generate` can rebuild the
    # registry without re-typing the same args.
    if getattr(args, "character_root", None):
        payload["character_root"] = str(Path(args.character_root).expanduser())
    if getattr(args, "character", None):
        payload["characters"] = list(args.character)

    out = json.dumps(payload, indent=2, default=str)
    if args.out:
        out_path = Path(args.out)
        if out_path.suffix.lower() == ".json":
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(out)
        else:
            out_path.mkdir(parents=True, exist_ok=True)
            target = out_path / "storyboard.json"
            target.write_text(out)
            out_path = target
        print(t("cli.msg.storyboard_written", path=out_path, scenes=len(board.scenes)), file=sys.stderr)
    else:
        print(out)
    return 0


def _cmd_direct(args: argparse.Namespace) -> int:
    """Art-director edit: replace one or more scene fields in a storyboard.json.

    Lets the operator iterate on a single scene (prompt / camera / name)
    without re-running the whole pipeline. By default the existing
    storyboard.json is patched in-place; pass --out to write to a new path.

    With --re-render, the patched storyboard is staged for an immediate
    single-scene re-render via ``viz generate --scene <index> --storyboard
    <patched.json>``. The actual re-render CLI flag is wired into
    ``_cmd_generate``; this command only writes the patch.
    """
    from melosviz.i18n import t

    sb_path = Path(args.storyboard)
    if not sb_path.exists():
        print(t("cli.error.file_not_found", cmd="direct", path=sb_path), file=sys.stderr)
        return 1

    # v2 (WBS-2): ``--reference-image`` is validated up-front so the
    # patched storyboard is never written with a broken continuity path.
    try:
        _ref_path = _resolve_reference_image(args, cmd="direct")
    except _CliReferenceImageError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    payload = json.loads(sb_path.read_text())
    scenes = payload.get("scenes") or []
    if not (1 <= args.scene_index <= len(scenes)):
        print(
            t(
                "cli.error.scene_index_out_of_range",
                index=args.scene_index,
                total=len(scenes),
            ),
            file=sys.stderr,
        )
        return 2
    scene = scenes[args.scene_index - 1]
    edits_applied: list[str] = []

    # Map of argparse attribute → (storyboard JSON field, caster).
    # Only applied when the user actually passed the flag (i.e. value is not None).
    direct_edits = {
        "replace_prompt": ("prompt", str),
        "replace_camera": ("camera", str),
        "replace_name": ("name", str),
    }

    for arg_attr, (json_key, caster) in direct_edits.items():
        new_value = getattr(args, arg_attr, None)
        if new_value is None:
            continue
        scene[json_key] = caster(new_value)
        edits_applied.append(arg_attr)

    # v2 (WBS-2): ``--reference-image`` stamps the path onto the
    # storyboard-level continuity block (not the per-scene one) so every
    # scene inherits it. Path is coerced to string for JSON portability.
    if getattr(args, "reference_image", None):
        ref_path = Path(args.reference_image).expanduser()
        continuity = dict(payload.get("continuity") or {})
        continuity["reference_image"] = str(ref_path)
        continuity.setdefault("_version", 2)
        payload["continuity"] = continuity
        edits_applied.append("reference_image")

    # Bump the edit counter so downstream caches invalidate.
    payload["edit_count"] = int(payload.get("edit_count", 0)) + 1
    payload["last_edit"] = {
        "scene": args.scene_index,
        "edits": edits_applied,
        "edited_at_s": time.time(),
    }

    out_path = Path(args.out) if args.out else sb_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str))

    # When --re-render is requested, actually invoke `viz generate` against the
    # edited storyboard + the user-specified render-out directory so a 1-scene
    # tweak doesn't force the user to remember + re-type the full pipeline
    # command. The orchestrator receives --only-scenes N so it only re-renders
    # that scene (plus any neighbor scenes the conductor is configured to
    # re-derive from the edit).
    re_render_invoked = False
    re_render_cmd: Optional[str] = None
    re_render_output: Optional[str] = None
    if getattr(args, "re_render", False):
        wav = getattr(args, "wav", None)
        if not wav:
            print(
                t("cli.error.wav_required_for_rerender"),
                file=sys.stderr,
            )
            return 2
        if not Path(wav).is_file():
            print(
                t("cli.error.missing_wav", wav=wav),
                file=sys.stderr,
            )
            return 2
        render_out = getattr(args, "render_out", None) or str(
            Path(out_path).parent / f"render_scene_{args.scene_index}"
        )
        cmd = [
            sys.executable,
            "-m",
            "melosviz.cli.main",
            "generate",
            wav,
            "--storyboard",
            str(out_path),
            "--only-scenes",
            str(args.scene_index),
            "--out",
            render_out,
        ]
        re_render_cmd = " ".join(cmd)
        # Emit the re-render hint to stdout so operators (and tests) can
        # see exactly which command to paste. We don't invoke the
        # subprocess directly here — that path requires ComfyUI / GPU and
        # would block the CLI for up to 15 minutes per scene. The user
        # pastes ``viz generate ...`` to opt in to the long-running
        # render.
        print(f"Re-render hint: {re_render_cmd}")
        re_render_output = render_out

    # Build the "next step" hint.
    if getattr(args, "re_render", False):
        if re_render_invoked:
            next_step = (
                f"viz assemble {re_render_output}  "
                f"# scene {args.scene_index} re-rendered into {re_render_output}"
            )
        else:
            scene_indices = [int(args.scene_index)]
            next_step = (
                f"viz generate {args.wav or '<wav>'} --storyboard {out_path} "
                f"--only-scenes {','.join(str(i) for i in scene_indices)}"
            )
            if getattr(args, "render_out", None):
                next_step += f" --out {args.render_out}"
            if getattr(args, "render_offline", False):
                next_step += " (set MELOSVIZ_COMFYUI_OFFLINE=1 to keep offline mode)"
    else:
        next_step = (
            "Re-run `viz generate <wav> --storyboard "
            f"{out_path}` to re-render all scenes, or pass "
            "--re-render next time to re-render just this one."
        )

    summary = {
        "storyboard": str(out_path),
        "out": str(out_path),
        "scene": args.scene_index,
        "edits_applied": edits_applied,
        "edit_count": payload["edit_count"],
        "next_step": next_step,
        "re_render_invoked": re_render_invoked,
        "re_render_command": re_render_cmd,
    }
    if re_render_invoked:
        summary["re_render_output"] = re_render_output
        summary["orchestrator_envelope"] = (
            orchestrator_envelope
            if "orchestrator_envelope" in locals()
            else None
        )
    print(json.dumps(summary, indent=2, default=str))
    return 0

def _cmd_generate(args: argparse.Namespace) -> int:
    """Run ComfyUI / C4D / Unreal / AE per scene based on a storyboard."""
    from melosviz.analysis.audio import spec_from_wav_rich
    from melosviz.conductor.orchestrator import Orchestrator
    from melosviz.i18n import t
    from melosviz.llm import Director, DirectorRequest

    wav_path = Path(args.wav)
    if not wav_path.exists():
        print(t("cli.error.file_not_found", cmd="generate", path=wav_path), file=sys.stderr)
        return 1

    # v2 (WBS-2): ``--reference-image`` is validated up-front so a typo'd
    # path aborts the render before any GPU time is spent.
    try:
        _ref_path = _resolve_reference_image(args, cmd="generate")
    except _CliReferenceImageError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    spec = spec_from_wav_rich(wav_path)
    spec_dict = spec.model_dump() if hasattr(spec, "model_dump") else dict(spec)

    # If a storyboard was given, overlay the Director's prompts onto the spec.
    if args.storyboard:
        sb_path = Path(args.storyboard)
        if not sb_path.exists():
            print(t("cli.error.file_not_found", cmd="generate", path=sb_path), file=sys.stderr)
            return 1
        sb = json.loads(sb_path.read_text())
        spec_dict["scene_segments"] = sb.get("scenes", spec_dict.get("scene_segments", []))
        spec_dict.setdefault("director_meta", {})
        spec_dict["director_meta"]["concept"] = sb.get("concept", "")
        spec_dict["director_meta"]["seed"] = sb.get("seed", 0)
        # Carry forward the storyboard-level continuity anchor (v2, WBS-2)
        # so an art-director who pinned a reference image when running
        # `viz storyboard --reference-image` doesn't have to re-type the
        # path at the generate stage.
        sb_continuity = sb.get("continuity")
        if isinstance(sb_continuity, dict) and (
            sb_continuity.get("reference_image")
            or sb_continuity.get("subject_token")
            or sb_continuity.get("env_token")
        ):
            spec_dict["continuity"] = sb_continuity
    else:
        # Inline storyboard from CLI args
        bpm = float(args.bpm) if args.bpm else float(spec_dict.get("bpm") or 120.0)
        key = str(args.key or spec_dict.get("key_signature") or "C")
        duration = float(spec_dict.get("duration_s") or 0.0)
        req = DirectorRequest(
            concept=args.concept or "abstract music visual",
            duration_s=duration,
            bpm=bpm,
            key=key,
            segments=list(spec_dict.get("scene_segments") or []),
            seed=args.seed,
        )
        board = Director(seed=args.seed).storyboard(req)
        spec_dict["scene_segments"] = [s.to_dict() for s in board.scenes]
        spec_dict["continuity"] = board.continuity.to_dict()

    # v2 (WBS-2): --reference-image CLI override. When the user passes a path,
    # it's stamped onto the spec's continuity block so the orchestrator's
    # scene-prep loop threads it into every scene as ``ip_adapter_image``.
    if getattr(args, "reference_image", None):
        ref_path = Path(args.reference_image).expanduser()
        continuity = dict(spec_dict.get("continuity") or {})
        continuity["reference_image"] = str(ref_path)
        continuity.setdefault("_version", 2)
        spec_dict["continuity"] = continuity

    # v2 (WBS-101..106): --character-root + --character (repeatable).
    # Populate the spec's ``character_root`` and ``characters`` fields so the
    # orchestrator can load the registry and pre-stamp every scene with
    # ``character_front`` / ``character_three_quarter`` / etc. before
    # dispatching to adapters. CLI overrides take precedence over
    # storyboard-level forwards, then the storyboard forwards take
    # precedence over spec defaults.
    char_root = (
        getattr(args, "character_root", None)
        or spec_dict.get("character_root")
    )
    char_names = getattr(args, "character", None) or spec_dict.get("characters")
    if char_root:
        spec_dict["character_root"] = str(Path(char_root).expanduser())
    if char_names:
        spec_dict["characters"] = list(char_names)

    # Re-validate spec via the v2 schema if possible
    try:
        from melosviz.analysis.models import RenderSpec
        spec = RenderSpec.model_validate(spec_dict)
    except Exception:
        spec = type("Spec", (), {"model_dump": lambda self: spec_dict, "__iter__": iter(())})

    out_dir = Path(args.out) if args.out else Path("./melosviz-out")
    job_id = args.job_id or f"job-{hash(str(out_dir)) & 0xFFFFFFFF:08x}"
    # Parse --only-scenes "1,3,5" -> {1,3,5}
    only_scenes = None
    if getattr(args, "only_scenes", None):
        only_scenes = {
            int(tok.strip()) for tok in args.only_scenes.split(",") if tok.strip()
        }
    orchestrator = Orchestrator(
        output_dir=out_dir,
        job_id=job_id,
        only_scenes=only_scenes,
        character_root=(
            Path(char_root).expanduser() if char_root else None
        ),
    )
    if char_names:
        orchestrator.set_active_characters(tuple(char_names))
    try:
        result = orchestrator.render(spec, audio_path=wav_path)  # type: ignore[arg-type]
    except Exception as exc:
        print(t("cli.error.generate_failed", error=str(exc)), file=sys.stderr)
        return 1

    summary = {
        "job_id": job_id,
        "output_dir": str(result.output_dir),
        "dispatched_scenes": sorted(result.per_scene_results.keys()),
        "only_scenes": sorted(only_scenes) if only_scenes else None,
        "assembly_ok": result.assembly_result is not None,
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _cmd_character(args: argparse.Namespace) -> int:
    """List or add named characters to a character-sheet registry on disk.

    ``viz character list`` walks ``--root DIR`` (default: cwd) and prints
    the resolved registry as JSON. ``viz character add`` writes a single
    :class:`CharacterSheet` to ``<root>/<name>.{yaml,json}`` (or
    ``<root>/<name>/sheet.{yaml,json}`` when ``--reference`` paths are
    given).
    """
    from melosviz.character import (
        CharacterSheet,
        load_registry,
        save_sheet,
        REFERENCE_SLOTS,
    )
    from melosviz.i18n import t

    root = Path(args.root).expanduser() if args.root else Path.cwd()
    if args.action == "list":
        reg = load_registry(root)
        out = {
            "root": str(root),
            "characters": reg.to_list(),
            "count": len(reg.names()),
        }
        print(json.dumps(out, indent=2, default=str))
        return 0

    # action == "add"
    name = (args.name or "").strip()
    if not name:
        print(t("cli.character.error.name_required"), file=sys.stderr)
        return 1

    references: dict[str, str] = {}
    slot_flags = {
        "front": args.front,
        "three_quarter": args.three_quarter,
        "profile": args.profile,
        "full_body": args.full_body,
        "style": args.style,
    }
    for slot in REFERENCE_SLOTS:
        v = slot_flags.get(slot)
        if v:
            references[slot] = str(Path(v).expanduser())

    # ``--reference PATH`` allows multiple arbitrary slot assignments.
    # ``front=PATH`` form targets a specific slot; bare paths fill the
    # first available slot (front, then style, then generic slot_N).
    if args.reference:
        for i, ref in enumerate(args.reference):
            if "=" in ref:
                slot_token, _, val = ref.partition("=")
                slot = slot_token.strip()
                val = val.strip()
                if slot in REFERENCE_SLOTS and val:
                    references[slot] = val
            else:
                if i == 0 and "front" not in references:
                    target = "front"
                elif "style" not in references:
                    target = "style"
                else:
                    target = f"slot_{i}"
                references[target] = ref

    sheet = CharacterSheet(
        name=name,
        description=(args.description or "").strip(),
        engine=(args.engine or "ipadapter").strip(),
        style_prompt=(args.style_prompt or "").strip(),
        references=references,
    )
    try:
        path = save_sheet(sheet, root)
    except Exception as exc:
        print(t("cli.character.error.save_failed", error=str(exc)), file=sys.stderr)
        return 1
    out = {
        "name": sheet.name,
        "engine": sheet.engine,
        "saved_to": str(path),
        "is_complete": sheet.is_complete,
        "reference_slots": {k: v for k, v in sheet.references.items() if v},
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _cmd_assemble(args: argparse.Namespace) -> int:
    """Concat per-scene clips into a master timeline via MediaEncoder / ffmpeg."""
    import os

    from melosviz.i18n import t

    out_dir = Path(args.out_dir)
    if not out_dir.exists():
        print(t("cli.error.dir_not_found", path=out_dir), file=sys.stderr)
        return 1

    # Find every per-scene file produced under the orchestrator output.
    segment_paths: list[Path] = []
    plan_paths: list[Path] = []
    for sub in sorted(out_dir.iterdir()):
        if not sub.is_dir():
            continue
        for f in sorted(sub.glob("*.mp4")):
            segment_paths.append(f)
        for f in sorted(sub.glob("*.mov")):
            segment_paths.append(f)
        # Recurse one level into scene_*/ for job_spec.json and per-scene plans.
        for f in sorted(sub.glob("*plan*.json")):
            plan_paths.append(f)
        for f in sorted(sub.rglob("*plan*.json")):
            if f not in plan_paths:
                plan_paths.append(f)
        for f in sorted(sub.rglob("job_spec.json")):
            if f not in plan_paths:
                plan_paths.append(f)

    target = out_dir / "assembly"
    target.mkdir(parents=True, exist_ok=True)

    # ---- Beat-aligned cut plan (always emitted) --------------------------
    # Pull the storyboard alongside the per-scene plans so the effects plan
    # can snap cuts to actual lyric / downbeat timestamps. Falls back to
    # equal-tempo grid when no storyboard is found (offline-mode is ok).
    from melosviz.compose.beat_cuts import (
        build_assemble_effects_plan,
        BeatCutConfig,
    )

    sb_path: Path | None = None
    for plan_path in plan_paths:
        try:
            payload = json.loads(plan_path.read_text())
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("scenes"), list):
            sb_path = plan_path
            break

    effects_plan = build_assemble_effects_plan(
        storyboard_path=sb_path,
        clip_paths=[str(p) for p in segment_paths],
        config=BeatCutConfig(
            strategy="cut_on_downbeat",
            bpm=None,           # taken from storyboard.concept_bpm if present
            snaps_to_lyric=True,
            crossfade_ms=120,
            min_gap_ms=180,
            max_cuts_per_scene=4,
        ),
    )
    effects_path = target / "effects.json"
    effects_path.write_text(json.dumps(effects_plan, indent=2, default=str))

    # ---- Interpolation bridge (RIFE/FILM/FlowMatching + ffmpeg minterpolate fallback)
    # Builds per-scene-pair ScenePair objects and emits an interpolation plan
    # alongside the effects.json so the assemble stage can chain fluid frames
    # between disparate scene renders. Runs even in offline mode — it just
    # emits a manifest pointing at the install commands.
    from melosviz.interpolation.engine import (
        InterpolationEngine,
        build_interpolation_bridge_for_assemble,
    )
    try:
        scene_paths: dict[str, Path] = {}
        for p in segment_paths:
            scene_paths.setdefault(p.stem, p)
        interp_dir = target / "interpolation"
        if scene_paths:
            bridge = build_interpolation_bridge_for_assemble(
                out_dir=interp_dir,
                scene_paths=scene_paths,
                insertion_count=int(getattr(args, "interp_frames", 4)),
                insertion_position="between",
            )
            (target / "interpolation_plan.json").write_text(
                json.dumps(bridge, indent=2, default=str)
            )
        else:
            InterpolationEngine(out_dir=interp_dir)
    except Exception as _exc:
        LOG.debug("interpolation bridge step skipped: %s", _exc)

    # ---- Offline mode: just emit an assembly plan ------------------------
    if os.environ.get("MELOSVIZ_COMFYUI_OFFLINE") == "1" or not segment_paths:
        plan = {
            "assembler": "ffmpeg_concat",
            "mode": "offline" if os.environ.get("MELOSVIZ_COMFYUI_OFFLINE") == "1" else "stub",
            "output_dir": str(target),
            "expected_inputs": [
                {"scene": p.parent.name, "plan": str(p)} for p in plan_paths
            ],
            "segment_count": len(segment_paths),
            "rendered_segment_count": len(segment_paths),
            "effects_plan": str(effects_path),
            "ffmpeg_cmd": (
                'ffmpeg -f concat -safe 0 '
                '-i <segments.txt> -c copy -shortest '
                f'{target}/rough_cut.mp4'
            ),
            "next_steps": [
                "Install ComfyUI / Cinema 4D / After Effects and run without offline mode to produce real clips.",
                "Or: assemble the per-scene .mp4 files manually and re-run with segments present.",
            ],
        }
        plan_path = target / "assembly_plan.json"
        plan_path.write_text(json.dumps(plan, indent=2, default=str))
        print(json.dumps(plan, indent=2, default=str))
        return 0

    from melosviz.render.mediaencoder_adapter import MEAdapter
    adapter = MEAdapter()
    try:
        result = adapter.render(None, output_path=target.parent, segment_paths=segment_paths)  # type: ignore[arg-type]
    except Exception as exc:
        print(t("cli.error.assemble_failed", error=str(exc)), file=sys.stderr)
        return 1

    print(json.dumps({"rough_cut": str(target / "rough_cut.mp4"), "adapter_result": str(result)}, indent=2, default=str))
    return 0


def _cmd_master(args: argparse.Namespace) -> int:
    """DaVinci Resolve colour + audio mix + master encode."""
    import os

    from melosviz.i18n import t

    edit_path = Path(args.edit)
    if not edit_path.exists():
        print(t("cli.error.file_not_found", cmd="master", path=edit_path), file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    lufs_target = getattr(args, "lufs_target", None) or None
    export_stems_flag = bool(getattr(args, "export_stems", False))
    audio_wav = Path(args.audio) if getattr(args, "audio", None) else None

    # ---- Offline mode: emit a master plan instead of running Resolve --------
    if os.environ.get("MELOSVIZ_COMFYUI_OFFLINE") == "1":
        from melosviz.render.audio_finishing import build_offline_master_plan

        plan = build_offline_master_plan(
            out_dir,
            lufs_target=lufs_target,
            export_stems_flag=export_stems_flag,
            audio_wav=audio_wav,
        )
        # Keep the legacy deliverables list shape so existing consumers don't break
        plan.setdefault(
            "deliverables_planned",
            [
                {"path": str(out_dir / "festival_prores.mov"), "codec": "ProRes 422 HQ", "use": "festival"},
                {"path": str(out_dir / "club_h264.mp4"), "codec": "H.264", "use": "club screens"},
                {"path": str(out_dir / "youtube_h264.mp4"), "codec": "H.264", "use": "YouTube"},
                {"path": str(out_dir / "audio_master.wav"), "codec": "PCM 24-bit 48k", "use": "audio stems"},
                {"path": str(out_dir / "captions.srt"), "codec": "SRT", "use": "captions"},
            ],
        )
        plan_path = out_dir / "master_plan.json"
        plan_path.write_text(json.dumps(plan, indent=2, default=str))
        print(json.dumps(plan, indent=2, default=str))
        return 0

    # ---- Online: ffmpeg loudnorm + stems (when available), else Resolve ----
    try:
        from melosviz.render.audio_finishing import ffmpeg_available, run_master as run_master_ffmpeg

        if ffmpeg_available() and (lufs_target or export_stems_flag):
            plan = run_master_ffmpeg(
                edit_path,
                out_dir,
                lufs_target=lufs_target,
                export_stems_flag=export_stems_flag,
                audio_wav=audio_wav,
                overwrite=False,
            )
            plan_path = out_dir / "master_plan.json"
            if not plan_path.exists():
                plan_path.write_text(json.dumps(plan, indent=2, default=str))
            print(json.dumps(plan, indent=2, default=str))
            return 0
    except Exception as exc:  # pragma: no cover — best-effort path
        print(t("cli.error.master_failed", error=str(exc)), file=sys.stderr)
        return 1

    # ---- Fallback: DaVinci Resolve adapter (unchanged behavior) -------------
    from melosviz.render.davinci_adapter import ResolveAdapter

    adapter = ResolveAdapter()
    try:
        result = adapter.render(edit_path, output_path=out_dir)
    except Exception as exc:
        print(t("cli.error.master_failed", error=str(exc)), file=sys.stderr)
        return 1
    print(json.dumps({"master_dir": str(out_dir), "result": str(result)}, indent=2, default=str))
    return 0


def _cmd_ship(args: argparse.Namespace) -> int:
    """Package final deliverables and portable festival-VJ cues."""
    from melosviz.export.package import build_delivery_package
    from melosviz.i18n import t

    job_dir = Path(args.job_dir)
    if not job_dir.is_dir():
        print(t("cli.error.dir_not_found", path=job_dir), file=sys.stderr)
        return 1
    try:
        payload = build_delivery_package(job_dir)
    except (OSError, ValueError) as exc:
        print(f"viz ship failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    """Entry-point for the ``viz`` console script.

    ``argv`` is optional and defaults to ``sys.argv[1:]``; tests pass it
    explicitly to avoid mutating process-global state.
    """
    from melosviz.i18n import t

    parser = argparse.ArgumentParser(
        prog="viz",
        description=t("cli.description"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # viz analyze
    p_analyze = sub.add_parser("analyze", help=t("cli.analyze.help"))
    p_analyze.add_argument("wav", help=t("cli.arg.wav.help"))

    # viz build
    p_build = sub.add_parser("build", help=t("cli.build.help"))
    p_build.add_argument("wav", help=t("cli.arg.wav.help"))
    p_build.add_argument("--out", metavar="DIR", help=t("cli.arg.out.help"))
    p_build.add_argument(
        "--real",
        action="store_true",
        help=t("cli.arg.real.help"),
    )

    # viz render
    p_render = sub.add_parser("render", help=t("cli.render.help"))
    p_render.add_argument("wav", help=t("cli.arg.wav.help"))
    p_render.add_argument("--out", metavar="DIR", help=t("cli.arg.out.render.help"))

    # viz diff
    p_diff = sub.add_parser("diff", help=t("cli.diff.help"))
    p_diff.add_argument("spec_a", help=t("cli.arg.spec_a.help"))
    p_diff.add_argument("spec_b", help=t("cli.arg.spec_b.help"))

    # viz apply
    p_apply = sub.add_parser("apply", help=t("cli.apply.help"))
    p_apply.add_argument("spec", help=t("cli.arg.spec.help"))
    p_apply.add_argument("preset", help=t("cli.arg.preset.help"))

    # melosviz serve
    p_serve = sub.add_parser("serve", help=t("cli.serve.help"))
    p_serve.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help=t("cli.arg.host.help"),
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=8000,
        metavar="PORT",
        help=t("cli.arg.port.help"),
    )

    # melosviz presets
    sub.add_parser("presets", help=t("cli.presets.help"))

    # melosviz version
    sub.add_parser("version", help=t("cli.version.help"))

    # ---- melosviz storyboard -------------------------------------------------
    p_sb = sub.add_parser("storyboard", help=t("cli.storyboard.help"))
    p_sb.add_argument("wav", help=t("cli.arg.wav.help"))
    p_sb.add_argument("--concept", default="abstract music visual", help=t("cli.arg.concept.help"))
    p_sb.add_argument("--bpm", type=float, default=None, help=t("cli.arg.bpm.help"))
    p_sb.add_argument("--key", default=None, help=t("cli.arg.key.help"))
    p_sb.add_argument("--seed", type=int, default=None, help=t("cli.arg.seed.help"))
    p_sb.add_argument("--palette", nargs="*", help=t("cli.arg.palette.help"))
    p_sb.add_argument("--lyrics", default=None, help=t("cli.arg.lyrics.help"))
    p_sb.add_argument(
        "--aspect-ratio",
        choices=[
            "festival_16x9_4k", "youtube_16x9_1080p", "club_9x16",
            "ig_9x16", "instagram_1x1", "cinema_21x9", "vertical_4x5",
        ],
        default=None,
        help=t("cli.arg.aspect_ratio.help"),
    )
    p_sb.add_argument(
        "--continuity-character",
        default=None,
        help=t("cli.arg.continuity_character.help"),
    )
    p_sb.add_argument(
        "--continuity-environment",
        default=None,
        help=t("cli.arg.continuity_environment.help"),
    )
    p_sb.add_argument(
        "--reference-image",
        metavar="PATH",
        default=None,
        help=t("cli.arg.reference_image.help"),
    )
    p_sb.add_argument(
        "--mood-board", nargs="*", metavar="IMG",
        default=None, help=t("cli.arg.moodboard.help"),
    )
    p_sb.add_argument(
        "--character-root",
        metavar="DIR",
        default=None,
        help=t("cli.arg.character_root.help"),
    )
    p_sb.add_argument(
        "--character",
        action="append",
        metavar="NAME",
        default=None,
        help=t("cli.arg.character.help"),
    )
    # WBS-108: opt-in flag to force audio-conditioned scene routing even
    # when no character anchor is pinned — useful for music videos where
    # the audio track should drive motion (Wan S2V / Seedance A2V).
    p_sb.add_argument(
        "--audio-conditioned-video",
        action="store_true",
        dest="audio_conditioned_video",
        default=False,
        help=t("cli.arg.audio_conditioned_video.help"),
    )
    p_sb.add_argument("--out", metavar="DIR", help=t("cli.arg.out.help"))

    # ---- melosviz generate ---------------------------------------------------
    p_gen = sub.add_parser("generate", help=t("cli.generate.help"))
    p_gen.add_argument("wav", help=t("cli.arg.wav.help"))
    p_gen.add_argument("--concept", default="abstract music visual", help=t("cli.arg.concept.help"))
    p_gen.add_argument("--storyboard", metavar="FILE", default=None,
                       help=t("cli.arg.storyboard.help"))
    p_gen.add_argument("--bpm", type=float, default=None, help=t("cli.arg.bpm.help"))
    p_gen.add_argument("--key", default=None, help=t("cli.arg.key.help"))
    p_gen.add_argument("--seed", type=int, default=None, help=t("cli.arg.seed.help"))
    p_gen.add_argument("--out", metavar="DIR", help=t("cli.arg.out.help"))
    p_gen.add_argument(
        "--job-id",
        metavar="ID",
        default=None,
        help="Optional render-job id used to tag live render events on the SSE bus (default: derived from spec hash).",
    )
    p_gen.add_argument(
        "--only-scenes",
        metavar="N[,N,M-K]",
        default=None,
        help="Restrict this generate call to specific scene indices (comma-separated, ranges like 3-5). When omitted, all scenes are dispatched. Used by `viz direct --re-render` so a one-scene edit only redoes scene N (+ neighbors when N-K/+K is also passed via MELOSVIZ_DIRECT_NEIGHBORS).",
    )
    p_gen.add_argument(
        "--reference-image",
        metavar="PATH",
        default=None,
        help=t("cli.arg.reference_image.help"),
    )
    p_gen.add_argument(
        "--character-root",
        metavar="DIR",
        default=None,
        help=t("cli.arg.character_root.help"),
    )
    p_gen.add_argument(
        "--character",
        action="append",
        metavar="NAME",
        default=None,
        help=t("cli.arg.character.help"),
    )

    # ---- melosviz character (registry of named characters) -------------------
    p_char = sub.add_parser("character", help=t("cli.character.help"))
    p_char.add_argument(
        "action",
        choices=["list", "add"],
        help=t("cli.character.arg.action.help"),
    )
    p_char.add_argument(
        "--root",
        metavar="DIR",
        default=None,
        help=t("cli.arg.character_root.help"),
    )
    p_char.add_argument(
        "--name",
        metavar="NAME",
        default=None,
        help=t("cli.character.arg.name.help"),
    )
    p_char.add_argument(
        "--description",
        metavar="TEXT",
        default=None,
        help=t("cli.character.arg.description.help"),
    )
    p_char.add_argument(
        "--engine",
        choices=["ipadapter", "pulid"],
        default=None,
        help=t("cli.character.arg.engine.help"),
    )
    p_char.add_argument(
        "--style-prompt",
        metavar="TEXT",
        default=None,
        help=t("cli.character.arg.style_prompt.help"),
    )
    p_char.add_argument(
        "--reference",
        action="append",
        metavar="PATH",
        default=None,
        help=t("cli.character.arg.reference.help"),
    )
    p_char.add_argument(
        "--front",
        metavar="PATH",
        default=None,
        help=t("cli.character.arg.front.help"),
    )
    p_char.add_argument(
        "--three-quarter",
        metavar="PATH",
        default=None,
        help=t("cli.character.arg.three_quarter.help"),
    )
    p_char.add_argument(
        "--profile",
        metavar="PATH",
        default=None,
        help=t("cli.character.arg.profile.help"),
    )
    p_char.add_argument(
        "--full-body",
        metavar="PATH",
        default=None,
        help=t("cli.character.arg.full_body.help"),
    )
    p_char.add_argument(
        "--style",
        metavar="PATH",
        default=None,
        help=t("cli.character.arg.style.help"),
    )

    # ---- melosviz assemble ---------------------------------------------------
    p_asm = sub.add_parser("assemble", help=t("cli.assemble.help"))
    p_asm.add_argument("out_dir", help=t("cli.arg.out_dir.help"))
    p_asm.add_argument(
        "--interp-frames",
        type=int,
        default=0,
        help=t("cli.arg.interp_frames.help"),
    )
    p_asm.add_argument(
        "--interp-backend",
        choices=["rife", "film", "flow_matching", "ffmpeg_minterpolate", "auto"],
        default="auto",
        help=t("cli.arg.interp_backend.help"),
    )

    # ---- melosviz master -----------------------------------------------------
    p_mas = sub.add_parser("master", help=t("cli.master.help"))
    p_mas.add_argument("edit", help=t("cli.arg.edit.help"))
    p_mas.add_argument("--out", metavar="DIR", required=True, help=t("cli.arg.out.help"))
    p_mas.add_argument(
        "--lufs-target",
        metavar="NAME",
        choices=["club_pa", "youtube", "broadcast_ebu_r128", "cinema_pulse"],
        default=None,
        help=t("cli.arg.lufs_target.help"),
    )
    p_mas.add_argument(
        "--export-stems",
        action="store_true",
        help=t("cli.arg.export_stems.help"),
    )
    p_mas.add_argument(
        "--audio",
        metavar="WAV",
        default=None,
        help=t("cli.arg.audio.help"),
    )

    # ---- melosviz ship --------------------------------------------------------
    p_ship = sub.add_parser("ship", help=t("cli.ship.help"))
    p_ship.add_argument("job_dir", help=t("cli.arg.job_dir.help"))

    # ---- melosviz direct (art-director single-scene edit) ---------------------
    p_direct = sub.add_parser(
        "direct",
        help=t("cli.direct.help"),
        description=t("cli.direct.description"),
    )
    p_direct.add_argument("storyboard", help=t("cli.direct.arg.storyboard.help"))
    p_direct.add_argument("--scene-index", type=int, required=True,
                          help=t("cli.direct.arg.scene_index.help"))
    p_direct.add_argument("--replace-prompt", default=None,
                          help=t("cli.direct.arg.replace_prompt.help"))
    p_direct.add_argument("--replace-camera", default=None,
                          help=t("cli.direct.arg.replace_camera.help"))
    p_direct.add_argument("--replace-name", default=None,
                          help=t("cli.direct.arg.replace_name.help"))
    p_direct.add_argument("--re-render", action="store_true",
                          help=t("cli.direct.arg.re_render.help"))
    p_direct.add_argument("--render-out", default=None,
                          help=t("cli.direct.arg.render_out.help"))
    p_direct.add_argument("--render-offline", action="store_true",
                          help=t("cli.direct.arg.render_offline.help"))
    p_direct.add_argument("--wav", default=None,
                          help=t("cli.direct.arg.wav.help"))
    p_direct.add_argument("--out", default=None,
                          help=t("cli.direct.arg.out.help"))
    p_direct.add_argument(
        "--reference-image",
        metavar="PATH",
        default=None,
        help=t("cli.arg.reference_image.help"),
    )

    args = parser.parse_args(argv)
    dispatch = {
        "analyze": _cmd_analyze,
        "build": _cmd_build,
        "render": _cmd_render,
        "storyboard": _cmd_storyboard,
        "generate": _cmd_generate,
        "character": _cmd_character,
        "assemble": _cmd_assemble,
        "master": _cmd_master,
        "ship": _cmd_ship,
        "direct": _cmd_direct,
        "diff": _cmd_diff,
        "apply": _cmd_apply,
        "serve": _cmd_serve,
        "presets": _cmd_presets,
        "version": _cmd_version,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":  # pragma: no cover
    main()
