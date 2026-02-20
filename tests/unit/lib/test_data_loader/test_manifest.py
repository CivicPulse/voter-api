"""Unit tests for the manifest fetcher."""

import json
from datetime import UTC

import httpx
import pytest

from voter_api.lib.data_loader.manifest import fetch_manifest
from voter_api.lib.data_loader.types import FileCategory


def _make_manifest_json(
    *,
    version: str = "1",
    updated_at: str = "2026-02-20T09:00:00Z",
    files: list[dict] | None = None,
) -> str:
    """Build a valid manifest JSON string."""
    if files is None:
        files = [
            {
                "filename": "test.zip",
                "sha512": "a" * 128,
                "category": "boundary",
                "size_bytes": 1024,
            }
        ]
    return json.dumps({"version": version, "updated_at": updated_at, "files": files})


@pytest.mark.asyncio
class TestFetchManifest:
    """Tests for fetch_manifest()."""

    async def test_successful_parse(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text=_make_manifest_json(),
        )

        manifest = await fetch_manifest("https://data.example.com/")

        assert manifest.version == "1"
        assert manifest.updated_at.tzinfo == UTC
        assert len(manifest.files) == 1
        assert manifest.files[0].filename == "test.zip"
        assert manifest.files[0].category == FileCategory.BOUNDARY

    async def test_multiple_files(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        files = [
            {"filename": "a.zip", "sha512": "a" * 128, "category": "boundary", "size_bytes": 100},
            {"filename": "b.csv", "sha512": "b" * 128, "category": "voter", "size_bytes": 200},
        ]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text=_make_manifest_json(files=files),
        )

        manifest = await fetch_manifest("https://data.example.com/")
        assert len(manifest.files) == 2
        assert manifest.files[1].category == FileCategory.VOTER

    async def test_trailing_slash_normalization(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text=_make_manifest_json(),
        )

        manifest = await fetch_manifest("https://data.example.com")
        assert len(manifest.files) == 1

    async def test_invalid_json_raises(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text="not json at all",
        )

        with pytest.raises(json.JSONDecodeError):
            await fetch_manifest("https://data.example.com/")

    async def test_missing_required_field_raises(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text=json.dumps({"version": "1"}),
        )

        with pytest.raises(ValueError, match="missing required field"):
            await fetch_manifest("https://data.example.com/")

    async def test_non_200_response_raises(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            status_code=404,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_manifest("https://data.example.com/")

    async def test_invalid_file_entry_raises(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        files = [{"filename": "test.zip"}]  # Missing required fields
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text=_make_manifest_json(files=files),
        )

        with pytest.raises(ValueError, match="Invalid file entry at index 0"):
            await fetch_manifest("https://data.example.com/")

    async def test_unsupported_version_raises(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text=_make_manifest_json(version="99"),
        )

        with pytest.raises(ValueError, match="Unsupported manifest version"):
            await fetch_manifest("https://data.example.com/")

    async def test_network_error_raises(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://data.example.com/manifest.json",
        )

        with pytest.raises(httpx.ConnectError):
            await fetch_manifest("https://data.example.com/")

    async def test_invalid_updated_at_raises(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text=_make_manifest_json(updated_at="not-a-datetime"),
        )

        with pytest.raises(ValueError, match="Invalid 'updated_at' field"):
            await fetch_manifest("https://data.example.com/")

    async def test_manifest_not_object_raises(self, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        httpx_mock.add_response(
            url="https://data.example.com/manifest.json",
            text="[]",
        )

        with pytest.raises(ValueError, match="must be a JSON object"):
            await fetch_manifest("https://data.example.com/")
