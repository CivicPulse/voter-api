"""Extended tests for precinct metadata service — covering uncovered functions."""

import io
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger

from voter_api.services.precinct_metadata_service import (
    _build_precinct_indexes,
    _extract_precinct_fields,
    _normalize_precinct_name,
    get_precinct_metadata_batch,
    get_precinct_metadata_by_boundary,
    get_precinct_metadata_by_county_multi_strategy,
    upsert_precinct_metadata,
)


class TestExtractPrecinctFields:
    """Tests for _extract_precinct_fields."""

    def test_full_properties(self) -> None:
        props = {
            "DISTRICT": "123",
            "CTYSOSID": "001",
            "FIPS": "13121",
            "FIPS2": "121",
            "CTYNAME": "FULTON",
            "CONTY": "060",
            "PRECINCT_I": "SS01",
            "PRECINCT_N": "Sandy Springs 01",
            "AREA": "1234567.89",
        }
        result = _extract_precinct_fields(props)
        assert result["sos_district_id"] == "123"
        assert result["sos_id"] == "001"
        assert result["fips"] == "13121"
        assert result["fips_county"] == "121"
        assert result["county_name"] == "FULTON"
        assert result["county_number"] == "060"
        assert result["precinct_id"] == "SS01"
        assert result["precinct_name"] == "Sandy Springs 01"
        assert result["area"] == Decimal("1234567.89")

    def test_missing_optional_fields(self) -> None:
        props = {"DISTRICT": "123", "FIPS": "13121"}
        result = _extract_precinct_fields(props)
        assert result["sos_district_id"] == "123"
        assert result["fips"] == "13121"
        assert "sos_id" not in result

    def test_invalid_area_becomes_none(self) -> None:
        props = {"AREA": "not-a-number", "DISTRICT": "123"}
        result = _extract_precinct_fields(props)
        assert "area" not in result  # Invalid decimal excluded

    def test_empty_properties(self) -> None:
        result = _extract_precinct_fields({})
        assert result == {}

    def test_strips_whitespace(self) -> None:
        props = {"DISTRICT": "  123  ", "CTYNAME": "  FULTON  "}
        result = _extract_precinct_fields(props)
        assert result["sos_district_id"] == "123"
        assert result["county_name"] == "FULTON"


class TestUpsertPrecinctMetadata:
    """Tests for upsert_precinct_metadata."""

    @pytest.mark.asyncio
    async def test_creates_new_record(self) -> None:
        session = AsyncMock()
        boundary_id = uuid.uuid4()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        props = {
            "DISTRICT": "123",
            "FIPS": "13121",
            "FIPS2": "121",
            "CTYNAME": "FULTON",
            "PRECINCT_I": "SS01",
            "PRECINCT_N": "Sandy Springs 01",
        }

        record = await upsert_precinct_metadata(session, boundary_id, props)
        assert record is not None
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_record(self) -> None:
        session = AsyncMock()
        boundary_id = uuid.uuid4()
        existing = MagicMock()

        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        session.execute.return_value = result

        props = {
            "DISTRICT": "456",
            "FIPS": "13121",
            "FIPS2": "121",
            "CTYNAME": "FULTON",
            "PRECINCT_I": "SS01",
            "PRECINCT_N": "Sandy Springs 01",
        }

        record = await upsert_precinct_metadata(session, boundary_id, props)
        assert record is existing
        # Verify fields were updated
        assert existing.sos_district_id == "456"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing_required(self) -> None:
        session = AsyncMock()
        boundary_id = uuid.uuid4()

        # Missing required fields
        props = {"DISTRICT": "123"}
        record = await upsert_precinct_metadata(session, boundary_id, props)
        assert record is None


class TestGetPrecinctMetadataBatch:
    """Tests for get_precinct_metadata_batch."""

    @pytest.mark.asyncio
    async def test_returns_records_by_boundary_id(self) -> None:
        session = AsyncMock()
        bid1 = uuid.uuid4()
        bid2 = uuid.uuid4()

        rec1 = MagicMock()
        rec1.boundary_id = bid1
        rec2 = MagicMock()
        rec2.boundary_id = bid2

        result = MagicMock()
        result.scalars.return_value.all.return_value = [rec1, rec2]
        session.execute.return_value = result

        records = await get_precinct_metadata_batch(session, [bid1, bid2])
        assert bid1 in records
        assert bid2 in records

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self) -> None:
        session = AsyncMock()

        records = await get_precinct_metadata_batch(session, [])
        assert records == {}
        session.execute.assert_not_awaited()


class TestGetPrecinctMetadataByBoundary:
    """Tests for get_precinct_metadata_by_boundary."""

    @pytest.mark.asyncio
    async def test_returns_record_when_found(self) -> None:
        session = AsyncMock()
        record = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = record
        session.execute.return_value = result

        found = await get_precinct_metadata_by_boundary(session, uuid.uuid4())
        assert found is record

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        found = await get_precinct_metadata_by_boundary(session, uuid.uuid4())
        assert found is None


class TestNormalizePrecinctName:
    """Tests for _normalize_precinct_name."""

    def test_lowercase_and_strip(self) -> None:
        assert _normalize_precinct_name("  SANDY SPRINGS  ") == "sandy springs"

    def test_removes_precinct_prefix(self) -> None:
        assert _normalize_precinct_name("Precinct 1") == "1"

    def test_removes_pct_prefix(self) -> None:
        assert _normalize_precinct_name("PCT 5") == "5"

    def test_removes_prec_prefix_with_dot(self) -> None:
        assert _normalize_precinct_name("Prec. 12") == "12"

    def test_strips_punctuation(self) -> None:
        assert _normalize_precinct_name("Sandy Springs - 01") == "sandy springs 01"

    def test_numeric_strips_leading_zeros(self) -> None:
        assert _normalize_precinct_name("007") == "7"

    def test_zero_stays_as_zero(self) -> None:
        assert _normalize_precinct_name("000") == "0"

    def test_empty_string(self) -> None:
        assert _normalize_precinct_name("") == ""

    def test_mixed_case_and_whitespace(self) -> None:
        assert _normalize_precinct_name("  PcT  3a  ") == "3a"

    def test_non_numeric_preserves_leading_zeros(self) -> None:
        assert _normalize_precinct_name("01A") == "01a"

    def test_removes_prc_token(self) -> None:
        assert _normalize_precinct_name("PRC 42") == "42"


def _mock_precinct_meta(
    precinct_id: str,
    precinct_name: str,
    sos_id: str | None = None,
    county_name: str = "HOUSTON",
) -> MagicMock:
    """Create a mock PrecinctMetadata record."""
    m = MagicMock()
    m.precinct_id = precinct_id
    m.precinct_name = precinct_name
    m.sos_id = sos_id
    m.county_name = county_name
    m.boundary_id = uuid.uuid4()
    return m


class TestBuildPrecinctIndexes:
    """Tests for _build_precinct_indexes."""

    def test_builds_all_three_indexes(self) -> None:
        rec = _mock_precinct_meta("P01", "Sandy Springs", sos_id="C001")
        by_pid, by_sos, by_name = _build_precinct_indexes([rec])
        assert "P01" in by_pid
        assert "C001" in by_sos
        assert "sandy springs" in by_name
        assert by_name["sandy springs"] == [rec]

    def test_precinct_id_uppercased(self) -> None:
        rec = _mock_precinct_meta("p01", "Test")
        by_pid, _, _ = _build_precinct_indexes([rec])
        assert "P01" in by_pid
        assert "p01" not in by_pid

    def test_sos_id_none_excluded(self) -> None:
        rec = _mock_precinct_meta("P01", "Test", sos_id=None)
        _, by_sos, _ = _build_precinct_indexes([rec])
        assert by_sos == {}

    def test_duplicate_precinct_id_logs_warning(self) -> None:
        rec1 = _mock_precinct_meta("P01", "First")
        rec2 = _mock_precinct_meta("P01", "Second")
        sink = io.StringIO()
        handler_id = logger.add(sink, format="{message}")
        try:
            by_pid, _, _ = _build_precinct_indexes([rec1, rec2])
            # Last record wins
            assert by_pid["P01"] is rec2
            assert "Duplicate precinct_id" in sink.getvalue()
        finally:
            logger.remove(handler_id)

    def test_duplicate_sos_id_logs_warning(self) -> None:
        rec1 = _mock_precinct_meta("P01", "First", sos_id="C001")
        rec2 = _mock_precinct_meta("P02", "Second", sos_id="C001")
        sink = io.StringIO()
        handler_id = logger.add(sink, format="{message}")
        try:
            _, by_sos, _ = _build_precinct_indexes([rec1, rec2])
            # Last record wins
            assert by_sos["C001"] is rec2
            assert "Duplicate sos_id" in sink.getvalue()
        finally:
            logger.remove(handler_id)

    def test_empty_normalized_name_excluded(self) -> None:
        """Records whose name normalizes to empty are excluded from name index."""
        rec = _mock_precinct_meta("P01", "---")  # normalizes to ""
        _, _, by_name = _build_precinct_indexes([rec])
        assert by_name == {}

    def test_name_collision_builds_list(self) -> None:
        rec1 = _mock_precinct_meta("P01", "Precinct 1")
        rec2 = _mock_precinct_meta("P02", "PCT 1")  # both normalize to "1"
        _, _, by_name = _build_precinct_indexes([rec1, rec2])
        assert len(by_name["1"]) == 2

    def test_empty_records(self) -> None:
        by_pid, by_sos, by_name = _build_precinct_indexes([])
        assert by_pid == {}
        assert by_sos == {}
        assert by_name == {}


class TestGetPrecinctMetadataMultiStrategy:
    """Tests for get_precinct_metadata_by_county_multi_strategy."""

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self) -> None:
        session = AsyncMock()
        result = await get_precinct_metadata_by_county_multi_strategy(session, "Houston", [])
        assert result == {}
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_strategy_1_exact_precinct_id_match(self) -> None:
        rec = _mock_precinct_meta("SS01", "Sandy Springs 01", sos_id="C001")
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec]
        session.execute.return_value = query_result

        result = await get_precinct_metadata_by_county_multi_strategy(session, "Houston", ["SS01"])
        assert "SS01" in result
        assert result["SS01"] is rec

    @pytest.mark.asyncio
    async def test_strategy_2_sos_id_fallback(self) -> None:
        rec = _mock_precinct_meta("SS01", "Sandy Springs 01", sos_id="C099")
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec]
        session.execute.return_value = query_result

        # SOS election data uses "C099" as the precinct ID, which doesn't
        # match precinct_id="SS01" but matches sos_id="C099".
        result = await get_precinct_metadata_by_county_multi_strategy(session, "Houston", ["C099"])
        assert "C099" in result
        assert result["C099"] is rec

    @pytest.mark.asyncio
    async def test_strategy_3_fuzzy_name_fallback(self) -> None:
        rec = _mock_precinct_meta("SS01", "Sandy Springs 01")
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec]
        session.execute.return_value = query_result

        # SOS ID "X99" matches neither precinct_id nor sos_id,
        # but name "SANDY SPRINGS 01" normalizes to match.
        result = await get_precinct_metadata_by_county_multi_strategy(
            session,
            "Houston",
            ["X99"],
            precinct_names={"X99": "SANDY SPRINGS 01"},
        )
        assert "X99" in result
        assert result["X99"] is rec

    @pytest.mark.asyncio
    async def test_all_strategies_combined(self) -> None:
        rec1 = _mock_precinct_meta("P01", "Precinct 1", sos_id="C001")
        # rec2 has a different precinct_name than the SOS name so that
        # only sos_id matching (strategy 2) can resolve it — strategy 3
        # would not match "Zone Two" to "Precinct 2".
        rec2 = _mock_precinct_meta("P02", "Zone Two", sos_id="C002")
        rec3 = _mock_precinct_meta("P03", "Annex", sos_id="C003")

        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec1, rec2, rec3]
        session.execute.return_value = query_result

        result = await get_precinct_metadata_by_county_multi_strategy(
            session,
            "Houston",
            ["P01", "C002", "NOMATCH"],
            precinct_names={"P01": "Precinct 1", "C002": "Precinct 2", "NOMATCH": "Annex"},
        )
        # P01 matches via strategy 1 (precinct_id)
        assert result["P01"] is rec1
        # C002 matches via strategy 2 (sos_id) — name "Precinct 2" ≠ "Zone Two"
        assert result["C002"] is rec2
        # NOMATCH matches via strategy 3 (name "Annex" → "annex")
        assert result["NOMATCH"] is rec3

    @pytest.mark.asyncio
    async def test_no_match_returns_empty_for_id(self) -> None:
        rec = _mock_precinct_meta("P01", "Precinct 1")
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec]
        session.execute.return_value = query_result

        result = await get_precinct_metadata_by_county_multi_strategy(
            session,
            "Houston",
            ["UNKNOWN"],
            precinct_names={"UNKNOWN": "Nonexistent Precinct"},
        )
        assert "UNKNOWN" not in result

    @pytest.mark.asyncio
    async def test_no_county_records_returns_empty(self) -> None:
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = []
        session.execute.return_value = query_result

        result = await get_precinct_metadata_by_county_multi_strategy(session, "Nonexistent", ["P01"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self) -> None:
        rec = _mock_precinct_meta("ss01", "Sandy Springs", sos_id="c099")
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec]
        session.execute.return_value = query_result

        # Uppercase input should match lowercase precinct_id
        result = await get_precinct_metadata_by_county_multi_strategy(session, "Houston", ["SS01"])
        assert "SS01" in result

    @pytest.mark.asyncio
    async def test_without_precinct_names_skips_strategy_3(self) -> None:
        rec = _mock_precinct_meta("P01", "Precinct 1")
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec]
        session.execute.return_value = query_result

        # No precinct_names provided — strategy 3 not attempted
        result = await get_precinct_metadata_by_county_multi_strategy(session, "Houston", ["UNKNOWN"])
        assert "UNKNOWN" not in result

    @pytest.mark.asyncio
    async def test_strategy_3_skips_ambiguous_name_collision(self) -> None:
        """When two precincts normalize to the same name, fuzzy match is skipped."""
        rec1 = _mock_precinct_meta("P01", "Precinct 1")
        rec2 = _mock_precinct_meta("P02", "PCT 1")  # normalizes to "1" — same as rec1
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec1, rec2]
        session.execute.return_value = query_result

        result = await get_precinct_metadata_by_county_multi_strategy(
            session,
            "Houston",
            ["X99"],
            precinct_names={"X99": "Precinct 1"},
        )
        # X99 doesn't match by ID/sos_id, and normalized name "1" is ambiguous
        assert "X99" not in result

    @pytest.mark.asyncio
    async def test_strategy_3_matches_unique_skips_ambiguous(self) -> None:
        """Fuzzy match returns unique matches and skips ambiguous ones."""
        rec1 = _mock_precinct_meta("P01", "Precinct 1")
        rec2 = _mock_precinct_meta("P02", "PCT 1")  # collision with rec1
        rec3 = _mock_precinct_meta("P03", "Annex")  # unique name
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec1, rec2, rec3]
        session.execute.return_value = query_result

        result = await get_precinct_metadata_by_county_multi_strategy(
            session,
            "Houston",
            ["X99", "Y88"],
            precinct_names={"X99": "Precinct 1", "Y88": "Annex"},
        )
        assert "X99" not in result  # ambiguous
        assert "Y88" in result  # unique match
        assert result["Y88"] is rec3

    @pytest.mark.asyncio
    async def test_strategy_3_excludes_already_matched_records(self) -> None:
        """Strategy 3 should not re-match a record already consumed by strategy 1."""
        rec = _mock_precinct_meta("P01", "Sandy Springs")
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [rec]
        session.execute.return_value = query_result

        # P01 matches via strategy 1. X99 has the same name as rec but should
        # NOT match because rec is already consumed.
        result = await get_precinct_metadata_by_county_multi_strategy(
            session,
            "Houston",
            ["P01", "X99"],
            precinct_names={"P01": "Sandy Springs", "X99": "Sandy Springs"},
        )
        assert result["P01"] is rec
        assert "X99" not in result
