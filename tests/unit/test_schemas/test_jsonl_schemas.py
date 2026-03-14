"""Unit tests for JSONL schema Pydantic models.

Tests cover ElectionEventJSONL, ElectionJSONL, CandidateJSONL, and
CandidacyJSONL -- the four data contracts for the markdown-to-database
import pipeline.

Requirements: FMT-04, FMT-05, FMT-06
"""

import uuid
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from voter_api.schemas.jsonl import (
    CandidacyJSONL,
    CandidateJSONL,
    CandidateLinkJSONL,
    ElectionEventJSONL,
    ElectionJSONL,
)
from voter_api.schemas.jsonl.enums import (
    BoundaryType,
    ElectionStage,
    ElectionType,
    FilingStatus,
    LinkType,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_EVENT_ID = uuid.uuid4()
_ELECTION_ID = uuid.uuid4()
_CANDIDATE_ID = uuid.uuid4()
_CANDIDACY_ID = uuid.uuid4()


def _valid_election_event_data() -> dict:
    """Return a valid ElectionEventJSONL dict with all required fields."""
    return {
        "id": _EVENT_ID,
        "event_date": date(2026, 5, 19),
        "event_name": "May 19, 2026 - General Primary Election",
        "event_type": "general_primary",
    }


def _valid_election_data() -> dict:
    """Return a valid ElectionJSONL dict with all required fields."""
    return {
        "id": _ELECTION_ID,
        "election_event_id": _EVENT_ID,
        "name": "Governor",
        "election_date": date(2026, 5, 19),
        "election_type": "general_primary",
    }


def _valid_candidate_data() -> dict:
    """Return a valid CandidateJSONL dict with all required fields."""
    return {
        "id": _CANDIDATE_ID,
        "full_name": "Jane Doe",
    }


def _valid_candidacy_data() -> dict:
    """Return a valid CandidacyJSONL dict with all required fields."""
    return {
        "id": _CANDIDACY_ID,
        "candidate_id": _CANDIDATE_ID,
        "election_id": _ELECTION_ID,
    }


# ===================================================================
# ElectionEventJSONL
# ===================================================================


class TestElectionEventJSONL:
    """Tests for the ElectionEventJSONL Pydantic model."""

    def test_valid_record(self) -> None:
        """Valid record with all required fields passes validation."""
        data = _valid_election_event_data()
        model = ElectionEventJSONL(**data)
        assert model.id == _EVENT_ID
        assert model.event_date == date(2026, 5, 19)
        assert model.event_name == "May 19, 2026 - General Primary Election"
        assert model.event_type == ElectionType.GENERAL_PRIMARY

    def test_schema_version_defaults_to_1(self) -> None:
        """schema_version defaults to 1 when not provided."""
        model = ElectionEventJSONL(**_valid_election_event_data())
        assert model.schema_version == 1

    def test_schema_version_explicit(self) -> None:
        """schema_version can be set explicitly."""
        data = _valid_election_event_data()
        data["schema_version"] = 2
        model = ElectionEventJSONL(**data)
        assert model.schema_version == 2

    def test_calendar_fields_optional(self) -> None:
        """Calendar fields are optional date fields."""
        data = _valid_election_event_data()
        data["registration_deadline"] = date(2026, 4, 21)
        data["early_voting_start"] = date(2026, 4, 28)
        data["early_voting_end"] = date(2026, 5, 15)
        data["absentee_request_deadline"] = date(2026, 5, 9)
        data["qualifying_start"] = date(2026, 3, 3)
        data["qualifying_end"] = date(2026, 3, 7)
        model = ElectionEventJSONL(**data)
        assert model.registration_deadline == date(2026, 4, 21)
        assert model.early_voting_start == date(2026, 4, 28)
        assert model.early_voting_end == date(2026, 5, 15)
        assert model.absentee_request_deadline == date(2026, 5, 9)
        assert model.qualifying_start == date(2026, 3, 3)
        assert model.qualifying_end == date(2026, 3, 7)

    def test_calendar_fields_default_none(self) -> None:
        """Calendar fields default to None when omitted."""
        model = ElectionEventJSONL(**_valid_election_event_data())
        assert model.registration_deadline is None
        assert model.early_voting_start is None
        assert model.early_voting_end is None
        assert model.absentee_request_deadline is None
        assert model.qualifying_start is None
        assert model.qualifying_end is None

    def test_feed_fields_optional(self) -> None:
        """Feed-related fields are optional."""
        data = _valid_election_event_data()
        data["data_source_url"] = "https://results.sos.ga.gov/api/v1"
        data["last_refreshed_at"] = datetime(2026, 5, 19, 20, 0, 0)
        data["refresh_interval_seconds"] = 120
        model = ElectionEventJSONL(**data)
        assert model.data_source_url == "https://results.sos.ga.gov/api/v1"
        assert model.refresh_interval_seconds == 120

    def test_feed_fields_default_none(self) -> None:
        """Feed fields default to None when omitted."""
        model = ElectionEventJSONL(**_valid_election_event_data())
        assert model.data_source_url is None
        assert model.last_refreshed_at is None
        assert model.refresh_interval_seconds is None

    def test_invalid_event_type_rejected(self) -> None:
        """Invalid event_type value raises ValidationError."""
        data = _valid_election_event_data()
        data["event_type"] = "invalid_type"
        with pytest.raises(ValidationError, match="event_type"):
            ElectionEventJSONL(**data)

    def test_missing_required_field_rejected(self) -> None:
        """Missing a required field raises ValidationError."""
        data = _valid_election_event_data()
        del data["event_name"]
        with pytest.raises(ValidationError, match="event_name"):
            ElectionEventJSONL(**data)

    def test_model_json_schema(self) -> None:
        """model_json_schema() returns valid schema with descriptions."""
        schema = ElectionEventJSONL.model_json_schema()
        props = schema["properties"]
        assert "schema_version" in props
        assert "id" in props
        assert "event_date" in props
        assert "event_name" in props
        assert "event_type" in props
        # All fields have descriptions
        for field_name, field_info in props.items():
            assert "description" in field_info, f"Missing description on {field_name}"

    def test_schema_version_in_model_dump(self) -> None:
        """schema_version appears in model_dump() output (not a private attr)."""
        model = ElectionEventJSONL(**_valid_election_event_data())
        dumped = model.model_dump()
        assert "schema_version" in dumped
        assert dumped["schema_version"] == 1


# ===================================================================
# ElectionJSONL
# ===================================================================


class TestElectionJSONL:
    """Tests for the ElectionJSONL Pydantic model."""

    def test_valid_record(self) -> None:
        """Valid record with all required fields passes validation."""
        data = _valid_election_data()
        model = ElectionJSONL(**data)
        assert model.id == _ELECTION_ID
        assert model.election_event_id == _EVENT_ID
        assert model.name == "Governor"
        assert model.election_date == date(2026, 5, 19)
        assert model.election_type == ElectionType.GENERAL_PRIMARY

    def test_schema_version_defaults_to_1(self) -> None:
        """schema_version defaults to 1 when not provided."""
        model = ElectionJSONL(**_valid_election_data())
        assert model.schema_version == 1

    def test_election_stage_defaults_to_election(self) -> None:
        """election_stage defaults to 'election' when not provided."""
        model = ElectionJSONL(**_valid_election_data())
        assert model.election_stage == ElectionStage.ELECTION

    def test_election_stage_runoff(self) -> None:
        """election_stage accepts 'runoff'."""
        data = _valid_election_data()
        data["election_stage"] = "runoff"
        model = ElectionJSONL(**data)
        assert model.election_stage == ElectionStage.RUNOFF

    def test_invalid_election_type_rejected(self) -> None:
        """Invalid election_type raises ValidationError."""
        data = _valid_election_data()
        data["election_type"] = "primary"
        with pytest.raises(ValidationError, match="election_type"):
            ElectionJSONL(**data)

    def test_invalid_election_stage_rejected(self) -> None:
        """Invalid election_stage raises ValidationError."""
        data = _valid_election_data()
        data["election_stage"] = "overtime"
        with pytest.raises(ValidationError, match="election_stage"):
            ElectionJSONL(**data)

    def test_no_calendar_fields(self) -> None:
        """ElectionJSONL does NOT have calendar fields (they moved to ElectionEvent)."""
        model = ElectionJSONL(**_valid_election_data())
        assert not hasattr(model, "registration_deadline")
        assert not hasattr(model, "early_voting_start")
        assert not hasattr(model, "early_voting_end")
        assert not hasattr(model, "absentee_request_deadline")
        assert not hasattr(model, "qualifying_start")
        assert not hasattr(model, "qualifying_end")

    def test_boundary_fields_optional(self) -> None:
        """boundary_type and district_identifier are optional strings."""
        data = _valid_election_data()
        data["boundary_type"] = "state_house"
        data["district_identifier"] = "42"
        model = ElectionJSONL(**data)
        assert model.boundary_type == "state_house"
        assert model.district_identifier == "42"

    def test_boundary_fields_default_none(self) -> None:
        """boundary_type and district_identifier default to None."""
        model = ElectionJSONL(**_valid_election_data())
        assert model.boundary_type is None
        assert model.district_identifier is None

    def test_name_sos_optional(self) -> None:
        """name_sos is an optional string field."""
        data = _valid_election_data()
        data["name_sos"] = "Governor - Republican Primary"
        model = ElectionJSONL(**data)
        assert model.name_sos == "Governor - Republican Primary"

    def test_name_sos_default_none(self) -> None:
        """name_sos defaults to None."""
        model = ElectionJSONL(**_valid_election_data())
        assert model.name_sos is None

    def test_optional_fields(self) -> None:
        """All optional fields can be set."""
        data = _valid_election_data()
        data["district"] = "Bibb County"
        data["data_source_url"] = "https://results.sos.ga.gov"
        data["source"] = "sos_feed"
        data["ballot_item_id"] = "GOV-2026"
        data["status"] = "active"
        data["boundary_id"] = uuid.uuid4()
        data["district_party"] = "R"
        model = ElectionJSONL(**data)
        assert model.district == "Bibb County"
        assert model.source == "sos_feed"

    def test_model_json_schema(self) -> None:
        """model_json_schema() returns valid schema with descriptions."""
        schema = ElectionJSONL.model_json_schema()
        props = schema["properties"]
        assert "schema_version" in props
        assert "election_type" in props
        assert "election_stage" in props
        assert "name_sos" in props
        # All fields have descriptions
        for field_name, field_info in props.items():
            assert "description" in field_info, f"Missing description on {field_name}"

    def test_schema_version_in_model_dump(self) -> None:
        """schema_version appears in model_dump() output."""
        model = ElectionJSONL(**_valid_election_data())
        dumped = model.model_dump()
        assert "schema_version" in dumped
        assert dumped["schema_version"] == 1


# ===================================================================
# CandidateJSONL
# ===================================================================


class TestCandidateJSONL:
    """Tests for the CandidateJSONL Pydantic model."""

    def test_valid_person_record(self) -> None:
        """Valid person record (id, full_name) passes validation."""
        data = _valid_candidate_data()
        model = CandidateJSONL(**data)
        assert model.id == _CANDIDATE_ID
        assert model.full_name == "Jane Doe"

    def test_no_election_id_field(self) -> None:
        """CandidateJSONL does NOT have election_id (that's on CandidacyJSONL)."""
        model = CandidateJSONL(**_valid_candidate_data())
        assert not hasattr(model, "election_id")

    def test_schema_version_defaults_to_1(self) -> None:
        """schema_version defaults to 1 when not provided."""
        model = CandidateJSONL(**_valid_candidate_data())
        assert model.schema_version == 1

    def test_person_level_fields(self) -> None:
        """Person-level fields (bio, photo_url, email, etc.) are optional."""
        data = _valid_candidate_data()
        data["bio"] = "Former state legislator with 20 years of experience."
        data["photo_url"] = "https://example.com/jane.jpg"
        data["email"] = "jane@example.com"
        data["home_county"] = "Bibb"
        data["municipality"] = "Macon"
        model = CandidateJSONL(**data)
        assert model.bio == "Former state legislator with 20 years of experience."
        assert model.photo_url == "https://example.com/jane.jpg"
        assert model.email == "jane@example.com"
        assert model.home_county == "Bibb"
        assert model.municipality == "Macon"

    def test_person_fields_default_none(self) -> None:
        """Person-level optional fields default to None."""
        model = CandidateJSONL(**_valid_candidate_data())
        assert model.bio is None
        assert model.photo_url is None
        assert model.email is None
        assert model.home_county is None
        assert model.municipality is None

    def test_links_optional_list(self) -> None:
        """links is an optional list of CandidateLinkJSONL objects."""
        data = _valid_candidate_data()
        data["links"] = [
            {"link_type": "website", "url": "https://janedoe.com"},
            {"link_type": "twitter", "url": "https://twitter.com/janedoe", "label": "@janedoe"},
        ]
        model = CandidateJSONL(**data)
        assert len(model.links) == 2
        assert model.links[0].link_type == LinkType.WEBSITE
        assert model.links[0].url == "https://janedoe.com"
        assert model.links[1].label == "@janedoe"

    def test_links_default_empty(self) -> None:
        """links defaults to an empty list."""
        model = CandidateJSONL(**_valid_candidate_data())
        assert model.links == []

    def test_links_invalid_link_type_rejected(self) -> None:
        """Invalid link_type in links raises ValidationError."""
        data = _valid_candidate_data()
        data["links"] = [{"link_type": "tiktok", "url": "https://tiktok.com/@jane"}]
        with pytest.raises(ValidationError, match="link_type"):
            CandidateJSONL(**data)

    def test_external_ids_optional_dict(self) -> None:
        """external_ids is an optional dict for cross-referencing."""
        data = _valid_candidate_data()
        data["external_ids"] = {
            "ballotpedia": "Jane_Doe_(Georgia)",
            "open_states": "ocd-person/12345",
        }
        model = CandidateJSONL(**data)
        assert model.external_ids["ballotpedia"] == "Jane_Doe_(Georgia)"

    def test_external_ids_default_none(self) -> None:
        """external_ids defaults to None."""
        model = CandidateJSONL(**_valid_candidate_data())
        assert model.external_ids is None

    def test_model_json_schema(self) -> None:
        """model_json_schema() returns valid schema with descriptions."""
        schema = CandidateJSONL.model_json_schema()
        props = schema["properties"]
        assert "schema_version" in props
        assert "full_name" in props
        assert "links" in props
        assert "external_ids" in props
        # election_id should NOT be in schema
        assert "election_id" not in props
        # All fields have descriptions
        for field_name, field_info in props.items():
            assert "description" in field_info, f"Missing description on {field_name}"

    def test_schema_version_in_model_dump(self) -> None:
        """schema_version appears in model_dump() output."""
        model = CandidateJSONL(**_valid_candidate_data())
        dumped = model.model_dump()
        assert "schema_version" in dumped
        assert dumped["schema_version"] == 1


# ===================================================================
# CandidacyJSONL
# ===================================================================


class TestCandidacyJSONL:
    """Tests for the CandidacyJSONL Pydantic model."""

    def test_valid_junction_record(self) -> None:
        """Valid junction record (id, candidate_id, election_id) passes validation."""
        data = _valid_candidacy_data()
        model = CandidacyJSONL(**data)
        assert model.id == _CANDIDACY_ID
        assert model.candidate_id == _CANDIDATE_ID
        assert model.election_id == _ELECTION_ID

    def test_schema_version_defaults_to_1(self) -> None:
        """schema_version defaults to 1 when not provided."""
        model = CandidacyJSONL(**_valid_candidacy_data())
        assert model.schema_version == 1

    def test_filing_status_defaults_to_qualified(self) -> None:
        """filing_status defaults to 'qualified'."""
        model = CandidacyJSONL(**_valid_candidacy_data())
        assert model.filing_status == FilingStatus.QUALIFIED

    def test_filing_status_withdrawn(self) -> None:
        """filing_status accepts 'withdrawn'."""
        data = _valid_candidacy_data()
        data["filing_status"] = "withdrawn"
        model = CandidacyJSONL(**data)
        assert model.filing_status == FilingStatus.WITHDRAWN

    def test_invalid_filing_status_rejected(self) -> None:
        """Invalid filing_status raises ValidationError."""
        data = _valid_candidacy_data()
        data["filing_status"] = "pending"
        with pytest.raises(ValidationError, match="filing_status"):
            CandidacyJSONL(**data)

    def test_contest_specific_fields(self) -> None:
        """Contest-specific fields are optional."""
        data = _valid_candidacy_data()
        data["party"] = "Republican"
        data["occupation"] = "Attorney"
        data["qualified_date"] = date(2026, 3, 3)
        data["is_incumbent"] = True
        data["ballot_order"] = 1
        data["sos_ballot_option_id"] = "OPT-001"
        data["contest_name"] = "Governor - Republican Primary"
        model = CandidacyJSONL(**data)
        assert model.party == "Republican"
        assert model.occupation == "Attorney"
        assert model.qualified_date == date(2026, 3, 3)
        assert model.is_incumbent is True
        assert model.ballot_order == 1
        assert model.sos_ballot_option_id == "OPT-001"
        assert model.contest_name == "Governor - Republican Primary"

    def test_contest_fields_defaults(self) -> None:
        """Contest-specific optional fields have appropriate defaults."""
        model = CandidacyJSONL(**_valid_candidacy_data())
        assert model.party is None
        assert model.occupation is None
        assert model.qualified_date is None
        assert model.is_incumbent is False
        assert model.ballot_order is None
        assert model.sos_ballot_option_id is None
        assert model.contest_name is None

    def test_missing_candidate_id_rejected(self) -> None:
        """Missing candidate_id raises ValidationError."""
        data = _valid_candidacy_data()
        del data["candidate_id"]
        with pytest.raises(ValidationError, match="candidate_id"):
            CandidacyJSONL(**data)

    def test_missing_election_id_rejected(self) -> None:
        """Missing election_id raises ValidationError."""
        data = _valid_candidacy_data()
        del data["election_id"]
        with pytest.raises(ValidationError, match="election_id"):
            CandidacyJSONL(**data)

    def test_model_json_schema(self) -> None:
        """model_json_schema() returns valid schema with descriptions."""
        schema = CandidacyJSONL.model_json_schema()
        props = schema["properties"]
        assert "schema_version" in props
        assert "candidate_id" in props
        assert "election_id" in props
        assert "filing_status" in props
        # All fields have descriptions
        for field_name, field_info in props.items():
            assert "description" in field_info, f"Missing description on {field_name}"

    def test_schema_version_in_model_dump(self) -> None:
        """schema_version appears in model_dump() output."""
        model = CandidacyJSONL(**_valid_candidacy_data())
        dumped = model.model_dump()
        assert "schema_version" in dumped
        assert dumped["schema_version"] == 1


# ===================================================================
# Cross-cutting tests
# ===================================================================


class TestSchemaVersionAllModels:
    """schema_version field is present on all 4 models and defaults to 1."""

    @pytest.mark.parametrize(
        ("model_cls", "data_fn"),
        [
            (ElectionEventJSONL, _valid_election_event_data),
            (ElectionJSONL, _valid_election_data),
            (CandidateJSONL, _valid_candidate_data),
            (CandidacyJSONL, _valid_candidacy_data),
        ],
        ids=["election_event", "election", "candidate", "candidacy"],
    )
    def test_schema_version_defaults_to_1(self, model_cls, data_fn) -> None:
        """schema_version defaults to 1 on all JSONL models."""
        model = model_cls(**data_fn())
        assert model.schema_version == 1

    @pytest.mark.parametrize(
        ("model_cls", "data_fn"),
        [
            (ElectionEventJSONL, _valid_election_event_data),
            (ElectionJSONL, _valid_election_data),
            (CandidateJSONL, _valid_candidate_data),
            (CandidacyJSONL, _valid_candidacy_data),
        ],
        ids=["election_event", "election", "candidate", "candidacy"],
    )
    def test_schema_version_in_json_schema(self, model_cls, data_fn) -> None:
        """schema_version appears in model_json_schema() output."""
        schema = model_cls.model_json_schema()
        assert "schema_version" in schema["properties"]

    @pytest.mark.parametrize(
        ("model_cls", "data_fn"),
        [
            (ElectionEventJSONL, _valid_election_event_data),
            (ElectionJSONL, _valid_election_data),
            (CandidateJSONL, _valid_candidate_data),
            (CandidacyJSONL, _valid_candidacy_data),
        ],
        ids=["election_event", "election", "candidate", "candidacy"],
    )
    def test_model_json_schema_valid(self, model_cls, data_fn) -> None:
        """model_json_schema() returns valid JSON Schema with descriptions."""
        schema = model_cls.model_json_schema()
        assert "properties" in schema
        props = schema["properties"]
        assert len(props) > 0
        for field_name, field_info in props.items():
            assert "description" in field_info, (
                f"{model_cls.__name__}.{field_name} missing description"
            )


# ===================================================================
# Enum validation tests
# ===================================================================


class TestEnums:
    """Tests for StrEnum definitions in enums.py."""

    def test_election_type_values(self) -> None:
        """ElectionType has exactly 5 values."""
        assert set(ElectionType) == {
            "general_primary",
            "general",
            "special",
            "special_primary",
            "municipal",
        }

    def test_election_stage_values(self) -> None:
        """ElectionStage has exactly 3 values."""
        assert set(ElectionStage) == {"election", "runoff", "recount"}

    def test_filing_status_values(self) -> None:
        """FilingStatus has exactly 4 values."""
        assert set(FilingStatus) == {"qualified", "withdrawn", "disqualified", "write_in"}

    def test_link_type_values(self) -> None:
        """LinkType has exactly 8 values."""
        assert set(LinkType) == {
            "website",
            "campaign",
            "facebook",
            "twitter",
            "instagram",
            "youtube",
            "linkedin",
            "other",
        }

    def test_boundary_type_values(self) -> None:
        """BoundaryType has exactly 18 values matching BOUNDARY_TYPES."""
        expected = {
            "congressional",
            "state_senate",
            "state_house",
            "judicial",
            "psc",
            "county",
            "county_commission",
            "school_board",
            "city_council",
            "municipal_school_board",
            "water_board",
            "super_council",
            "super_commissioner",
            "super_school_board",
            "fire_district",
            "county_precinct",
            "municipal_precinct",
            "us_senate",
        }
        assert set(BoundaryType) == expected


# ===================================================================
# CandidateLinkJSONL tests
# ===================================================================


class TestCandidateLinkJSONL:
    """Tests for the CandidateLinkJSONL embedded model."""

    def test_valid_link(self) -> None:
        """Valid link with required fields passes validation."""
        link = CandidateLinkJSONL(link_type="website", url="https://example.com")
        assert link.link_type == LinkType.WEBSITE
        assert link.url == "https://example.com"
        assert link.label is None

    def test_link_with_label(self) -> None:
        """Link with optional label."""
        link = CandidateLinkJSONL(
            link_type="campaign",
            url="https://janedoe.com",
            label="Jane Doe for Governor",
        )
        assert link.label == "Jane Doe for Governor"

    def test_invalid_link_type_rejected(self) -> None:
        """Invalid link_type raises ValidationError."""
        with pytest.raises(ValidationError, match="link_type"):
            CandidateLinkJSONL(link_type="tiktok", url="https://tiktok.com")
