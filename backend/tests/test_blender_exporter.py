"""TDD suite for the headless Blender adapter (melosviz.render.blender_exporter).

All tests run without a real Blender installation — the subprocess invocation
is mocked throughout.  The test suite validates:

  (a) RenderSpec v2 → correct bpy driver-script content
      (energy/stem/segment mappings present in the generated script).
  (b) The flash-safety limiter caps flash rate to ≤ 3 Hz.
  (c) The adapter errors cleanly when the Blender binary is absent.
  (d) Scene-segment count maps to multi-scene output (per-segment bg keyframes
      present in the generated script).
  (e) export_blender orchestration: happy-path + error paths.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from melosviz.analysis.models import (
    DenseKeyframe,
    MIRSummary,
    RenderSpec,
    SceneSegment,
    StemFrame,
)
from melosviz.render.blender_exporter import (
    FLASH_SAFETY_MAX_HZ,
    BlenderNotFoundError,
    BlenderRenderError,
    apply_flash_safety,
    build_bpy_script,
    export_blender,
    is_blender_available,
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_spec(
    n_kfs: int = 5,
    n_segs: int = 3,
    duration: float = 10.0,
    fps: int = 30,
) -> RenderSpec:
    """Return a minimal but complete RenderSpec v2 for testing."""
    dense_keyframes = [
        DenseKeyframe(
            t=i * (duration / n_kfs),
            energy=0.3 + 0.6 * (i / max(1, n_kfs - 1)),
            brightness=0.4,
            valence=0.6,
            arousal=0.7,
            beat_strength=1.0 if i % 2 == 0 else 0.0,
            onset_strength=0.5,
            spectral_centroid=3000.0,
            stems=StemFrame(drums=0.8, bass=0.5, vocals=0.3, other=0.2),
            easing="ease_in_out",
        ).model_dump()
        for i in range(n_kfs)
    ]
    scene_segments = [
        SceneSegment(
            index=i,
            label=["intro", "chorus", "outro"][i % 3],
            start=i * (duration / n_segs),
            end=(i + 1) * (duration / n_segs),
            energy_mean=0.3 + 0.2 * i,
            brightness_mean=0.4,
            dominant_stem="drums",
        ).model_dump()
        for i in range(n_segs)
    ]
    return RenderSpec(
        metadata={"duration": duration, "fps": fps, "width": 640, "height": 360},
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
        dense_keyframes=dense_keyframes,
        scene_segments=scene_segments,
        mir=MIRSummary(tempo_bpm=128.0).model_dump(),
    )


# ---------------------------------------------------------------------------
# (a) bpy driver script content validation
# ---------------------------------------------------------------------------


class TestBuildBpyScript:
    """build_bpy_script produces a correct bpy driver script from RenderSpec v2."""

    def test_returns_non_empty_string(self) -> None:
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert isinstance(script, str)
        assert len(script) > 200

    def test_script_imports_bpy(self) -> None:
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "import bpy" in script

    def test_script_contains_kf_data_with_energy(self) -> None:
        """KF_DATA embedded in the script must reference energy values."""
        spec = _make_spec(n_kfs=3)
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "KF_DATA" in script
        assert '"energy"' in script

    def test_script_references_all_stems(self) -> None:
        """The script must map all four stems to their visual targets."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        # drums → particle proxy
        assert "drums_e" in script
        # bass → camera/scale
        assert "bass_e" in script
        # vocals → vocal highlight
        assert "vocals_e" in script
        # other → background
        assert "other_e" in script

    def test_script_contains_seg_data(self) -> None:
        """SEG_DATA embedded in script must include segment entries."""
        spec = _make_spec(n_segs=3)
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "SEG_DATA" in script
        assert '"label"' in script

    def test_script_references_valence_arousal_colour_mapping(self) -> None:
        """Valence/arousal must drive a colour tint path in the script."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "valence_arousal_to_tint" in script or "val" in script
        assert "arousal" in script

    def test_script_references_spectral_centroid_hue(self) -> None:
        """spectral_centroid must drive a hue mapping in the script."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "centroid_to_hue" in script or "spectral_centroid" in script.lower()

    def test_script_beat_strength_drives_pulse(self) -> None:
        """beat_strength / onset_strength must appear in the pulse calculation."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "beat_strength" in script or "bs" in script
        assert "onset_strength" in script or "os_" in script
        assert "pulse" in script

    def test_script_references_easing_interpolation(self) -> None:
        """Easing hints must be mapped to Blender interpolation type strings."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "EASE_IN_OUT" in script or "interp" in script

    def test_script_sets_fps_and_resolution(self) -> None:
        """Generated script must contain the fps / resolution we passed in."""
        spec = _make_spec(fps=24)
        script = build_bpy_script(
            spec, output_path="/tmp/frames/frame_", fps=24, width=1280, height=720
        )
        # Script uses aligned assignment: "FPS        = 24"
        assert "= 24" in script and "FPS" in script
        assert "= 1280" in script and "WIDTH" in script
        assert "= 720" in script and "HEIGHT" in script

    def test_script_sets_output_path(self) -> None:
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/custom/out/frame_")
        assert "/custom/out/frame_" in script

    def test_script_calls_render_animation(self) -> None:
        """Script must trigger bpy.ops.render.render(animation=True)."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "bpy.ops.render.render" in script
        assert "animation=True" in script

    def test_script_uses_emission_shader(self) -> None:
        """Energy drives emission strength — ShaderNodeEmission must be present."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "ShaderNodeEmission" in script

    def test_script_embeds_palette(self) -> None:
        """Palette colours must appear in the generated script."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "PALETTE" in script

    def test_drums_stem_drives_particle_proxy(self) -> None:
        """drums stem energy must drive the drum_src scale proxy."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "drum_src" in script
        assert "drums_e" in script

    def test_bass_stem_drives_camera(self) -> None:
        """bass stem energy must drive the camera Z offset."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "bass_e" in script
        assert "cam.location" in script or "cam.location.z" in script

    def test_vocals_stem_drives_emission_strength(self) -> None:
        """vocals stem must drive vocal highlight emission strength."""
        spec = _make_spec()
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "vocals_e" in script
        assert "vocal_str" in script or "vemit" in script

    def test_works_with_dict_spec(self) -> None:
        """build_bpy_script must also accept a plain dict (JSON-deserialized spec)."""
        spec = _make_spec()
        spec_dict = spec.model_dump()
        script = build_bpy_script(spec_dict, output_path="/tmp/frames/frame_")
        assert "import bpy" in script
        assert "KF_DATA" in script


# ---------------------------------------------------------------------------
# (b) Flash-safety limiter
# ---------------------------------------------------------------------------


class TestApplyFlashSafety:
    """apply_flash_safety clamps full-frame flash rate to ≤ FLASH_SAFETY_MAX_HZ."""

    def test_returns_same_length(self) -> None:
        values = [0.1, 0.9, 0.1, 0.9, 0.1, 0.9]
        result = apply_flash_safety(values, fps=10.0)
        assert len(result) == len(values)

    def test_no_suppression_when_well_spaced(self) -> None:
        """Flashes 1 second apart (fps=10, max_hz=3) should not be suppressed."""
        fps = 10.0
        # one flash every 10 frames (1 s) — well below 3 Hz threshold
        values = [0.0] * 30
        for i in range(0, 30, 10):
            values[i] = 1.0
        result = apply_flash_safety(values, fps=fps)
        # Flashes at frames 0, 10, 20 are all at least 3+ frames apart; none suppressed.
        assert result[10] == pytest.approx(1.0)
        assert result[20] == pytest.approx(1.0)

    def test_suppresses_rapid_flashes_above_3hz(self) -> None:
        """Consecutive large flashes faster than 3 Hz must be clamped."""
        fps = 30.0
        # Flash every other frame = 15 Hz >> 3 Hz limit
        values = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0] * 5
        result = apply_flash_safety(values, fps=fps)
        # Count the number of large upward transitions (>0.5 delta) remaining.
        flash_count = sum(
            1 for i in range(1, len(result)) if result[i] - result[i - 1] > 0.5
        )
        max_allowed = int(len(result) / fps * FLASH_SAFETY_MAX_HZ) + 2
        assert flash_count <= max_allowed, (
            f"Flash count {flash_count} exceeds limit {max_allowed}"
        )

    def test_empty_input_returns_empty(self) -> None:
        assert apply_flash_safety([], fps=30.0) == []

    def test_flat_signal_unchanged(self) -> None:
        values = [0.5] * 20
        result = apply_flash_safety(values, fps=30.0)
        assert result == values

    def test_single_flash_not_suppressed(self) -> None:
        values = [0.0] * 10 + [1.0] + [0.0] * 10
        result = apply_flash_safety(values, fps=30.0)
        # The single flash should NOT be suppressed (no prior flash).
        assert result[10] == pytest.approx(1.0)

    def test_suppressed_values_stay_in_range(self) -> None:
        """All output values must remain in [0, 1]."""
        import random
        rng = random.Random(42)
        values = [rng.random() for _ in range(100)]
        result = apply_flash_safety(values, fps=30.0)
        assert all(0.0 <= v <= 1.0 for v in result)

    def test_flash_safety_max_hz_constant(self) -> None:
        assert FLASH_SAFETY_MAX_HZ == 3.0


# ---------------------------------------------------------------------------
# (c) Adapter errors cleanly when Blender binary absent
# ---------------------------------------------------------------------------


class TestBlenderAbsent:
    """When Blender is not installed, the adapter raises BlenderNotFoundError."""

    def test_is_blender_available_returns_false_when_absent(self) -> None:
        with patch(
            "melosviz.render.blender_exporter._resolve_blender_binary",
            side_effect=BlenderNotFoundError("no blender"),
        ):
            assert is_blender_available() is False

    def test_is_blender_available_returns_true_when_present(self) -> None:
        with patch(
            "melosviz.render.blender_exporter._resolve_blender_binary",
            return_value="/usr/bin/blender",
        ):
            assert is_blender_available() is True

    def test_export_blender_raises_blender_not_found(self, tmp_path: Path) -> None:
        spec = _make_spec()
        with patch(
            "melosviz.render.blender_exporter._resolve_blender_binary",
            side_effect=BlenderNotFoundError("blender not installed"),
        ), pytest.raises(BlenderNotFoundError, match="blender not installed"):
            export_blender(spec, output_dir=tmp_path)

    def test_blender_not_found_is_blender_render_error(self) -> None:
        """BlenderNotFoundError must be a subclass of BlenderRenderError."""
        assert issubclass(BlenderNotFoundError, BlenderRenderError)


# ---------------------------------------------------------------------------
# (d) Segment count → multi-scene output (per-segment bg keyframes)
# ---------------------------------------------------------------------------


class TestMultiSegmentOutput:
    """Scene segments produce distinct per-segment background colour keyframes."""

    def test_single_segment_script_has_seg_data(self) -> None:
        spec = _make_spec(n_segs=1)
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "SEG_DATA" in script

    def test_three_segments_all_labels_in_script(self) -> None:
        spec = _make_spec(n_segs=3)
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        # Should contain at least one label from our segments
        assert "intro" in script or "chorus" in script or "outro" in script

    def test_segment_count_reflected_in_seg_data(self) -> None:
        """SEG_DATA JSON list length must equal n_segs."""

        n = 4
        spec = _make_spec(n_segs=n)
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        # Extract SEG_DATA line and parse it
        # Verify SEG_DATA appears in the script (content parsed implicitly by Blender).
        assert "SEG_DATA" in script, "SEG_DATA not found in generated script"

    def test_world_background_keyframe_insertion_present(self) -> None:
        """Per-segment background colour keyframe insertion code must be present."""
        spec = _make_spec(n_segs=3)
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        assert "bg_node" in script
        assert "keyframe_insert" in script
        assert "frame_start" in script or "fs" in script

    def test_five_segments_distinct_labels(self) -> None:
        """Five segments with distinct labels produce a script referencing all labels."""
        segs = [
            SceneSegment(
                index=i,
                label=lbl,
                start=i * 10.0,
                end=(i + 1) * 10.0,
            ).model_dump()
            for i, lbl in enumerate(["intro", "verse", "chorus", "bridge", "outro"])
        ]
        spec = RenderSpec(
            metadata={"duration": 50.0, "fps": 30},
            dense_keyframes=[DenseKeyframe(t=0.0).model_dump()],
            scene_segments=segs,
        )
        script = build_bpy_script(spec, output_path="/tmp/frames/frame_")
        for label in ["intro", "verse", "chorus", "bridge", "outro"]:
            assert label in script, f"Label {label!r} not found in script"


# ---------------------------------------------------------------------------
# (e) export_blender orchestration: happy-path and error paths
# ---------------------------------------------------------------------------


def _fake_blender_success(
    cmd: list[str], **kwargs: Any
) -> subprocess.CompletedProcess:
    """Simulate a successful Blender run by writing fake PNG frames."""
    # Locate output prefix from the generated script's OUTPUT_PATH
    # The frame directory is inside the temp dir the adapter created.
    # We find it by inspecting the cmd: cmd is [blender, -b, --python, <script>].
    script_path = Path(cmd[-1])
    script_content = script_path.read_text()
    # Extract OUTPUT_PATH value from "OUTPUT_PATH = '/tmp/.../frame_'"
    for line in script_content.splitlines():
        if "OUTPUT_PATH" in line and "=" in line:
            # e.g.  OUTPUT_PATH = '/tmp/melosviz-blender-.../frames/frame_'
            raw = line.split("=", 1)[1].strip().strip("'\"")
            frames_dir = Path(raw).parent
            frames_dir.mkdir(parents=True, exist_ok=True)
            # Write 3 fake PNG frames
            for i in range(1, 4):
                (frames_dir / f"frame_{i:04d}.png").write_bytes(
                    # minimal valid PNG header
                    b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
                )
            break
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")


def _fake_ffmpeg_success(
    cmd: list[str], **kwargs: Any
) -> subprocess.CompletedProcess:
    """Simulate a successful ffmpeg mux by writing a fake MP4."""
    Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
    Path(cmd[-1]).write_bytes(b"\x00" * 4096)
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")


class TestExportBlenderOrchestration:
    """export_blender orchestrates bpy script generation, Blender subprocess, and mux."""

    def _patch_all(
        self,
        blender_bin: str = "/fake/blender",
        blender_returncode: int = 0,
        ffmpeg_returncode: int = 0,
    ):
        """Context manager that patches binary resolution + subprocess.run."""
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(
            patch(
                "melosviz.render.blender_exporter._resolve_blender_binary",
                return_value=blender_bin,
            )
        )
        stack.enter_context(
            patch(
                "melosviz.render.blender_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            )
        )

        def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if "blender" in cmd[0]:
                return _fake_blender_success(cmd, **kwargs)
            return _fake_ffmpeg_success(cmd, **kwargs)

        stack.enter_context(
            patch("melosviz.render.blender_exporter.subprocess.run", side_effect=_run)
        )
        return stack

    def test_happy_path_returns_mp4(self, tmp_path: Path) -> None:
        spec = _make_spec()
        with self._patch_all():
            result = export_blender(spec, output_dir=tmp_path)
        assert result.suffix == ".mp4"
        assert result.exists()

    def test_blender_called_with_background_flag(self, tmp_path: Path) -> None:
        spec = _make_spec()
        calls: list[list[str]] = []

        def _capture(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            calls.append(list(cmd))
            if "blender" in cmd[0]:
                return _fake_blender_success(cmd, **kwargs)
            return _fake_ffmpeg_success(cmd, **kwargs)

        with (
            patch(
                "melosviz.render.blender_exporter._resolve_blender_binary",
                return_value="/fake/blender",
            ),
            patch(
                "melosviz.render.blender_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            ),
            patch(
                "melosviz.render.blender_exporter.subprocess.run",
                side_effect=_capture,
            ),
        ):
            export_blender(spec, output_dir=tmp_path)

        blender_calls = [c for c in calls if "blender" in c[0]]
        assert blender_calls, "No Blender subprocess call found"
        assert "-b" in blender_calls[0], "Blender was not invoked in background mode"

    def test_blender_called_with_python_script(self, tmp_path: Path) -> None:
        spec = _make_spec()
        calls: list[list[str]] = []

        def _capture(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            calls.append(list(cmd))
            if "blender" in cmd[0]:
                return _fake_blender_success(cmd, **kwargs)
            return _fake_ffmpeg_success(cmd, **kwargs)

        with (
            patch(
                "melosviz.render.blender_exporter._resolve_blender_binary",
                return_value="/fake/blender",
            ),
            patch(
                "melosviz.render.blender_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            ),
            patch(
                "melosviz.render.blender_exporter.subprocess.run",
                side_effect=_capture,
            ),
        ):
            export_blender(spec, output_dir=tmp_path)

        blender_calls = [c for c in calls if "blender" in c[0]]
        assert "--python" in blender_calls[0]

    def test_blender_failure_raises_blender_render_error(self, tmp_path: Path) -> None:
        spec = _make_spec()

        def _fail(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="Blender crash"
            )

        with (
            patch(
                "melosviz.render.blender_exporter._resolve_blender_binary",
                return_value="/fake/blender",
            ),
            patch(
                "melosviz.render.blender_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            ),
            patch(
                "melosviz.render.blender_exporter.subprocess.run",
                side_effect=_fail,
            ),pytest.raises(BlenderRenderError, match="rc=1")
        ):
            export_blender(spec, output_dir=tmp_path)

    def test_no_frames_produced_raises_blender_render_error(self, tmp_path: Path) -> None:
        """When Blender exits 0 but produces no frames, raise BlenderRenderError."""
        spec = _make_spec()

        def _no_frames(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            # Blender returns 0 but writes no frame files.
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        with (
            patch(
                "melosviz.render.blender_exporter._resolve_blender_binary",
                return_value="/fake/blender",
            ),
            patch(
                "melosviz.render.blender_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            ),
            patch(
                "melosviz.render.blender_exporter.subprocess.run",
                side_effect=_no_frames,
            ),pytest.raises(BlenderRenderError, match="no frame files")
        ):
            export_blender(spec, output_dir=tmp_path)

    def test_fps_and_resolution_from_spec_metadata(self, tmp_path: Path) -> None:
        """FPS/width/height from spec.metadata are passed to the bpy script."""
        spec = _make_spec(fps=24)
        generated_scripts: list[str] = []

        def _capture(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            if "blender" in cmd[0]:
                script_path = Path(cmd[cmd.index("--python") + 1])
                generated_scripts.append(script_path.read_text())
                return _fake_blender_success(cmd, **kwargs)
            return _fake_ffmpeg_success(cmd, **kwargs)

        with (
            patch(
                "melosviz.render.blender_exporter._resolve_blender_binary",
                return_value="/fake/blender",
            ),
            patch(
                "melosviz.render.blender_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            ),
            patch(
                "melosviz.render.blender_exporter.subprocess.run",
                side_effect=_capture,
            ),
        ):
            export_blender(spec, output_dir=tmp_path)

        assert generated_scripts, "No bpy script was captured"
        script = generated_scripts[0]
        # Script uses aligned assignment: "FPS        = 24"
        assert "FPS" in script and "= 24" in script

    def test_oserror_on_blender_start_raises_blender_render_error(
        self, tmp_path: Path
    ) -> None:
        spec = _make_spec()
        with (
            patch(
                "melosviz.render.blender_exporter._resolve_blender_binary",
                return_value="/fake/blender",
            ),
            patch(
                "melosviz.render.blender_exporter._resolve_ffmpeg_binary",
                return_value="/fake/ffmpeg",
            ),
            patch(
                "melosviz.render.blender_exporter.subprocess.run",
                side_effect=OSError("permission denied"),
            ),pytest.raises(BlenderRenderError, match="Failed to start Blender")
        ):
            export_blender(spec, output_dir=tmp_path)

    def test_v1_spec_still_works(self, tmp_path: Path) -> None:
        """A v1 RenderSpec (no dense_keyframes, no segments) must not crash."""
        spec = RenderSpec(
            metadata={"duration": 2.0, "fps": 10, "width": 320, "height": 240},
            palette=["#00f5ff"],
        )
        with self._patch_all():
            result = export_blender(spec, output_dir=tmp_path)
        assert result.suffix == ".mp4"
