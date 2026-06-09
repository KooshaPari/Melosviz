"""Python client for Melosviz API."""

from __future__ import annotations

from pathlib import Path

import requests

from melosviz.analysis.models import AnalysisResult, RenderStyle, VisualizeRequest, VisualizeResponse


class MelosvizClient:
    """Simple HTTP client for analysis and visualization endpoints."""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _request_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def analyze(self, audio_path: str, **kwargs) -> AnalysisResult:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, "audio/wav")}
            response = requests.post(
                f"{self.base_url}/v1/audio/analyze",
                files=files,
                data=kwargs,
                headers=self._request_headers(),
                timeout=120,
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Analyze request failed: {response.status_code} {response.text}"
            )
        return AnalysisResult.model_validate(response.json())

    def visualize(self, audio_path: str, style: RenderStyle, **kwargs) -> VisualizeResponse:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        request = VisualizeRequest(source_file=str(path), style=style, **kwargs)
        payload = request.model_dump_json()
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, "audio/wav")}
            response = requests.post(
                f"{self.base_url}/v1/audio/visualize",
                files=files,
                data={"payload": payload},
                headers=self._request_headers(),
                timeout=120,
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Visualize request failed: {response.status_code} {response.text}"
            )
        return VisualizeResponse.model_validate(response.json())
