"""Tests for the P5 TouchDesigner runtime generator + bridge + overrides.

TDD protocol (failing first, then green):
(a) generator produces all 9 required operator groups (io/timeline/scene/
    fields/materials/mix/camera/ui/output).
(b) RenderSpec → operator params mapping correct (BPM→audio_clock,
    beats→beat_chops, scanner→fields, segments→section_dat,
    domains→domain_blend, palette→materials).
(c) Scanner specs wire into fields group with correct param propagation.
(d) Override export → round-trip (load/apply/diff) works correctly.
(e) OSC serialisation of timeline events and dense keyframes produces
    correct JSON-safe dicts.
(f) live_stage adapter no longer raises NotImplementedError.
(g) generate_network writes JSON + bootstrap + .toe stub to output_dir.
(h) apply_overrides patches nested params correctly.
(i) diff_overrides detects divergence from canonical.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_render_spec():  # type: ignore[return]
    """Build a minimal RenderSpec v2 for tests (no heavy audio deps)."""
    from melosviz.analysis.models import RenderSpec

    spec = RenderSpec(
        metadata={
            "source_audio": "test.wav",
            "duration": 60.0,
            "fps": 30,
            "width": 1920,
            "height": 1080,
            "estimated_bpm": 128.0,
        },
        palette=["#00f5ff", "#ff2fd5", "#8a75ff"],
        layers=[],
        keyframes=[],
    )
    # Inject v2 fields manually (pydantic allows extras / via __dict__ on model)
    object.__setattr__(spec, "dense_keyframes", [
        type("DK", (), {
            "t": 0.0, "energy": 0.7, "brightness": 0.6,
            "valence": 0.5, "arousal": 0.8,
            "beat_strength": 0.9, "onset_strength": 0.3,
            "spectral_centroid": 3200.0,
            "stems": {"drums": 0.8, "bass": 0.5, "vocals": 0.2, "other": 0.3},
            "easing": "ease_in_out",
        })(),
    ])
    object.__setattr__(spec, "timeline_events", [
        {"type": "beat", "t": 0.0, "strength": 0.9},
        {"type": "onset", "t": 0.47, "strength": 0.6},
        {"type": "section", "t": 32.0, "label": "drop", "segment_index": 1},
    ])
    object.__setattr__(spec, "scene_segments", [
        type("Seg", (), {
            "index": 0, "label": "intro", "start": 0.0, "end": 32.0,
            "mood": "calm", "dominant_stem": "bass",
        })(),
        type("Seg", (), {
            "index": 1, "label": "drop", "start": 32.0, "end": 60.0,
            "mood": "energetic", "dominant_stem": "drums",
        })(),
    ])
    return spec


def _scanner_spec():  # type: ignore[return]
    from melosviz.scene.models import (
        FalloffType,
        OcclusionMode,
        ScannerNoise,
        ScannerRotation,
        ScannerSpec,
        ScannerType,
    )

    class _Shape:
        cone_angle_deg = 30.0

    sc = ScannerSpec(
        scanner_id="test_scanner",
        type=ScannerType.ROTATING_CONE,
        rotation=ScannerRotation(bpm_locked=True, beats_per_rotation=4.0),
        noise=ScannerNoise(beat_pulse_gain=0.5),
        falloff=FalloffType.SMOOTHSTEP,
        occlusion=OcclusionMode.NONE,
    )
    # Inject shape (model may define it as optional)
    if not hasattr(sc, "shape") or sc.shape is None:
        object.__setattr__(sc, "shape", _Shape())
    return sc


# ---------------------------------------------------------------------------
# (a) Required operator groups present
# ---------------------------------------------------------------------------


class TestGeneratorGroups:
    def test_all_nine_groups_present(self) -> None:
        """generator must produce io/timeline/scene/fields/materials/mix/camera/ui/output."""
        from melosviz.runtime.touchdesigner.generator import (
            REQUIRED_GROUP_NAMES,
            render_spec_to_network,
        )

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        group_names = network.group_names()
        for required in REQUIRED_GROUP_NAMES:
            assert required in group_names, f"Missing required group: {required!r}"

    def test_group_count_matches_required(self) -> None:
        from melosviz.runtime.touchdesigner.generator import (
            REQUIRED_GROUP_NAMES,
            render_spec_to_network,
        )

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)
        assert len(network.groups) >= len(REQUIRED_GROUP_NAMES)

    def test_each_group_has_operators(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)
        for group in network.groups:
            assert len(group.operators) >= 1, (
                f"Group {group.name!r} has no operators"
            )


# ---------------------------------------------------------------------------
# (b) RenderSpec → operator param mapping
# ---------------------------------------------------------------------------


class TestParamMapping:
    def test_bpm_wired_to_audio_clock(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        timeline = network.find_group("timeline")
        assert timeline is not None

        clock = next((op for op in timeline.operators if op.name == "audio_clock"), None)
        assert clock is not None, "audio_clock operator missing from timeline group"
        assert clock.params.get("BPM_value") == 128.0

    def test_bpm_wired_to_beat_chops(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        timeline = network.find_group("timeline")
        beat_chops = next(
            (op for op in timeline.operators if op.name == "beat_chops"), None
        )
        assert beat_chops is not None
        assert beat_chops.params.get("BPM_value") == 128.0
        # Beat times extracted from timeline_events
        assert 0.0 in beat_chops.params.get("beat_times", [])

    def test_section_dat_populated_from_segments(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        timeline = network.find_group("timeline")
        section_dat = next(
            (op for op in timeline.operators if op.name == "section_dat"), None
        )
        assert section_dat is not None
        rows = section_dat.params.get("rows", [])
        assert len(rows) == 2
        labels = {r["label"] for r in rows}
        assert "intro" in labels
        assert "drop" in labels

    def test_palette_wired_into_materials(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        materials = network.find_group("materials")
        assert materials is not None

        photo_mat = next(
            (op for op in materials.operators if op.name == "photo_materials"), None
        )
        assert photo_mat is not None
        assert photo_mat.params.get("base_color") == "#00f5ff"

    def test_domain_blend_in_mix(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        mix = network.find_group("mix")
        assert mix is not None

        blend = next(
            (op for op in mix.operators if op.name == "domain_blend"), None
        )
        assert blend is not None
        # Photo domain should start at opacity 1.0
        assert blend.params.get("photo_opacity") == 1.0

    def test_meta_populated(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        assert network.meta.get("estimated_bpm") == 128.0
        assert network.meta.get("duration") == 60.0
        assert network.meta.get("palette") == ["#00f5ff", "#ff2fd5", "#8a75ff"]

    def test_wires_from_cross_group(self) -> None:
        """Beat_chops should receive input from audio_clock."""
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        timeline = network.find_group("timeline")
        beat_chops = next(op for op in timeline.operators if op.name == "beat_chops")
        assert "timeline/audio_clock" in beat_chops.wires_from


# ---------------------------------------------------------------------------
# (c) Scanner specs → fields group
# ---------------------------------------------------------------------------


class TestScannerWiring:
    def test_scanner_spec_propagated_to_fields(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        sc = _scanner_spec()
        network = render_spec_to_network(spec, scanner_specs=[sc])

        fields = network.find_group("fields")
        assert fields is not None

        scanner_op = next(
            (op for op in fields.operators if op.name == "scanner_1"), None
        )
        assert scanner_op is not None
        assert scanner_op.params.get("scanner_id") == "test_scanner"
        assert scanner_op.params.get("beats_per_rotation") == 4.0
        assert scanner_op.params.get("beat_pulse_gain") == 0.5

    def test_default_two_scanners_when_no_spec(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec, scanner_specs=None)

        fields = network.find_group("fields")
        scanner_ops = [op for op in fields.operators if op.name.startswith("scanner_")]
        assert len(scanner_ops) == 2

    def test_write_channels_present(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec, scanner_specs=None)

        fields = network.find_group("fields")
        scanner_1 = next(op for op in fields.operators if op.name == "scanner_1")
        channels = scanner_1.params.get("write_channels", [])
        for ch in ("reveal_splat", "hide_photo", "boost_wireframe", "edge_emission"):
            assert ch in channels

    def test_mask_composer_wired_from_scanners(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)

        fields = network.find_group("fields")
        composer = next(op for op in fields.operators if op.name == "mask_composer")
        # Composer should list scanners in wires_from
        assert any("scanner" in w for w in composer.wires_from)


# ---------------------------------------------------------------------------
# (d) Override round-trip
# ---------------------------------------------------------------------------


class TestOverrideRoundTrip:
    def test_export_and_load_roundtrip(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.overrides import (
            export_overrides,
            load_overrides,
        )

        params = {
            "fields.scanner_1.cone_angle_deg": 21.0,
            "mix.domain_blend.photo_opacity": 0.3,
            "camera.camera_rig.tz": 5.5,
        }
        path = tmp_path / "overrides.yaml"
        export_overrides(params, path)
        loaded = load_overrides(path)

        assert loaded["fields.scanner_1.cone_angle_deg"] == 21.0
        assert loaded["mix.domain_blend.photo_opacity"] == 0.3
        assert loaded["camera.camera_rig.tz"] == 5.5

    def test_apply_overrides_patches_params(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network
        from melosviz.runtime.touchdesigner.overrides import apply_overrides

        spec = _minimal_render_spec()
        network = render_spec_to_network(spec)
        network_dict = network.to_dict()

        overrides = {
            "camera.camera_rig.tz": 99.0,
            "mix.domain_blend.photo_opacity": 0.1,
        }
        patched = apply_overrides(network_dict, overrides)

        # Navigate to patched values
        camera_group = next(g for g in patched["groups"] if g["name"] == "camera")
        cam_rig = next(op for op in camera_group["operators"] if op["name"] == "camera_rig")
        assert cam_rig["params"]["tz"] == 99.0

        mix_group = next(g for g in patched["groups"] if g["name"] == "mix")
        blend = next(op for op in mix_group["operators"] if op["name"] == "domain_blend")
        assert blend["params"]["photo_opacity"] == 0.1

    def test_apply_overrides_does_not_mutate_original(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network
        from melosviz.runtime.touchdesigner.overrides import apply_overrides

        spec = _minimal_render_spec()
        network_dict = render_spec_to_network(spec).to_dict()
        original_json = json.dumps(network_dict)

        apply_overrides(network_dict, {"camera.camera_rig.tz": 999.0})
        assert json.dumps(network_dict) == original_json

    def test_diff_detects_divergence(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network
        from melosviz.runtime.touchdesigner.overrides import diff_overrides

        spec = _minimal_render_spec()
        network_dict = render_spec_to_network(spec).to_dict()

        overrides = {"camera.camera_rig.tz": 999.0}
        diff = diff_overrides(network_dict, overrides)

        assert "camera.camera_rig.tz" in diff
        entry = diff["camera.camera_rig.tz"]
        assert entry["canonical"] == 4.5  # from _build_camera_group default
        assert entry["override"] == 999.0

    def test_diff_empty_when_no_divergence(self) -> None:
        from melosviz.runtime.touchdesigner.generator import render_spec_to_network
        from melosviz.runtime.touchdesigner.overrides import diff_overrides

        spec = _minimal_render_spec()
        network_dict = render_spec_to_network(spec).to_dict()
        diff = diff_overrides(network_dict, {})
        assert diff == {}

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.overrides import load_overrides

        result = load_overrides(tmp_path / "nonexistent.yaml")
        assert result == {}


# ---------------------------------------------------------------------------
# (e) OSC/WS bridge serialisation
# ---------------------------------------------------------------------------


class TestBridgeSerialisation:
    def test_serialise_timeline_event_dict(self) -> None:
        from melosviz.runtime.touchdesigner.bridge import serialise_timeline_event

        ev = {"type": "beat", "t": 1.024, "strength": 0.9}
        result = serialise_timeline_event(ev)
        assert result["type"] == "beat"
        assert result["t"] == 1.024
        assert result["strength"] == 0.9

    def test_serialise_dense_keyframe_adds_type(self) -> None:
        from melosviz.runtime.touchdesigner.bridge import serialise_dense_keyframe

        kf = {"t": 0.5, "energy": 0.7, "beat_strength": 0.9}
        result = serialise_dense_keyframe(kf)
        assert result["type"] == "keyframe"
        assert result["t"] == 0.5

    def test_serialise_pydantic_style_event(self) -> None:
        from melosviz.runtime.touchdesigner.bridge import serialise_timeline_event

        class _Ev:
            type = "onset"
            t = 2.0
            strength = 0.6

            def model_dump(self) -> dict:
                return {"type": self.type, "t": self.t, "strength": self.strength}

        result = serialise_timeline_event(_Ev())
        assert result["type"] == "onset"

    def test_osc_encode_produces_valid_packet(self) -> None:
        """OSC packet must start with the address string, 4-byte aligned."""
        from melosviz.runtime.touchdesigner.bridge import _OscTransport

        transport = _OscTransport.__new__(_OscTransport)
        packet = transport._encode_osc("/melosviz/event", '{"type":"beat"}')
        # Address block: "/melosviz/event" + null padded to 4 bytes
        assert packet[:16] == b"/melosviz/event\x00"
        # Type tag block starts with ","
        assert b",s" in packet

    def test_stream_render_spec_sends_all_events(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """stream_render_spec must call _send_sync for every event."""
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        sent: list[dict] = []

        def _fake_send(self, payload):  # noqa: ANN001
            sent.append(payload)

        monkeypatch.setattr(TDBridge, "_send_sync", _fake_send)

        bridge = TDBridge(BridgeConfig(transport="osc"))
        spec = _minimal_render_spec()
        bridge.stream_render_spec(spec, realtime=False)

        # 3 timeline events + 1 dense keyframe = 4 messages
        assert len(sent) >= 4

    def test_stream_events_sorted_by_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from melosviz.runtime.touchdesigner.bridge import BridgeConfig, TDBridge

        sent: list[dict] = []

        def _fake_send(self, payload):  # noqa: ANN001
            sent.append(payload)

        monkeypatch.setattr(TDBridge, "_send_sync", _fake_send)

        bridge = TDBridge(BridgeConfig(transport="osc"))
        bridge.stream_render_spec(_minimal_render_spec(), realtime=False)

        times = [float(m.get("t", 0.0)) for m in sent]
        assert times == sorted(times)


# ---------------------------------------------------------------------------
# (f) live_stage adapter raises no NotImplementedError
# ---------------------------------------------------------------------------


class TestLiveStageAdapter:
    def test_adapter_does_not_raise_not_implemented(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.adapter import TDAdapter

        adapter = TDAdapter()
        spec = _minimal_render_spec()

        # Must not raise NotImplementedError
        result = adapter.render(spec, output_path=tmp_path)
        assert result is not None

    def test_adapter_scene_type_is_live_stage(self) -> None:
        from melosviz.runtime.touchdesigner.adapter import TDAdapter

        assert TDAdapter.scene_type == "live_stage"

    def test_adapter_returns_render_result(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.adapter import TDAdapter, TDRenderResult

        adapter = TDAdapter()
        result = adapter.render(_minimal_render_spec(), output_path=tmp_path)
        assert isinstance(result, TDRenderResult)

    def test_adapter_result_has_paths(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.adapter import TDAdapter

        result = TDAdapter().render(_minimal_render_spec(), output_path=tmp_path)
        assert result.network_spec_path is not None
        assert result.bootstrap_path is not None
        assert result.project_path is not None

    def test_adapter_live_mode_false_by_default(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.adapter import TDAdapter

        result = TDAdapter().render(_minimal_render_spec(), output_path=tmp_path)
        assert result.live_mode is False


# ---------------------------------------------------------------------------
# (g) generate_network writes files
# ---------------------------------------------------------------------------


class TestGenerateNetworkIO:
    def test_writes_network_spec_json(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.generator import generate_network

        result = generate_network(_minimal_render_spec(), output_dir=tmp_path)

        assert result.network_spec_path is not None
        assert result.network_spec_path.exists()
        parsed = json.loads(result.network_spec_path.read_text())
        assert "groups" in parsed
        assert parsed["version"] == "1.0"

    def test_writes_bootstrap_script(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.generator import generate_network

        result = generate_network(_minimal_render_spec(), output_dir=tmp_path)

        assert result.bootstrap_path is not None
        assert result.bootstrap_path.exists()
        content = result.bootstrap_path.read_text()
        assert "network_spec.json" in content
        # Bootstrap uses TD's op() global (not td.op — TD globals don't need prefix)
        assert "op(" in content or "_get_or_create_comp" in content

    def test_writes_toe_stub(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.generator import generate_network

        result = generate_network(_minimal_render_spec(), output_dir=tmp_path)

        assert result.project_path is not None
        assert result.project_path.exists()
        stub = json.loads(result.project_path.read_text())
        assert stub["format"] == "melosviz_toe_stub"

    def test_no_files_when_no_output_dir(self) -> None:
        from melosviz.runtime.touchdesigner.generator import generate_network

        result = generate_network(_minimal_render_spec(), output_dir=None)
        assert result.network_spec_path is None
        assert result.bootstrap_path is None
        assert result.project_path is None
        # But in-memory spec must be present
        assert result.network_spec is not None

    def test_network_spec_json_roundtrip(self, tmp_path: Path) -> None:
        from melosviz.runtime.touchdesigner.generator import (
            generate_network,
        )

        result = generate_network(_minimal_render_spec(), output_dir=tmp_path)
        raw = result.network_spec_path.read_text()
        parsed = json.loads(raw)

        group_names = [g["name"] for g in parsed["groups"]]
        from melosviz.runtime.touchdesigner.generator import REQUIRED_GROUP_NAMES

        for required in REQUIRED_GROUP_NAMES:
            assert required in group_names
