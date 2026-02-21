"""Unit tests for local file storage."""

import pytest

from voter_api.lib.meetings.storage import LocalFileStorage


@pytest.fixture
def storage(tmp_path):
    """Create a LocalFileStorage instance with a temporary directory."""
    return LocalFileStorage(tmp_path)


class TestLocalFileStorageSave:
    """Tests for saving files."""

    @pytest.mark.asyncio
    async def test_save_returns_relative_path(self, storage, tmp_path):
        """save() should return a relative path like YYYY/MM/uuid.ext."""
        path = await storage.save(b"hello world", "test.pdf")
        assert path.endswith(".pdf")
        parts = path.split("/")
        assert len(parts) == 3  # year/month/filename
        assert parts[0].isdigit() and len(parts[0]) == 4  # year
        assert parts[1].isdigit() and len(parts[1]) == 2  # month

    @pytest.mark.asyncio
    async def test_save_creates_file(self, storage, tmp_path):
        """save() should write the file to disk."""
        content = b"PDF content here"
        path = await storage.save(content, "agenda.pdf")
        full_path = tmp_path / path
        assert full_path.exists()
        assert full_path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_save_creates_directories(self, storage, tmp_path):
        """save() should create year/month subdirectories."""
        await storage.save(b"data", "file.csv")
        # Check that at least one year directory exists
        subdirs = list(tmp_path.iterdir())
        assert len(subdirs) >= 1
        assert subdirs[0].is_dir()

    @pytest.mark.asyncio
    async def test_save_preserves_extension(self, storage):
        """save() should preserve the original file extension."""
        path = await storage.save(b"data", "budget.xlsx")
        assert path.endswith(".xlsx")

    @pytest.mark.asyncio
    async def test_save_lowercases_extension(self, storage):
        """save() should lowercase the file extension."""
        path = await storage.save(b"data", "REPORT.PDF")
        assert path.endswith(".pdf")

    @pytest.mark.asyncio
    async def test_save_no_extension(self, storage):
        """save() should handle files without an extension."""
        path = await storage.save(b"data", "noext")
        # Should not have a dot before the filename part
        filename = path.split("/")[-1]
        assert "." not in filename

    @pytest.mark.asyncio
    async def test_save_unique_filenames(self, storage):
        """Multiple saves of the same file should produce unique paths."""
        path1 = await storage.save(b"data1", "file.pdf")
        path2 = await storage.save(b"data2", "file.pdf")
        assert path1 != path2


class TestLocalFileStorageLoad:
    """Tests for loading files."""

    @pytest.mark.asyncio
    async def test_load_returns_content(self, storage):
        """load() should return the file content."""
        content = b"test content for loading"
        path = await storage.save(content, "test.pdf")
        loaded = await storage.load(path)
        assert loaded == content

    @pytest.mark.asyncio
    async def test_load_nonexistent_raises(self, storage):
        """load() should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            await storage.load("2026/01/nonexistent.pdf")


class TestLocalFileStorageDelete:
    """Tests for deleting files."""

    @pytest.mark.asyncio
    async def test_delete_removes_file(self, storage, tmp_path):
        """delete() should remove the file from disk."""
        path = await storage.save(b"to be deleted", "temp.pdf")
        full_path = tmp_path / path
        assert full_path.exists()

        await storage.delete(path)
        assert not full_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, storage):
        """delete() should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            await storage.delete("2026/01/nonexistent.pdf")
