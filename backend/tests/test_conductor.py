"""Tests for melosviz.conductor — registry and orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_adapter_registry_is_non_empty_dict():
    from melosviz.conductor.registry import ADAPTER_REGISTRY

    assert isinstance(ADAPTER_REGISTRY, dict)
    assert len(ADAPTER_REGISTRY) > 0


def test_adapter_registry_keys_are_strings():
    from melosviz.conductor.registry import ADAPTER_REGISTRY

    for key in ADAPTER_REGISTRY:
        assert isinstance(key, str), f"Expected str key, got {type(key)}: {key!r}"


def test_adapter_registry_contains_expected_scene_types():
    from melosviz.conductor.registry import ADAPTER_REGISTRY

    required = {"video_export", "assembly_encode"}
    missing = required - ADAPTER_REGISTRY.keys()
    assert not missing, f"Missing registry keys: {missing}"


def test_adapter_registry_instances_have_render_method():
    """Each registered adapter must expose a 'render' callable."""
    from melosviz.conductor.registry import (
        _BlenderAdapterShim,
        _VideoExportAdapter,
    )

    # Only test the shim classes that are defined locally (no heavy imports).
    for cls in (_BlenderAdapterShim, _VideoExportAdapter):
        instance = cls()
        assert callable(getattr(instance, "render", None)), (
            f"{cls.__name__} must have a render() method"
        )


def test_shim_adapters_have_scene_type_attribute():
    from melosviz.conductor.registry import _BlenderAdapterShim, _VideoExportAdapter

    assert _BlenderAdapterShim.scene_type == "procedural_3d_animation"
    assert _VideoExportAdapter.scene_type == "video_export"


# ---------------------------------------------------------------------------
# Orchestrator construction tests
# ---------------------------------------------------------------------------


def test_orchestrator_default_output_dir():
    from melosviz.conductor.orchestrator import Orchestrator

    orch = Orchestrator()
    assert orch._output_dir == Path("/tmp/melosviz-conductor")


def test_orchestrator_custom_output_dir(tmp_path):
    from melosviz.conductor.orchestrator import Orchestrator

    orch = Orchestrator(output_dir=tmp_path)
    assert orch._output_dir == tmp_path


# ---------------------------------------------------------------------------
# Orchestrator render tests (mocked adapters)
# ---------------------------------------------------------------------------


def _minimal_spec_dict(**overrides):
    """Return a dict that quacks like a RenderSpec.model_dump() result."""
    base = {"scene_segments": [], "title": "test", "fps": 24}
    base.update(overrides)
    return base


def _make_mock_spec(scene_types: list[str] | None = None):
    """Return a mock RenderSpec with model_dump()."""
    spec = MagicMock()
    segs = [{"scene_type": st} for st in (scene_types or [])]
    spec.model_dump.return_value = {
        "scene_segments": segs,
        "title": "test",
        "fps": 24,
    }
    return spec


def test_render_empty_spec_falls_back_to_video_export(tmp_path):
    """When scene_segments is empty the orchestrator falls back to video_export."""
    from melosviz.conductor.orchestrator import Orchestrator

    mock_result = object()
    mock_adapter_instance = MagicMock()
    mock_adapter_instance.render.return_value = mock_result
    mock_adapter_cls = MagicMock(return_value=mock_adapter_instance)

    mock_assembly_instance = MagicMock()
    mock_assembly_instance.render.return_value = None
    mock_assembly_cls = MagicMock(return_value=mock_assembly_instance)

    patched_registry = {
        "video_export": mock_adapter_cls,
        "assembly_encode": mock_assembly_cls,
    }

    orch = Orchestrator(output_dir=tmp_path, skip_assembly=False)
    spec = _make_mock_spec([])

    # The import inside render() pulls from the module; patch that.
    with (
        patch(
            "melosviz.conductor.orchestrator.ADAPTER_REGISTRY",
            patched_registry,
            create=True,
        ),
        patch.dict("sys.modules", {}),
    ):
        import melosviz.conductor.registry as reg_mod

        original = reg_mod.ADAPTER_REGISTRY
        reg_mod.ADAPTER_REGISTRY = patched_registry
        try:
            result = orch.render(spec)
        finally:
            reg_mod.ADAPTER_REGISTRY = original

    assert "video_export" in result.per_scene_results


def test_render_unknown_scene_type_raises_conductor_error(tmp_path):
    """An unregistered scene_type must raise ConductorError loudly."""
    from melosviz.conductor import registry as reg_mod
    from melosviz.conductor.orchestrator import ConductorError, Orchestrator

    orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
    spec = _make_mock_spec(["nonexistent_scene_xyz"])

    original = reg_mod.ADAPTER_REGISTRY
    reg_mod.ADAPTER_REGISTRY = {}  # empty — nothing registered
    try:
        try:
            orch.render(spec)
            assert False, "Expected ConductorError"
        except ConductorError as exc:
            assert "nonexistent_scene_xyz" in str(exc)
    finally:
        reg_mod.ADAPTER_REGISTRY = original


def test_render_with_known_scene_type_dispatches_adapter(tmp_path):
    """render() must call adapter_cls() then adapter.render() for matched scene type."""
    from melosviz.conductor import registry as reg_mod
    from melosviz.conductor.orchestrator import Orchestrator

    mock_result = {"frames": 100}
    mock_adapter_instance = MagicMock()
    mock_adapter_instance.render.return_value = mock_result
    mock_adapter_cls = MagicMock(return_value=mock_adapter_instance)

    patched = {"video_export": mock_adapter_cls}
    original = reg_mod.ADAPTER_REGISTRY
    reg_mod.ADAPTER_REGISTRY = patched
    try:
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        spec = _make_mock_spec(["video_export"])
        result = orch.render(spec)
    finally:
        reg_mod.ADAPTER_REGISTRY = original

    assert result.per_scene_results["video_export"] is mock_result
    mock_adapter_cls.assert_called_once()
    mock_adapter_instance.render.assert_called_once()


def test_render_skip_assembly_omits_assembly_step(tmp_path):
    """skip_assembly=True must skip calling the assembly_encode adapter."""
    from melosviz.conductor import registry as reg_mod
    from melosviz.conductor.orchestrator import Orchestrator

    mock_video_instance = MagicMock()
    mock_video_instance.render.return_value = {}
    mock_video_cls = MagicMock(return_value=mock_video_instance)

    assembly_cls = MagicMock()

    patched = {"video_export": mock_video_cls, "assembly_encode": assembly_cls}
    original = reg_mod.ADAPTER_REGISTRY
    reg_mod.ADAPTER_REGISTRY = patched
    try:
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        spec = _make_mock_spec(["video_export"])
        result = orch.render(spec)
    finally:
        reg_mod.ADAPTER_REGISTRY = original

    assembly_cls.assert_not_called()
    assert result.assembly_result is None


def test_render_adapter_exception_wrapped_as_conductor_error(tmp_path):
    """Adapter exception must be wrapped in ConductorError with scene context."""
    from melosviz.conductor import registry as reg_mod
    from melosviz.conductor.orchestrator import ConductorError, Orchestrator

    boom_instance = MagicMock()
    boom_instance.render.side_effect = RuntimeError("adapter exploded")
    boom_cls = MagicMock(return_value=boom_instance)

    patched = {"video_export": boom_cls}
    original = reg_mod.ADAPTER_REGISTRY
    reg_mod.ADAPTER_REGISTRY = patched
    try:
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        spec = _make_mock_spec(["video_export"])
        try:
            orch.render(spec)
            assert False, "Expected ConductorError"
        except ConductorError as exc:
            assert "video_export" in str(exc)
            assert "adapter exploded" in str(exc)
    finally:
        reg_mod.ADAPTER_REGISTRY = original


def test_render_assembly_encode_scene_type_skipped_in_dispatch(tmp_path):
    """assembly_encode as a scene_type in scene_segments must NOT be dispatched inline."""
    from melosviz.conductor import registry as reg_mod
    from melosviz.conductor.orchestrator import Orchestrator

    assembly_instance = MagicMock()
    assembly_instance.render.return_value = None
    assembly_cls = MagicMock(return_value=assembly_instance)

    patched = {"assembly_encode": assembly_cls}
    original = reg_mod.ADAPTER_REGISTRY
    reg_mod.ADAPTER_REGISTRY = patched
    try:
        orch = Orchestrator(output_dir=tmp_path, skip_assembly=True)
        spec = _make_mock_spec(["assembly_encode"])
        result = orch.render(spec)
    finally:
        reg_mod.ADAPTER_REGISTRY = original

    # assembly_encode should NOT appear in per_scene_results (it's skipped inline)
    assert "assembly_encode" not in result.per_scene_results
    # And the assembly_cls should not have been called for per-scene dispatch
    # (skip_assembly=True so it won't be called at all)
    assembly_cls.assert_not_called()


def test_orchestrator_result_attributes(tmp_path):
    """OrchestratorResult stores per_scene_results, assembly_result, output_dir."""
    from melosviz.conductor.orchestrator import OrchestratorResult

    r = OrchestratorResult(
        per_scene_results={"video_export": "ok"},
        assembly_result="assembled",
        output_dir=tmp_path,
    )
    assert r.per_scene_results == {"video_export": "ok"}
    assert r.assembly_result == "assembled"
    assert r.output_dir == tmp_path
