"""File storage abstraction for meeting attachments.

Provides a ``FileStorage`` Protocol and a ``LocalFileStorage`` implementation
that writes files to the local filesystem using async I/O. The storage path
is structured as ``{base_dir}/{year}/{month}/{uuid}.{ext}`` to keep
directories manageable at scale.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import aiofiles


class FileStorage(Protocol):
    """Abstract file storage interface for meeting attachments.

    Implementations must provide async save, load, and delete operations.
    """

    async def save(self, content: bytes, filename: str) -> str:
        """Save file content and return the stored path.

        Args:
            content: Raw file bytes to store.
            filename: Original filename (used only for extension extraction).

        Returns:
            The relative storage path (e.g., "2026/02/abc123.pdf").
        """
        ...

    async def load(self, stored_path: str) -> bytes:
        """Load file content from the stored path.

        Args:
            stored_path: The relative path returned by save().

        Returns:
            The raw file bytes.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        ...

    async def delete(self, stored_path: str) -> None:
        """Delete a file from storage.

        Args:
            stored_path: The relative path returned by save().

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        ...


class LocalFileStorage:
    """Local filesystem implementation of FileStorage.

    Files are stored under ``base_dir/{year}/{month}/{uuid}.{ext}``.

    Args:
        base_dir: The root directory for file storage.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)

    async def save(self, content: bytes, filename: str) -> str:
        """Save file content to the local filesystem.

        Creates year/month subdirectories as needed. Generates a UUID-based
        filename to prevent collisions.

        Args:
            content: Raw file bytes.
            filename: Original filename (extension is preserved).

        Returns:
            Relative storage path (e.g., "2026/02/abc123.pdf").
        """
        now = datetime.now(tz=UTC)
        year = str(now.year)
        month = f"{now.month:02d}"

        ext = self._extract_extension(filename)
        stored_name = f"{uuid.uuid4().hex}{ext}"
        relative_path = f"{year}/{month}/{stored_name}"

        full_dir = self._base_dir / year / month
        full_dir.mkdir(parents=True, exist_ok=True)

        full_path = self._base_dir / relative_path
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)

        return relative_path

    async def load(self, stored_path: str) -> bytes:
        """Load file content from the local filesystem.

        Args:
            stored_path: Relative path as returned by save().

        Returns:
            Raw file bytes.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        full_path = self._base_dir / stored_path
        if not full_path.exists():
            msg = f"File not found: {stored_path}"
            raise FileNotFoundError(msg)

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete(self, stored_path: str) -> None:
        """Delete a file from the local filesystem.

        Args:
            stored_path: Relative path as returned by save().

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        full_path = self._base_dir / stored_path
        if not full_path.exists():
            msg = f"File not found: {stored_path}"
            raise FileNotFoundError(msg)
        full_path.unlink()

    @staticmethod
    def _extract_extension(filename: str) -> str:
        """Extract the lowercase file extension including the dot.

        Args:
            filename: The filename to extract from.

        Returns:
            The extension (e.g., ".pdf") or empty string if none.
        """
        dot_idx = filename.rfind(".")
        if dot_idx == -1:
            return ""
        return filename[dot_idx:].lower()
