"""Unit tests for importer differ module."""

from voter_api.lib.importer.differ import detect_field_changes, generate_diff


class TestGenerateDiff:
    """Tests for diff generation."""

    def test_added_records(self) -> None:
        """New registration numbers detected as added."""
        diff = generate_diff({"A", "B", "C"}, {"A", "B"})
        assert diff["added"] == ["C"]
        assert diff["removed"] == []

    def test_removed_records(self) -> None:
        """Missing registration numbers detected as removed."""
        diff = generate_diff({"A"}, {"A", "B"})
        assert diff["removed"] == ["B"]
        assert diff["added"] == []

    def test_updated_records(self) -> None:
        """Updated records are tracked."""
        diff = generate_diff({"A", "B"}, {"A", "B"}, updated_reg_numbers={"A"})
        assert diff["updated"] == ["A"]
        assert diff["added"] == []
        assert diff["removed"] == []

    def test_empty_diff(self) -> None:
        """No changes produces empty diff."""
        diff = generate_diff({"A", "B"}, {"A", "B"})
        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["updated"] == []


class TestDetectFieldChanges:
    """Tests for field-level change detection."""

    def test_no_changes(self) -> None:
        """Identical records produce no changes."""
        existing = {"name": "John", "city": "Atlanta"}
        incoming = {"name": "John", "city": "Atlanta"}
        changes = detect_field_changes(existing, incoming)
        assert changes == {}

    def test_detects_changes(self) -> None:
        """Changed fields are detected."""
        existing = {"name": "John", "city": "Atlanta"}
        incoming = {"name": "John", "city": "Savannah"}
        changes = detect_field_changes(existing, incoming)
        assert "city" in changes
        assert changes["city"] == ("Atlanta", "Savannah")

    def test_specific_fields(self) -> None:
        """Only specified fields are compared."""
        existing = {"name": "John", "city": "Atlanta", "status": "ACTIVE"}
        incoming = {"name": "Jane", "city": "Savannah", "status": "INACTIVE"}
        changes = detect_field_changes(existing, incoming, compare_fields=["city"])
        assert "city" in changes
        assert "name" not in changes
        assert "status" not in changes
