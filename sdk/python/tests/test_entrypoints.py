"""Smoke tests for the Melosviz Python SDK entrypoints."""

from melosviz_sdk import MelosvizClient, MelosvizSDKError, create_client


def test_python_sdk_exports() -> None:
    client = create_client()
    assert isinstance(client, MelosvizClient)
    assert client.base_url.startswith("http")
    assert MelosvizSDKError.__name__ == "MelosvizSDKError"
