"""Minimal Python SDK client scaffold for Melosviz."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest


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
