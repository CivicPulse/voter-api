"""Tests for candidate importer validator."""

from voter_api.lib.candidate_importer.validator import validate_candidate_record


class TestValidateCandidateRecord:
    """Tests for validate_candidate_record."""

    def test_valid_record_returns_no_errors(self) -> None:
        record = {
            "election_name": "Governor (R)",
            "election_date": "2026-05-19",
            "candidate_name": "BRIAN KEMP",
        }
        assert validate_candidate_record(record) == []

    def test_valid_record_with_optional_fields(self) -> None:
        record = {
            "election_name": "Governor (R)",
            "election_date": "2026-05-19",
            "candidate_name": "BRIAN KEMP",
            "filing_status": "qualified",
            "email": "test@example.com",
        }
        assert validate_candidate_record(record) == []

    def test_missing_election_name(self) -> None:
        record = {
            "election_date": "2026-05-19",
            "candidate_name": "BRIAN KEMP",
        }
        errors = validate_candidate_record(record)
        assert len(errors) == 1
        assert "election_name" in errors[0]

    def test_empty_election_name(self) -> None:
        record = {
            "election_name": "  ",
            "election_date": "2026-05-19",
            "candidate_name": "BRIAN KEMP",
        }
        errors = validate_candidate_record(record)
        assert len(errors) == 1
        assert "election_name" in errors[0]

    def test_missing_election_date(self) -> None:
        record = {
            "election_name": "Governor (R)",
            "candidate_name": "BRIAN KEMP",
        }
        errors = validate_candidate_record(record)
        assert len(errors) == 1
        assert "election_date" in errors[0]

    def test_invalid_election_date(self) -> None:
        record = {
            "election_name": "Governor (R)",
            "election_date": "not-a-date",
            "candidate_name": "BRIAN KEMP",
        }
        errors = validate_candidate_record(record)
        assert len(errors) == 1
        assert "election_date" in errors[0]

    def test_missing_candidate_name(self) -> None:
        record = {
            "election_name": "Governor (R)",
            "election_date": "2026-05-19",
        }
        errors = validate_candidate_record(record)
        assert len(errors) == 1
        assert "candidate_name" in errors[0]

    def test_invalid_filing_status(self) -> None:
        record = {
            "election_name": "Governor (R)",
            "election_date": "2026-05-19",
            "candidate_name": "BRIAN KEMP",
            "filing_status": "invalid_status",
        }
        errors = validate_candidate_record(record)
        assert len(errors) == 1
        assert "filing_status" in errors[0]

    def test_invalid_email(self) -> None:
        record = {
            "election_name": "Governor (R)",
            "election_date": "2026-05-19",
            "candidate_name": "BRIAN KEMP",
            "email": "not-an-email",
        }
        errors = validate_candidate_record(record)
        assert len(errors) == 1
        assert "email" in errors[0]

    def test_multiple_errors(self) -> None:
        record = {
            "filing_status": "bad",
            "email": "nope",
        }
        errors = validate_candidate_record(record)
        assert len(errors) == 5  # 3 required + filing_status + email

    def test_empty_optional_fields_are_ok(self) -> None:
        record = {
            "election_name": "Governor (R)",
            "election_date": "2026-05-19",
            "candidate_name": "BRIAN KEMP",
            "filing_status": "",
            "email": "",
        }
        assert validate_candidate_record(record) == []
