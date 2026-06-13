"""Minimal Python SDK client scaffold for Melosviz."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest

import httpx


class MelosvizSDKError(RuntimeError):
    """Raised when an SDK request fails."""


@dataclass(slots=True)
class MelosvizClient:
    """Small stdlib-based client for the Melosviz HTTP API."""

    base_url: str = "http://127.0.0.1:8000"
    timeout: float = 20.0

    def _request_json(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        request = urlrequest.Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=data,
            headers=dict(headers) if headers else {},
            method=method,
        )
        try:
            with urlrequest.urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except (urlerror.HTTPError, urlerror.URLError) as exc:
            raise MelosvizSDKError(str(exc)) from exc
        import json
        return json.loads(payload)

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/v1/health")

    def presets(self) -> list[dict[str, Any]]:
        return self._request_json("GET", "/v1/presets")

    @staticmethod
    def _encode_multipart(
        fields: Mapping[str, str],
        file_field: str = "file",
        file_name: str = "",
        file_bytes: bytes = b"",
        content_type: str = "audio/wav",
    ) -> tuple[bytes, str]:
        boundary = "----melosviz-sdk-boundary"
        parts: list[bytes] = []
        for key, value in fields.items():
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode(
                    "utf-8"
                )
            )
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{file_name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode(
                "utf-8"
            )
            + file_bytes
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        return b"".join(parts), boundary

    def visualize_audio(
        self,
        file_path: str | Path,
        theme: str = "dark_street",
        analysis: str = "full",
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        duration_sec: float = 30.0,
        export_format: str = "json",
        seed: int = 42,
    ) -> dict[str, Any]:
        path = Path(file_path)
        body, boundary = self._encode_multipart(
            fields={
                "theme": theme,
                "analysis": analysis,
                "fps": str(fps),
                "width": str(width),
                "height": str(height),
                "duration_sec": str(duration_sec),
                "export_format": export_format,
                "seed": str(seed),
            },
            file_field="file",
            file_name=path.name,
            file_bytes=path.read_bytes(),
        )
        return self._request_json(
            "POST",
            "/v1/audio/visualize",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )


def create_client(
    base_url: str = "http://127.0.0.1:8000",
    timeout: float = 20.0,
) -> MelosvizClient:
    return MelosvizClient(base_url=base_url, timeout=timeout)


class AsyncClient:
    """Asynchronous client for the Melosviz HTTP API.

    Uses :mod:`httpx` for async HTTP. A caller can inject a pre-built
    ``http_session`` (handy for testing or connection pooling); otherwise
    the client lazily creates and owns its own :class:`httpx.AsyncClient`,
    which is closed on :meth:`close` or context-manager exit.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 20.0,
        http_session: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._user_session = http_session
        self._owned_session: httpx.AsyncClient | None = None

    @property
    def http_session(self) -> httpx.AsyncClient:
        """Return the active :class:`httpx.AsyncClient`.

        Resolves to a caller-injected session if one was supplied at
        construction; otherwise lazily constructs an owned session bound
        to ``base_url`` / ``timeout``.
        """
        if self._user_session is not None:
            return self._user_session
        if self._owned_session is None:
            self._owned_session = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._owned_session

    async def close(self) -> None:
        """Close the owned session (if any). Injected sessions are left alone."""
        if self._owned_session is not None:
            await self._owned_session.aclose()
            self._owned_session = None

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            response = await self.http_session.request(
                method, path, json=json, params=params
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MelosvizSDKError(str(exc)) from exc
        return response.json()

    async def submit(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Submit a job spec and return the server's acknowledgement."""
        return await self._request_json("POST", "/v1/jobs", json=dict(spec))

    async def get_result(self, job_id: str) -> dict[str, Any]:
        """Fetch the result/status of a previously submitted job."""
        return await self._request_json("GET", f"/v1/jobs/{job_id}")

    async def list_jobs(self) -> list[dict[str, Any]]:
        """List all jobs known to the server."""
        return await self._request_json("GET", "/v1/jobs")


def create_async_client(
    base_url: str = "http://127.0.0.1:8000",
    timeout: float = 20.0,
    http_session: httpx.AsyncClient | None = None,
) -> AsyncClient:
    return AsyncClient(base_url=base_url, timeout=timeout, http_session=http_session)
