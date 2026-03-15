"""Tests for uuid_handler module.

Covers UUID detection, generation, and candidate file renaming logic.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from voter_api.lib.normalizer.uuid_handler import ensure_uuid, rename_candidate_file

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"
_CONTENT_WITH_UUID = f"""# Jane Doe

## Metadata

| Field | Value |
|-------|-------|
| ID | {_VALID_UUID} |
| Format Version | 1 |
"""

_CONTENT_EMPTY_ID = """# Jane Doe

## Metadata

| Field | Value |
|-------|-------|
| ID |  |
| Format Version | 1 |
"""

_CONTENT_DASH_PLACEHOLDER = """# Jane Doe

## Metadata

| Field | Value |
|-------|-------|
| ID | -- |
| Format Version | 1 |
"""

_CONTENT_EMDASH_PLACEHOLDER = """# Jane Doe

## Metadata

| Field | Value |
|-------|-------|
| ID | \u2014 |
| Format Version | 1 |
"""

_CONTENT_INVALID_ID = """# Jane Doe

## Metadata

| Field | Value |
|-------|-------|
| ID | not-a-uuid |
| Format Version | 1 |
"""

_CONTENT_NO_ID_FIELD = """# Jane Doe

## Metadata

| Field | Value |
|-------|-------|
| Format Version | 1 |
"""


# ---------------------------------------------------------------------------
# TestEnsureUuid
# ---------------------------------------------------------------------------


class TestEnsureUuid:
    """Tests for the ensure_uuid function."""

    def test_valid_uuid_unchanged(self) -> None:
        """A file with a valid UUID is returned unchanged."""
        new_content, generated = ensure_uuid(_CONTENT_WITH_UUID)
        assert generated is None
        assert new_content == _CONTENT_WITH_UUID

    def test_valid_uuid_preserved_exactly(self) -> None:
        """The existing UUID value is preserved exactly as written."""
        new_content, generated = ensure_uuid(_CONTENT_WITH_UUID)
        assert _VALID_UUID in new_content

    def test_empty_id_generates_uuid(self) -> None:
        """An empty ID field triggers UUID generation."""
        new_content, generated = ensure_uuid(_CONTENT_EMPTY_ID)
        assert generated is not None
        # Verify it's a valid UUID
        parsed = uuid.UUID(generated)
        assert str(parsed) == generated.lower()

    def test_empty_id_written_into_content(self) -> None:
        """The generated UUID is inserted into the content."""
        new_content, generated = ensure_uuid(_CONTENT_EMPTY_ID)
        assert generated is not None
        assert generated in new_content

    def test_dash_placeholder_generates_uuid(self) -> None:
        """A '--' placeholder triggers UUID generation."""
        new_content, generated = ensure_uuid(_CONTENT_DASH_PLACEHOLDER)
        assert generated is not None
        # Verify UUID is in new content
        assert generated in new_content

    def test_emdash_placeholder_generates_uuid(self) -> None:
        """An em-dash (U+2014) placeholder triggers UUID generation."""
        new_content, generated = ensure_uuid(_CONTENT_EMDASH_PLACEHOLDER)
        assert generated is not None
        assert generated in new_content

    def test_invalid_uuid_raises_value_error(self) -> None:
        """A non-empty, non-UUID value raises ValueError."""
        with pytest.raises(ValueError, match="invalid UUID"):
            ensure_uuid(_CONTENT_INVALID_ID)

    def test_no_id_field_returns_generated(self) -> None:
        """If no ID field exists, a UUID is generated (treated as missing)."""
        _new_content, generated = ensure_uuid(_CONTENT_NO_ID_FIELD)
        assert generated is not None

    def test_generated_uuid_is_unique(self) -> None:
        """Two calls with missing ID produce different UUIDs."""
        _, uuid1 = ensure_uuid(_CONTENT_EMPTY_ID)
        _, uuid2 = ensure_uuid(_CONTENT_EMPTY_ID)
        assert uuid1 != uuid2

    def test_generated_uuid_format(self) -> None:
        """Generated UUID has standard UUID4 format (8-4-4-4-12)."""
        _, generated = ensure_uuid(_CONTENT_EMPTY_ID)
        assert generated is not None
        parts = generated.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12


# ---------------------------------------------------------------------------
# TestRenameCandidateFile
# ---------------------------------------------------------------------------


class TestRenameCandidateFile:
    """Tests for the rename_candidate_file function."""

    def test_placeholder_replaced_with_uuid_prefix(self, tmp_path: Path) -> None:
        """File with 00000000 placeholder is renamed using UUID prefix."""
        file_path = tmp_path / "jane-doe-00000000.md"
        file_path.write_text("# Jane Doe\n")
        test_uuid = "a3f2e1b4-1234-5678-9abc-def012345678"

        new_path = rename_candidate_file(file_path, test_uuid)

        assert new_path is not None
        assert new_path.name == "jane-doe-a3f2e1b4.md"
        assert new_path.exists()
        assert not file_path.exists()

    def test_rename_uses_first_8_chars_of_uuid(self, tmp_path: Path) -> None:
        """The rename uses the first 8 hex chars (no dashes) of the UUID."""
        file_path = tmp_path / "test-candidate-00000000.md"
        file_path.write_text("# Test\n")
        test_uuid = "550e8400-e29b-41d4-a716-446655440000"

        new_path = rename_candidate_file(file_path, test_uuid)

        assert new_path is not None
        # First 8 chars without dashes: "550e8400"
        assert "550e8400" in new_path.name

    def test_no_placeholder_returns_none(self, tmp_path: Path) -> None:
        """File without 00000000 placeholder returns None (no rename)."""
        file_path = tmp_path / "jane-doe-a3f2e1b4.md"
        file_path.write_text("# Jane Doe\n")
        test_uuid = "a3f2e1b4-1234-5678-9abc-def012345678"

        result = rename_candidate_file(file_path, test_uuid)

        assert result is None
        assert file_path.exists()

    def test_no_placeholder_file_unchanged(self, tmp_path: Path) -> None:
        """File without placeholder is not modified."""
        file_path = tmp_path / "already-named-a3f2e1b4.md"
        original_content = "# Already Named\n"
        file_path.write_text(original_content)
        test_uuid = "b4c5d6e7-1234-5678-9abc-def012345678"

        rename_candidate_file(file_path, test_uuid)

        assert file_path.read_text() == original_content

    def test_renamed_file_content_preserved(self, tmp_path: Path) -> None:
        """File content is preserved after rename."""
        file_path = tmp_path / "test-person-00000000.md"
        original_content = "# Test Person\n\nSome content here.\n"
        file_path.write_text(original_content)
        test_uuid = "deadbeef-dead-beef-dead-beefdeadbeef"

        new_path = rename_candidate_file(file_path, test_uuid)

        assert new_path is not None
        assert new_path.read_text() == original_content

    def test_only_first_placeholder_replaced(self, tmp_path: Path) -> None:
        """Only the first occurrence of 00000000 is replaced in the filename."""
        # Edge case: filename with two occurrences of placeholder
        file_path = tmp_path / "test-00000000-00000000.md"
        file_path.write_text("# Test\n")
        test_uuid = "a1b2c3d4-1234-5678-9abc-def012345678"

        new_path = rename_candidate_file(file_path, test_uuid)

        assert new_path is not None
        # Only the first occurrence should be replaced
        assert new_path.name == "test-a1b2c3d4-00000000.md"
