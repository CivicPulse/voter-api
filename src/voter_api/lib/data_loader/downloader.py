"""File download with checksum verification and skip-if-cached support.

Downloads data files from the Data Root URL with streaming, SHA512
checksum verification, atomic writes, and tqdm progress bars.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from pathlib import Path
from loguru import logger
from tqdm import tqdm

from voter_api.lib.data_loader.types import DataFileEntry, DownloadResult, FileCategory


def resolve_download_path(entry: DataFileEntry, data_dir: Path) -> Path:
    """Determine the local download path for a manifest entry.

    Voter-category files go to ``data_dir/voter/{filename}``;
    all other categories go to ``data_dir/{filename}``.

    Args:
        entry: The manifest file entry.
        data_dir: Root data directory.

    Returns:
        Absolute or relative Path for the downloaded file.
    """
    if entry.category == FileCategory.VOTER:
        return data_dir / "voter" / entry.filename
    return data_dir / entry.filename


def _compute_sha512(path: Path) -> str:
    """Compute SHA512 hex digest of a local file using streaming reads.

    Args:
        path: Path to the file to hash.

    Returns:
        Lowercase hex digest string (128 characters).
    """
    h = hashlib.sha512()
    with path.open("rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _is_cached(dest: Path, expected_sha512: str) -> bool:
    """Check if a local file exists and matches the expected checksum.

    Args:
        dest: Local file path.
        expected_sha512: Expected SHA512 hex digest.

    Returns:
        True if file exists with matching checksum.
    """
    if not dest.exists():
        return False
    actual = _compute_sha512(dest)
    return actual == expected_sha512


async def download_file(
    url: str,
    dest: Path,
    expected_sha512: str,
    size_bytes: int,
    *,
    skip_checksum: bool = False,
) -> DownloadResult:
    """Download a single file with checksum verification and atomic writes.

    If the file already exists locally with a matching checksum, the download
    is skipped. Downloads use a ``.part`` temporary file that is renamed on
    success, ensuring no partial files remain on failure (FR-011).

    Args:
        url: Full URL to download the file from.
        dest: Local path to save the file to.
        expected_sha512: Expected SHA512 hex digest from the manifest.
        size_bytes: Expected file size in bytes (for progress bar).
        skip_checksum: If True, skip checksum verification.

    Returns:
        A DownloadResult indicating success or failure.
    """
    entry = DataFileEntry(
        filename=dest.name,
        sha512=expected_sha512,
        category=FileCategory.REFERENCE,  # category not used for download logic
        size_bytes=size_bytes,
    )
    result = DownloadResult(entry=entry)

    # Skip if cached
    if not skip_checksum and _is_cached(dest, expected_sha512):
        logger.info("Cached (checksum match): {}", dest.name)
        result.downloaded = False
        result.verified = True
        result.local_path = dest
        return result

    if skip_checksum and dest.exists():
        logger.info("Cached (file exists, checksum skipped): {}", dest.name)
        result.downloaded = False
        result.verified = True
        result.local_path = dest
        return result

    # Ensure parent directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)

    part_path = dest.with_suffix(dest.suffix + ".part")

    try:
        h = hashlib.sha512()
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:  # noqa: SIM117
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                with (
                    part_path.open("wb") as f,
                    tqdm(
                        total=size_bytes,
                        unit="B",
                        unit_scale=True,
                        desc=dest.name,
                        leave=True,
                    ) as pbar,
                ):
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        h.update(chunk)
                        pbar.update(len(chunk))

        # Verify checksum
        if not skip_checksum:
            actual_hash = h.hexdigest()
            if actual_hash != expected_sha512:
                part_path.unlink(missing_ok=True)
                result.error = (
                    f"Checksum mismatch for {dest.name}: expected {expected_sha512[:16]}..., got {actual_hash[:16]}..."
                )
                logger.error(result.error)
                return result

        # Atomic rename
        part_path.rename(dest)
        result.downloaded = True
        result.verified = True
        result.local_path = dest
        logger.info("Downloaded: {} ({} bytes)", dest.name, size_bytes)

    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        part_path.unlink(missing_ok=True)
        result.error = f"Download failed for {dest.name}: {exc}"
        logger.error(result.error)

    except OSError as exc:
        part_path.unlink(missing_ok=True)
        result.error = f"File write error for {dest.name}: {exc}"
        logger.error(result.error)

    return result
