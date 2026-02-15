"""Tests for elected official service layer."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from voter_api.lib.officials.base import OfficialRecord
from voter_api.services.elected_official_service import (
    _find_matching_official,
    _promote_source_fields,
    approve_official,
    auto_create_officials_from_sources,
    create_official,
    delete_official,
    get_official,
    get_officials_for_district,
    list_officials,
    list_sources_for_district,
    update_official,
    upsert_source_records,
)


def _compile_query(query) -> str:
    """Compile a SQLAlchemy query to a PostgreSQL SQL string for inspection."""
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _mock_session(scalar_one_value=0, scalars_all_value=None) -> AsyncMock:
    """Create a mock async session with configurable return values."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = scalar_one_value
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = scalars_all_value or []
    session.execute.return_value = mock_result
    return session


class TestListOfficials:
    """Tests for list_officials query building."""

    @pytest.mark.asyncio
    async def test_no_filters(self) -> None:
        """Without filters, returns all officials."""
        session = _mock_session()
        officials, total = await list_officials(session)
        assert officials == []
        assert total == 0
        assert session.execute.call_count == 2  # count + data

    @pytest.mark.asyncio
    async def test_boundary_type_filter(self) -> None:
        """Filters by boundary_type when provided."""
        session = _mock_session()
        await list_officials(session, boundary_type="congressional")
        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        assert any("congressional" in q.lower() for q in queries)

    @pytest.mark.asyncio
    async def test_party_filter(self) -> None:
        """Filters by party when provided."""
        session = _mock_session()
        await list_officials(session, party="Democratic")
        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        assert any("democratic" in q.lower() for q in queries)

    @pytest.mark.asyncio
    async def test_pagination_offset(self) -> None:
        """Pagination applies correct offset."""
        session = _mock_session()
        await list_officials(session, page=3, page_size=10)
        calls = session.execute.call_args_list
        # The data query (second call) should have LIMIT 10 OFFSET 20
        data_query = _compile_query(calls[1][0][0])
        assert "20" in data_query  # offset
        assert "10" in data_query  # limit

    @pytest.mark.asyncio
    async def test_district_identifier_filter(self) -> None:
        """Filters by district_identifier when provided."""
        session = _mock_session()
        await list_officials(session, district_identifier="5")
        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        assert any("district_identifier" in q.lower() and "'5'" in q for q in queries)

    @pytest.mark.asyncio
    async def test_status_filter(self) -> None:
        """Filters by status when provided."""
        session = _mock_session()
        await list_officials(session, status="approved")
        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        assert any("approved" in q.lower() for q in queries)


class TestGetOfficial:
    """Tests for get_official."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        """Returns None when official not found."""
        session = _mock_session()
        result = await get_official(session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_official_when_found(self) -> None:
        """Returns official when found."""
        official_mock = MagicMock()
        official_mock.id = uuid.uuid4()
        session = _mock_session()
        session.execute.return_value.scalar_one_or_none.return_value = official_mock

        result = await get_official(session, official_mock.id)
        assert result is official_mock


class TestGetOfficialsForDistrict:
    """Tests for get_officials_for_district."""

    @pytest.mark.asyncio
    async def test_queries_by_district(self) -> None:
        """Queries filter by boundary_type and district_identifier."""
        session = _mock_session()
        await get_officials_for_district(session, "state_senate", "39")
        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        assert "state_senate" in compiled.lower()
        assert "'39'" in compiled


class TestCreateOfficial:
    """Tests for create_official."""

    @pytest.mark.asyncio
    async def test_adds_and_commits(self) -> None:
        """Creating an official adds to session and commits."""
        session = _mock_session()
        session.refresh = AsyncMock()

        await create_official(
            session,
            boundary_type="congressional",
            district_identifier="5",
            full_name="Nikema Williams",
        )
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_duplicate_raises_value_error(self) -> None:
        """IntegrityError on commit is caught and re-raised as ValueError."""
        session = _mock_session()
        session.refresh = AsyncMock()
        session.commit = AsyncMock(side_effect=IntegrityError("dup", {}, None))
        session.rollback = AsyncMock()

        with pytest.raises(ValueError, match="already exists"):
            await create_official(
                session,
                boundary_type="congressional",
                district_identifier="5",
                full_name="Nikema Williams",
            )
        session.rollback.assert_awaited_once()


class TestUpdateOfficial:
    """Tests for update_official."""

    @pytest.mark.asyncio
    async def test_applies_updates(self) -> None:
        """update_official sets attributes on the official."""
        session = _mock_session()
        session.refresh = AsyncMock()

        official = MagicMock()
        official.party = "Democratic"
        official.website = None

        await update_official(session, official, {"party": "Republican", "website": "https://example.com"})
        assert official.party == "Republican"
        assert official.website == "https://example.com"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clears_nullable_field_with_explicit_none(self) -> None:
        """Explicit None in updates clears the field."""
        session = _mock_session()
        session.refresh = AsyncMock()

        official = MagicMock()
        official.party = "Democratic"

        await update_official(session, official, {"party": None})
        # party should be cleared to None
        assert official.party is None

    @pytest.mark.asyncio
    async def test_rejects_non_allowlisted_fields(self) -> None:
        """Fields not in _UPDATABLE_FIELDS are silently ignored (mass-assignment guard)."""
        session = _mock_session()
        session.refresh = AsyncMock()

        official = MagicMock()
        official.status = "auto"
        official.approved_by_id = None
        official.id = uuid.uuid4()
        original_id = official.id

        await update_official(
            session,
            official,
            {"status": "approved", "approved_by_id": uuid.uuid4(), "id": uuid.uuid4()},
        )
        # Internal fields must NOT be modified via update_official
        assert official.status == "auto"
        assert official.approved_by_id is None
        assert official.id == original_id


class TestDeleteOfficial:
    """Tests for delete_official."""

    @pytest.mark.asyncio
    async def test_deletes_and_commits(self) -> None:
        """Deleting an official removes from session and commits."""
        session = _mock_session()
        official = MagicMock()
        official.id = uuid.uuid4()

        await delete_official(session, official)
        session.delete.assert_awaited_once_with(official)
        session.commit.assert_awaited_once()


class TestApproveOfficial:
    """Tests for approve_official."""

    @pytest.mark.asyncio
    async def test_sets_approved_status(self) -> None:
        """Approving sets status, approved_by_id, and approved_at."""
        session = _mock_session()
        session.refresh = AsyncMock()

        official = MagicMock()
        official.id = uuid.uuid4()
        official.status = "auto"
        official.sources = []

        user_id = uuid.uuid4()
        result = await approve_official(session, official, user_id)

        assert result.status == "approved"
        assert result.approved_by_id == user_id
        assert result.approved_at is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_promotes_source_data(self) -> None:
        """When source_id is given, promotes source fields."""
        session = _mock_session()
        session.refresh = AsyncMock()

        source = MagicMock()
        source.id = uuid.uuid4()
        source.full_name = "Updated Name"
        source.first_name = "Updated"
        source.last_name = "Name"
        source.party = "Republican"
        source.title = "Senator"
        source.photo_url = None
        source.term_start_date = None
        source.term_end_date = None
        source.website = "https://updated.example.com"
        source.email = None
        source.phone = None
        source.office_address = None

        official = MagicMock()
        official.id = uuid.uuid4()
        official.status = "auto"
        source.elected_official_id = official.id

        # Mock get_source to return the source
        session.execute.return_value.scalar_one_or_none.return_value = source

        result = await approve_official(session, official, uuid.uuid4(), source_id=source.id)
        assert result.full_name == "Updated Name"
        assert result.party == "Republican"
        assert result.status == "approved"

    @pytest.mark.asyncio
    async def test_approve_with_missing_source_raises(self) -> None:
        """Approving with a source_id that doesn't exist raises ValueError."""
        session = _mock_session()
        session.refresh = AsyncMock()

        official = MagicMock()
        official.id = uuid.uuid4()
        official.status = "auto"

        # get_source returns None
        session.execute.return_value.scalar_one_or_none.return_value = None

        with pytest.raises(ValueError, match="Source record .* not found"):
            await approve_official(session, official, uuid.uuid4(), source_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_approve_with_wrong_official_source_raises(self) -> None:
        """Approving with a source belonging to a different official raises ValueError."""
        session = _mock_session()
        session.refresh = AsyncMock()

        official = MagicMock()
        official.id = uuid.uuid4()
        official.status = "auto"

        source = MagicMock()
        source.id = uuid.uuid4()
        source.elected_official_id = uuid.uuid4()  # Different official

        session.execute.return_value.scalar_one_or_none.return_value = source

        with pytest.raises(ValueError, match="does not belong to official"):
            await approve_official(session, official, uuid.uuid4(), source_id=source.id)

    @pytest.mark.asyncio
    async def test_reapproval_logs_warning(self) -> None:
        """Re-approving an already-approved official logs a warning."""
        session = _mock_session()
        session.refresh = AsyncMock()

        official = MagicMock()
        official.id = uuid.uuid4()
        official.status = "approved"
        official.approved_by_id = uuid.uuid4()
        official.approved_at = datetime.now(UTC)

        with patch("voter_api.services.elected_official_service.logger") as mock_logger:
            await approve_official(session, official, uuid.uuid4())
            mock_logger.warning.assert_called_once()
            assert "Re-approving" in mock_logger.warning.call_args[0][0]


class TestPromoteSourceFields:
    """Tests for _promote_source_fields helper."""

    def test_copies_all_fields(self) -> None:
        """Promotes all normalized fields from source to official."""
        official = MagicMock()
        source = MagicMock()
        source.full_name = "Jane Doe"
        source.first_name = "Jane"
        source.last_name = "Doe"
        source.party = "Independent"
        source.title = "Representative"
        source.photo_url = "https://example.com/photo.jpg"
        source.term_start_date = None
        source.term_end_date = None
        source.website = "https://example.com"
        source.email = "jane@example.com"
        source.phone = "555-1234"
        source.office_address = "123 Main St"

        _promote_source_fields(official, source)

        assert official.full_name == "Jane Doe"
        assert official.party == "Independent"
        assert official.email == "jane@example.com"
        assert official.office_address == "123 Main St"


class TestListSourcesForDistrict:
    """Tests for list_sources_for_district."""

    @pytest.mark.asyncio
    async def test_filters_by_district(self) -> None:
        """Filters sources by boundary_type and district_identifier."""
        session = _mock_session()
        await list_sources_for_district(session, "congressional", "5")
        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        assert "congressional" in compiled.lower()
        assert "'5'" in compiled

    @pytest.mark.asyncio
    async def test_current_only_filter(self) -> None:
        """When current_only=True, filters on is_current."""
        session = _mock_session()
        await list_sources_for_district(session, "congressional", "5", current_only=True)
        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        assert "is_current" in compiled.lower()

    @pytest.mark.asyncio
    async def test_all_sources(self) -> None:
        """When current_only=False, no is_current filter in WHERE clause."""
        session = _mock_session()
        await list_sources_for_district(session, "congressional", "5", current_only=False)
        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        # is_current appears in SELECT (column list) but should NOT be in WHERE
        where_clause = compiled.lower().split("where", 1)[1] if "where" in compiled.lower() else ""
        assert "is_current" not in where_clause


class TestUpsertSourceRecords:
    """Tests for upsert_source_records."""

    @pytest.mark.asyncio
    async def test_inserts_new_record(self) -> None:
        """Inserts a new source record when none exists."""
        session = _mock_session()

        records = [
            OfficialRecord(
                source_name="test_source",
                source_record_id="rec-001",
                boundary_type="congressional",
                district_identifier="5",
                full_name="Nikema Williams",
            )
        ]

        result = await upsert_source_records(session, records)
        assert len(result) == 1
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_record(self) -> None:
        """Updates an existing source record by unique key."""
        existing = MagicMock()
        existing.elected_official_id = None
        existing.fetched_at = datetime.now(UTC)

        session = _mock_session()
        session.execute.return_value.scalar_one_or_none.return_value = existing

        records = [
            OfficialRecord(
                source_name="test_source",
                source_record_id="rec-001",
                boundary_type="congressional",
                district_identifier="5",
                full_name="Nikema Williams Updated",
                party="Democratic",
            )
        ]

        result = await upsert_source_records(session, records)
        assert len(result) == 1
        assert existing.full_name == "Nikema Williams Updated"
        assert existing.party == "Democratic"
        assert existing.is_current is True


class TestAutoCreateOfficialsFromSources:
    """Tests for auto_create_officials_from_sources."""

    @pytest.mark.asyncio
    async def test_creates_official_from_unlinked_source(self) -> None:
        """Creates a new official from an unlinked source record."""
        source = MagicMock()
        source.source_name = "open_states"
        source.source_record_id = "ocd-person/123"
        source.boundary_type = "state_senate"
        source.district_identifier = "39"
        source.full_name = "Sally Harrell"
        source.first_name = "Sally"
        source.last_name = "Harrell"
        source.party = "Democratic"
        source.title = "State Senator"
        source.photo_url = None
        source.term_start_date = None
        source.term_end_date = None
        source.website = None
        source.email = None
        source.phone = None
        source.office_address = None
        source.elected_official_id = None

        session = AsyncMock()
        # First call: find unlinked sources
        unlinked_result = MagicMock()
        unlinked_result.scalars.return_value.all.return_value = [source]
        # Second call: _find_matching_official returns None (no existing official)
        no_match_result = MagicMock()
        no_match_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [unlinked_result, no_match_result]
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        result = await auto_create_officials_from_sources(session, "state_senate", "39")
        assert len(result) == 1
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_links_to_existing_official(self) -> None:
        """Links unlinked source to existing official instead of creating duplicate."""
        existing_official = MagicMock()
        existing_official.id = uuid.uuid4()

        source = MagicMock()
        source.source_name = "open_states"
        source.source_record_id = "ocd-person/123"
        source.boundary_type = "state_senate"
        source.district_identifier = "39"
        source.full_name = "Sally Harrell"
        source.elected_official_id = None

        session = AsyncMock()
        # First call: find unlinked sources
        unlinked_result = MagicMock()
        unlinked_result.scalars.return_value.all.return_value = [source]
        # Second call: _find_matching_official returns existing official
        match_result = MagicMock()
        match_result.scalar_one_or_none.return_value = existing_official

        session.execute.side_effect = [unlinked_result, match_result]
        session.commit = AsyncMock()

        result = await auto_create_officials_from_sources(session, "state_senate", "39")
        assert len(result) == 0  # No new officials created
        assert source.elected_official_id == existing_official.id

    @pytest.mark.asyncio
    async def test_no_unlinked_sources(self) -> None:
        """Returns empty list when no unlinked sources exist."""
        session = AsyncMock()
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute.return_value = empty_result
        session.commit = AsyncMock()

        result = await auto_create_officials_from_sources(session, "congressional", "5")
        assert result == []
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_auto_links_to_existing_official(self) -> None:
        """New source is auto-linked to a matching existing official."""
        existing_official = MagicMock()
        existing_official.id = uuid.uuid4()

        session = AsyncMock()
        # First call: no existing source (insert path)
        no_source_result = MagicMock()
        no_source_result.scalar_one_or_none.return_value = None
        # Second call: _find_matching_official returns existing official
        match_result = MagicMock()
        match_result.scalar_one_or_none.return_value = existing_official

        session.execute.side_effect = [no_source_result, match_result]
        session.commit = AsyncMock()

        records = [
            OfficialRecord(
                source_name="test_source",
                source_record_id="rec-link",
                boundary_type="congressional",
                district_identifier="5",
                full_name="Nikema Williams",
            )
        ]

        result = await upsert_source_records(session, records)
        assert len(result) == 1
        assert result[0].elected_official_id == existing_official.id

    @pytest.mark.asyncio
    async def test_upsert_multiple_records(self) -> None:
        """Multiple records in one call are all upserted."""
        session = AsyncMock()
        # All lookups return None (new inserts)
        no_source_result = MagicMock()
        no_source_result.scalar_one_or_none.return_value = None
        # No matching official for any
        no_match_result = MagicMock()
        no_match_result.scalar_one_or_none.return_value = None

        # For 3 records: each has 2 execute calls (find source + find official)
        session.execute.side_effect = [
            no_source_result,
            no_match_result,
            no_source_result,
            no_match_result,
            no_source_result,
            no_match_result,
        ]
        session.commit = AsyncMock()

        records = [
            OfficialRecord(
                source_name="test",
                source_record_id=f"rec-{i}",
                boundary_type="congressional",
                district_identifier="5",
                full_name=f"Official {i}",
            )
            for i in range(3)
        ]

        result = await upsert_source_records(session, records)
        assert len(result) == 3
        assert session.add.call_count == 3
        session.commit.assert_awaited_once()


class TestFindMatchingOfficial:
    """Tests for _find_matching_official."""

    @pytest.mark.asyncio
    async def test_case_insensitive_name_match(self) -> None:
        """Uses case-insensitive name matching."""
        session = _mock_session()
        record = OfficialRecord(
            source_name="test",
            source_record_id="001",
            boundary_type="congressional",
            district_identifier="5",
            full_name="nikema williams",
        )
        await _find_matching_official(session, record)
        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        assert "upper" in compiled.lower()
