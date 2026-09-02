"""Contract tests for the offline GPU smoke GitHub workflow.

The workflow must support both a weekly scheduled run (so unattended CI
catches regressions) and a manual ``workflow_dispatch`` trigger (so an
operator can re-run it on demand).  Because the scheduled trigger does
not provide any ``inputs.*`` context, every env-var / input reference in
the workflow body has to be event-safe — the tests below pin that
contract.

If any of these contracts are broken (workflow_dispatch removed,
schedule cron edited, env defaults dropped) the tests will fail and the
PR will be blocked.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "gpu-smoke.yml"


def _read_workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_gpu_smoke_supports_manual_and_weekly_runs() -> None:
    text = _read_workflow()
    # Manual trigger must remain.
    assert "workflow_dispatch:" in text, "workflow_dispatch trigger missing"
    # Weekly schedule: Mondays at 08:17 UTC (cron must be quoted as a YAML
    # string or GitHub treats the leading 0 as octal in some shells).
    assert "schedule:" in text, "schedule trigger missing"
    assert "17 8 * * 1" in text, "weekly cron '17 8 * * 1' missing"


def test_scheduled_run_has_explicit_defaults() -> None:
    text = _read_workflow()
    # Event-safe env defaults so the scheduled run doesn't blow up on
    # the missing inputs.* context.
    assert "PYTHON_VERSION:" in text
    assert "INSTALL_FFMPEG:" in text
    # Offline-mode stays on so the smoke doesn't require a live GPU.
    assert "MELOSVIZ_COMFYUI_OFFLINE: '1'" in text
    # The actual smoke target is unchanged.
    assert "tests/cli/test_gpu_smoke.py" in text


def test_manifest_artifacts_are_uploaded() -> None:
    """On failure the workflow must upload the manifest artifacts so the
    operator can inspect what happened without re-running the job."""
    text = _read_workflow()
    assert "actions/upload-artifact" in text
    assert "smoke-output" in text
