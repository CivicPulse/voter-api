"""Fetch and parse the remote seed manifest.

Downloads ``manifest.json`` from the Data Root URL and returns a
validated :class:`SeedManifest` instance.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from loguru import logger

from voter_api.lib.data_loader.types import DataFileEntry, FileCategory, SeedManifest


async def fetch_manifest(data_root_url: str) -> SeedManifest:
    """Fetch and parse the remote manifest.json.

    Args:
        data_root_url: Base URL ending with ``/`` (e.g. ``https://data.hatchtech.dev/``).

    Returns:
        A validated SeedManifest with all file entries.

    Raises:
        httpx.HTTPStatusError: If the server returns a non-2xx response.
        httpx.ConnectError: If the server is unreachable.
        ValueError: If the manifest JSON is invalid or fails validation.
    """
    url = f"{data_root_url.rstrip('/')}/manifest.json"
    logger.info("Fetching manifest from {}", url)

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        msg = "Manifest must be a JSON object"
        raise ValueError(msg)

    for required_key in ("version", "updated_at", "files"):
        if required_key not in data:
            msg = f"Manifest missing required field: {required_key!r}"
            raise ValueError(msg)

    updated_at = datetime.fromisoformat(data["updated_at"]).astimezone(UTC)

    files: list[DataFileEntry] = []
    for i, raw in enumerate(data["files"]):
        try:
            entry = DataFileEntry(
                filename=raw["filename"],
                sha512=raw["sha512"],
                category=FileCategory(raw["category"]),
                size_bytes=raw["size_bytes"],
            )
            files.append(entry)
        except (KeyError, ValueError) as exc:
            msg = f"Invalid file entry at index {i}: {exc}"
            raise ValueError(msg) from exc

    manifest = SeedManifest(
        version=data["version"],
        updated_at=updated_at,
        files=tuple(files),
    )

    logger.info(
        "Manifest loaded: {} files, updated {}",
        len(manifest.files),
        manifest.updated_at.isoformat(),
    )
    return manifest
