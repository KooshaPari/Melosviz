"""Tests for the Melosviz SDK async client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from melosviz_sdk.client import (
    AsyncClient,
    MelosvizSDKError,
    create_async_client,
)


BASE_URL = "http://testserver"


# ---------------------------------------------------------------------------
# respx-based tests (mock at the transport layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_posts_spec_to_jobs_endpoint() -> None:
    client = AsyncClient(base_url=BASE_URL)
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as router:
        route = router.post("/v1/jobs").mock(
            return_value=httpx.Response(
                200, json={"job_id": "job-123", "status": "queued"}
            )
        )
        result = await client.submit(
            {"input": "audio.wav", "preset": "dark_street"}
        )

    assert result == {"job_id": "job-123", "status": "queued"}
    assert route.called
    last_request = route.calls.last.request
    assert last_request.method == "POST"
    assert last_request.url.path == "/v1/jobs"
    assert json.loads(last_request.read()) == {
        "input": "audio.wav",
        "preset": "dark_street",
    }


@pytest.mark.asyncio
async def test_get_result_fetches_job() -> None:
    client = AsyncClient(base_url=BASE_URL)
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as router:
        route = router.get("/v1/jobs/job-abc").mock(
            return_value=httpx.Response(
                200, json={"job_id": "job-abc", "status": "done"}
            )
        )
        result = await client.get_result("job-abc")

    assert result == {"job_id": "job-abc", "status": "done"}
    assert route.called
    assert route.calls.last.request.url.path == "/v1/jobs/job-abc"


@pytest.mark.asyncio
async def test_list_jobs_returns_list() -> None:
    client = AsyncClient(base_url=BASE_URL)
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as router:
        route = router.get("/v1/jobs").mock(
            return_value=httpx.Response(
                200, json=[{"job_id": "a"}, {"job_id": "b"}]
            )
        )
        result = await client.list_jobs()

    assert result == [{"job_id": "a"}, {"job_id": "b"}]
    assert route.called
    assert route.calls.last.request.url.path == "/v1/jobs"


@pytest.mark.asyncio
async def test_http_error_raises_sdk_error() -> None:
    client = AsyncClient(base_url=BASE_URL)
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v1/jobs").mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(MelosvizSDKError):
            await client.list_jobs()


@pytest.mark.asyncio
async def test_network_error_raises_sdk_error() -> None:
    client = AsyncClient(base_url=BASE_URL)
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v1/jobs").mock(
            side_effect=httpx.ConnectError("nope")
        )
        with pytest.raises(MelosvizSDKError):
            await client.list_jobs()


# ---------------------------------------------------------------------------
# Async context manager behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_manager_yields_self() -> None:
    async with AsyncClient(base_url=BASE_URL) as ctx:
        assert ctx is not None
        assert isinstance(ctx, AsyncClient)


@pytest.mark.asyncio
async def test_context_manager_closes_owned_session() -> None:
    client = AsyncClient(base_url=BASE_URL)
    async with client as ctx:
        # Touch http_session so the owned client is materialised.
        session = client.http_session
        assert isinstance(session, httpx.AsyncClient)
        assert client._owned_session is session
        assert client._user_session is None
    # After exit the owned session is closed and the slot is cleared.
    assert client._owned_session is None


@pytest.mark.asyncio
async def test_close_is_idempotent_without_owned_session() -> None:
    client = AsyncClient(base_url=BASE_URL)
    # Never materialised - close should be a safe no-op.
    await client.close()
    await client.close()
    assert client._owned_session is None


@pytest.mark.asyncio
async def test_context_manager_does_not_close_injected_session() -> None:
    injected = AsyncMock(spec=httpx.AsyncClient)
    client = AsyncClient(base_url=BASE_URL, http_session=injected)
    async with client:
        # http_session should resolve to the injected one.
        assert client.http_session is injected
    # Injected session must not be closed by the context manager.
    injected.aclose.assert_not_awaited()
    # The owned slot must remain untouched.
    assert client._owned_session is None


# ---------------------------------------------------------------------------
# http_session injection (unittest.mock)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_injected_http_session_is_used_and_request_serialised() -> None:
    """When a custom http_session is supplied the client must use it
    directly, serialising the spec as the ``json`` kwarg and decoding the
    response via :meth:`json`."""

    fake_response = MagicMock()
    fake_response.json.return_value = {"job_id": "injected", "status": "queued"}
    fake_response.raise_for_status = MagicMock()

    fake_session = AsyncMock()
    fake_session.request = AsyncMock(return_value=fake_response)

    client = AsyncClient(base_url="http://anywhere", http_session=fake_session)
    result = await client.submit({"foo": "bar"})

    assert result == {"job_id": "injected", "status": "queued"}
    fake_session.request.assert_awaited_once()
    args, kwargs = fake_session.request.call_args
    assert args[0] == "POST"
    assert args[1] == "/v1/jobs"
    assert kwargs.get("json") == {"foo": "bar"}
    fake_response.raise_for_status.assert_called_once()
    fake_response.json.assert_called_once()


@pytest.mark.asyncio
async def test_injected_session_http_error_is_wrapped() -> None:
    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=httpx.Request("GET", "/v1/jobs/missing"), response=None  # type: ignore[arg-type]
    )

    fake_session = AsyncMock()
    fake_session.request = AsyncMock(return_value=fake_response)

    client = AsyncClient(base_url="http://anywhere", http_session=fake_session)
    with pytest.raises(MelosvizSDKError):
        await client.get_result("missing")


# ---------------------------------------------------------------------------
# create_async_client factory
# ---------------------------------------------------------------------------


def test_create_async_client_returns_async_client() -> None:
    client = create_async_client(base_url=BASE_URL, timeout=5.0)
    assert isinstance(client, AsyncClient)
    assert client.base_url == BASE_URL
    assert client.timeout == 5.0
    assert client._user_session is None
    assert client._owned_session is None
