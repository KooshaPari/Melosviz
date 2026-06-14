"""Tests for the backend SDK client (mock HTTP).

Uses :mod:`unittest.mock` to exercise the Melosviz SDK client's
submit/get/list surface without hitting a live server.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the SDK source tree is on the path when tests run from the backend
# directory (which does not install the SDK as an editable package).
SDK_SRC = Path(__file__).resolve().parents[2] / "sdk" / "python" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from melosviz_sdk.client import (
    AsyncClient,
    MelosvizClient,
    MelosvizSDKError,
    create_async_client,
)

BASE_URL = "http://testserver"


# ---------------------------------------------------------------------------
# AsyncClient — submit / get_result / list_jobs (unittest.mock)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_posts_spec_to_jobs_endpoint() -> None:
    """submit() POSTs the spec to /v1/jobs and returns the parsed JSON."""
    fake_response = MagicMock()
    fake_response.json.return_value = {"job_id": "job-123", "status": "queued"}
    fake_response.raise_for_status = MagicMock()

    fake_session = AsyncMock()
    fake_session.request = AsyncMock(return_value=fake_response)

    client = AsyncClient(base_url=BASE_URL, http_session=fake_session)
    result = await client.submit(
        {"input": "audio.wav", "preset": "dark_street"}
    )

    assert result == {"job_id": "job-123", "status": "queued"}
    fake_session.request.assert_awaited_once()
    args, kwargs = fake_session.request.call_args
    assert args[0] == "POST"
    assert args[1] == "/v1/jobs"
    assert kwargs.get("json") == {"input": "audio.wav", "preset": "dark_street"}
    fake_response.raise_for_status.assert_called_once()
    fake_response.json.assert_called_once()


@pytest.mark.asyncio
async def test_get_result_fetches_job_by_id() -> None:
    """get_result() GETs /v1/jobs/{job_id} and returns the parsed JSON."""
    fake_response = MagicMock()
    fake_response.json.return_value = {"job_id": "job-abc", "status": "done"}
    fake_response.raise_for_status = MagicMock()

    fake_session = AsyncMock()
    fake_session.request = AsyncMock(return_value=fake_response)

    client = AsyncClient(base_url=BASE_URL, http_session=fake_session)
    result = await client.get_result("job-abc")

    assert result == {"job_id": "job-abc", "status": "done"}
    fake_session.request.assert_awaited_once()
    args, kwargs = fake_session.request.call_args
    assert args[0] == "GET"
    assert args[1] == "/v1/jobs/job-abc"
    fake_response.raise_for_status.assert_called_once()
    fake_response.json.assert_called_once()


@pytest.mark.asyncio
async def test_list_jobs_returns_all_jobs() -> None:
    """list_jobs() GETs /v1/jobs and returns the parsed list."""
    fake_response = MagicMock()
    fake_response.json.return_value = [
        {"job_id": "a"},
        {"job_id": "b"},
    ]
    fake_response.raise_for_status = MagicMock()

    fake_session = AsyncMock()
    fake_session.request = AsyncMock(return_value=fake_response)

    client = AsyncClient(base_url=BASE_URL, http_session=fake_session)
    result = await client.list_jobs()

    assert result == [{"job_id": "a"}, {"job_id": "b"}]
    fake_session.request.assert_awaited_once()
    args, kwargs = fake_session.request.call_args
    assert args[0] == "GET"
    assert args[1] == "/v1/jobs"
    fake_response.raise_for_status.assert_called_once()
    fake_response.json.assert_called_once()


@pytest.mark.asyncio
async def test_http_error_raises_sdk_error() -> None:
    """HTTP errors are wrapped in MelosvizSDKError."""
    import httpx

    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error",
        request=httpx.Request("GET", "/v1/jobs"),
        response=None,  # type: ignore[arg-type]
    )

    fake_session = AsyncMock()
    fake_session.request = AsyncMock(return_value=fake_response)

    client = AsyncClient(base_url=BASE_URL, http_session=fake_session)
    with pytest.raises(MelosvizSDKError):
        await client.list_jobs()


@pytest.mark.asyncio
async def test_network_error_raises_sdk_error() -> None:
    """Network errors are wrapped in MelosvizSDKError."""
    import httpx

    fake_session = AsyncMock()
    fake_session.request = AsyncMock(side_effect=httpx.ConnectError("nope"))

    client = AsyncClient(base_url=BASE_URL, http_session=fake_session)
    with pytest.raises(MelosvizSDKError):
        await client.list_jobs()


# ---------------------------------------------------------------------------
# Sync client (MelosvizClient) — health / presets (unittest.mock)
# ---------------------------------------------------------------------------


def test_sync_client_health() -> None:
    """health() GETs /v1/health and returns the parsed JSON."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"status": "ok"}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch(
        "melosviz_sdk.client.urlrequest.urlopen", return_value=mock_response
    ):
        client = MelosvizClient(base_url="http://testserver")
        result = client.health()

    assert result == {"status": "ok"}


def test_sync_client_presets() -> None:
    """presets() GETs /v1/presets and returns the parsed JSON."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'[{"name": "dark_street"}]'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch(
        "melosviz_sdk.client.urlrequest.urlopen", return_value=mock_response
    ):
        client = MelosvizClient(base_url="http://testserver")
        result = client.presets()

    assert result == [{"name": "dark_street"}]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_create_async_client_returns_async_client() -> None:
    """create_async_client() returns a properly configured AsyncClient."""
    client = create_async_client(base_url=BASE_URL, timeout=5.0)
    assert isinstance(client, AsyncClient)
    assert client.base_url == BASE_URL
    assert client.timeout == 5.0
    assert client._user_session is None
    assert client._owned_session is None
