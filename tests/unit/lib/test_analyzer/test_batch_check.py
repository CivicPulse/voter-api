"""Unit tests for batch boundary check library."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.lib.analyzer.batch_check import (
    BatchBoundaryCheckResult,
    VoterNotFoundError,
    check_batch_boundaries,
)

VOTER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
B_ID_1 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
B_ID_2 = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
B_ID_3 = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.fixture(autouse=True)
def patch_find_boundaries_for_point():
    """Patch find_boundaries_for_point to return {} by default for all tests.

    Individual tests that want to assert on determined_identifier should override
    this via their own patch context manager.
    """
    with patch(
        "voter_api.lib.analyzer.batch_check.find_boundaries_for_point",
        new_callable=AsyncMock,
        return_value={},
    ):
        yield


def _make_voter() -> MagicMock:
    voter = MagicMock()
    voter.id = VOTER_ID
    return voter


def _make_location(
    source_type: str,
    lat: float = 33.5,
    lng: float = -84.3,
    confidence: float | None = 0.95,
    point: object = None,
) -> MagicMock:
    loc = MagicMock()
    loc.source_type = source_type
    loc.latitude = lat
    loc.longitude = lng
    loc.confidence_score = confidence
    loc.voter_id = VOTER_ID
    loc.point = point or MagicMock(name=f"point_{source_type}")
    return loc


def _make_boundary(bid: uuid.UUID, btype: str, bident: str) -> MagicMock:
    b = MagicMock()
    b.id = bid
    b.boundary_type = btype
    b.boundary_identifier = bident
    return b


def _make_cross_row(
    source_type: str,
    boundary_id: uuid.UUID,
    boundary_type: str,
    boundary_identifier: str,
    is_contained: bool,
    lat: float = 33.5,
    lng: float = -84.3,
    confidence: float | None = 0.95,
) -> MagicMock:
    row = MagicMock()
    row.source_type = source_type
    row.latitude = lat
    row.longitude = lng
    row.confidence_score = confidence
    row.boundary_id = boundary_id
    row.boundary_type = boundary_type
    row.boundary_identifier = boundary_identifier
    row.is_contained = is_contained
    return row


def _make_session(*execute_side_effects: MagicMock) -> AsyncMock:
    """Build an AsyncMock session with sequential execute() return values."""
    session = AsyncMock()
    session.execute.side_effect = list(execute_side_effects)
    return session


def _scalar_one_or_none_result(value: object) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_all_result(items: list) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _all_result(rows: list) -> MagicMock:
    r = MagicMock()
    r.all.return_value = rows
    return r


# ---------------------------------------------------------------------------
# Happy path tests (US1)
# ---------------------------------------------------------------------------


class TestHappyPath:
    """US1: voter with multiple providers and district boundaries."""

    async def test_two_providers_three_districts_produces_correct_structure(self) -> None:
        """2 providers × 3 districts → 3 DistrictBoundaryResult entries, each with 2 providers."""
        voter = _make_voter()

        # Voter CSV uses unpadded identifiers; boundary DB uses 3-digit zero-padded identifiers.
        registered = {
            "congressional": "5",
            "state_senate": "34",
            "state_house": "42",
        }

        boundaries = [
            _make_boundary(B_ID_1, "congressional", "005"),
            _make_boundary(B_ID_2, "state_senate", "034"),
            _make_boundary(B_ID_3, "state_house", "042"),
        ]

        locations = [
            _make_location("google", lat=33.5, lng=-84.3),
            _make_location("census", lat=33.51, lng=-84.31),
        ]

        cross_rows = [
            _make_cross_row("census", B_ID_1, "congressional", "005", True),
            _make_cross_row("census", B_ID_2, "state_senate", "034", True),
            _make_cross_row("census", B_ID_3, "state_house", "042", False),
            _make_cross_row("google", B_ID_1, "congressional", "005", True),
            _make_cross_row("google", B_ID_2, "state_senate", "034", False),
            _make_cross_row("google", B_ID_3, "state_house", "042", True),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),  # voter lookup
            _scalars_all_result(boundaries),  # boundary query
            _scalars_all_result(locations),  # geocoded_locations query
            _all_result(cross_rows),  # cross-join query
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert isinstance(result, BatchBoundaryCheckResult)
        assert result.voter_id == VOTER_ID
        assert result.total_locations == 2
        assert result.total_districts == 3
        assert len(result.districts) == 3

        # Each district should have exactly 2 provider entries
        for district in result.districts:
            assert district.has_geometry is True
            assert len(district.providers) == 2

    async def test_provider_summary_counts_matched_vs_checked(self) -> None:
        """provider_summary correctly counts districts_matched (True rows) vs districts_checked."""
        voter = _make_voter()

        registered = {"congressional": "5", "state_senate": "34"}

        boundaries = [
            _make_boundary(B_ID_1, "congressional", "005"),
            _make_boundary(B_ID_2, "state_senate", "034"),
        ]

        locations = [
            _make_location("google", lat=33.5, lng=-84.3, confidence=0.9),
            _make_location("census", lat=33.51, lng=-84.31, confidence=None),
        ]

        # google: contained in congressional (True), not in state_senate (False) → matched=1, checked=2
        # census: contained in both (True, True) → matched=2, checked=2
        cross_rows = [
            _make_cross_row("census", B_ID_1, "congressional", "005", True, confidence=None),
            _make_cross_row("census", B_ID_2, "state_senate", "034", True, confidence=None),
            _make_cross_row("google", B_ID_1, "congressional", "005", True, confidence=0.9),
            _make_cross_row("google", B_ID_2, "state_senate", "034", False, confidence=0.9),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert len(result.provider_summary) == 2

        by_source = {ps.source_type: ps for ps in result.provider_summary}

        assert by_source["google"].districts_checked == 2
        assert by_source["google"].districts_matched == 1
        assert by_source["google"].latitude == pytest.approx(33.5)
        assert by_source["google"].longitude == pytest.approx(-84.3)
        assert by_source["google"].confidence_score == pytest.approx(0.9)

        assert by_source["census"].districts_checked == 2
        assert by_source["census"].districts_matched == 2
        assert by_source["census"].confidence_score is None

    async def test_missing_boundary_has_geometry_false_empty_providers(self) -> None:
        """Registered district with no matching boundary row → has_geometry=False, providers=[]."""
        voter = _make_voter()

        registered = {
            "congressional": "5",
            "state_senate": "99",  # this one has no boundary in DB
        }

        # Only congressional boundary exists in DB
        boundaries = [_make_boundary(B_ID_1, "congressional", "005")]

        locations = [_make_location("google")]

        cross_rows = [
            _make_cross_row("google", B_ID_1, "congressional", "005", True),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert len(result.districts) == 2

        by_type = {d.boundary_type: d for d in result.districts}

        assert by_type["congressional"].has_geometry is True
        assert by_type["congressional"].boundary_id == B_ID_1
        assert len(by_type["congressional"].providers) == 1

        assert by_type["state_senate"].has_geometry is False
        assert by_type["state_senate"].boundary_id is None
        assert by_type["state_senate"].providers == []

    async def test_voter_not_found_raises_error(self) -> None:
        """VoterNotFoundError raised when voter does not exist."""
        session = _make_session(_scalar_one_or_none_result(None))

        with pytest.raises(VoterNotFoundError, match=str(VOTER_ID)):
            await check_batch_boundaries(session, VOTER_ID)

        # Only one execute call should have been made
        assert session.execute.call_count == 1


# ---------------------------------------------------------------------------
# US2: no geocoded locations
# ---------------------------------------------------------------------------


class TestNoGeocodedLocations:
    """US2: voter has registered districts but no geocoded locations."""

    async def test_no_locations_returns_zero_total_and_empty_summary(self) -> None:
        """total_locations=0, provider_summary=[], districts have correct has_geometry status."""
        voter = _make_voter()

        registered = {"congressional": "5", "state_senate": "34"}

        boundaries = [
            _make_boundary(B_ID_1, "congressional", "005"),
            _make_boundary(B_ID_2, "state_senate", "034"),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),  # voter lookup
            _scalars_all_result(boundaries),  # boundary query
            _scalars_all_result([]),  # empty geocoded_locations
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert result.total_locations == 0
        assert result.provider_summary == []
        assert result.total_districts == 2
        assert len(result.districts) == 2

        for district in result.districts:
            assert district.has_geometry is True
            assert district.providers == []

    async def test_no_locations_missing_boundary_still_has_geometry_false(self) -> None:
        """When no locations and a district has no boundary, has_geometry=False."""
        voter = _make_voter()

        registered = {
            "congressional": "5",
            "state_senate": "99",  # no boundary in DB
        }

        boundaries = [_make_boundary(B_ID_1, "congressional", "005")]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result([]),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        by_type = {d.boundary_type: d for d in result.districts}
        assert by_type["congressional"].has_geometry is True
        assert by_type["state_senate"].has_geometry is False

    async def test_no_locations_no_cross_join_executed(self) -> None:
        """Cross-join query is skipped entirely when there are no geocoded locations."""
        voter = _make_voter()
        registered = {"congressional": "5"}
        boundaries = [_make_boundary(B_ID_1, "congressional", "005")]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result([]),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            await check_batch_boundaries(session, VOTER_ID)

        # Only 3 execute calls: voter + boundaries + locations (no cross-join)
        assert session.execute.call_count == 3


# ---------------------------------------------------------------------------
# US3: no registered districts
# ---------------------------------------------------------------------------


class TestNoRegisteredDistricts:
    """US3: voter has geocoded locations but no registered district assignments."""

    async def test_no_districts_returns_empty_districts_list(self) -> None:
        """total_districts=0, districts=[], provider_summary lists all providers."""
        voter = _make_voter()

        locations = [
            _make_location("google", lat=33.5, lng=-84.3, confidence=0.9),
            _make_location("census", lat=33.51, lng=-84.31, confidence=None),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),  # voter lookup
            _scalars_all_result(locations),  # geocoded_locations (no boundary query)
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value={},
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert result.total_districts == 0
        assert result.districts == []
        assert result.total_locations == 2

    async def test_no_districts_provider_summary_has_zero_counts(self) -> None:
        """provider_summary lists all providers with districts_matched=0, districts_checked=0."""
        voter = _make_voter()

        locations = [
            _make_location("google", lat=33.5, lng=-84.3, confidence=0.85),
            _make_location("census", lat=33.51, lng=-84.31, confidence=None),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(locations),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value={},
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert len(result.provider_summary) == 2

        by_source = {ps.source_type: ps for ps in result.provider_summary}

        assert by_source["google"].districts_matched == 0
        assert by_source["google"].districts_checked == 0
        assert by_source["google"].latitude == pytest.approx(33.5)
        assert by_source["google"].longitude == pytest.approx(-84.3)
        assert by_source["google"].confidence_score == pytest.approx(0.85)

        assert by_source["census"].districts_matched == 0
        assert by_source["census"].districts_checked == 0
        assert by_source["census"].confidence_score is None

    async def test_no_districts_skips_boundary_and_cross_join_queries(self) -> None:
        """When no registered districts, boundary and cross-join queries are not executed."""
        voter = _make_voter()
        locations = [_make_location("google")]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(locations),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value={},
        ):
            await check_batch_boundaries(session, VOTER_ID)

        # Only 2 execute calls: voter + locations (no boundary query, no cross-join)
        assert session.execute.call_count == 2

    async def test_no_districts_and_no_locations(self) -> None:
        """Edge case: voter with no districts AND no locations returns all-empty result."""
        voter = _make_voter()

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result([]),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value={},
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert result.total_districts == 0
        assert result.total_locations == 0
        assert result.districts == []
        assert result.provider_summary == []


# ---------------------------------------------------------------------------
# Regression: identifier format mismatch between voter CSV and boundary DB
# ---------------------------------------------------------------------------


class TestIdentifierNormalization:
    """Regression tests for #97 — voter CSV vs boundary DB identifier format mismatch.

    Numeric district types: voter CSV stores '8', boundary DB stores '008'.
    Precinct types: voter CSV stores 'HO7', boundary DB stores '021HO7'.
    """

    async def test_zero_padded_numeric_boundary_matched_by_unpadded_voter_identifier(
        self,
    ) -> None:
        """Voter with congressional='8' matches boundary with identifier '008' (providers populated)."""
        voter = _make_voter()

        # Voter CSV format: no leading zeros
        registered = {"congressional": "8"}

        # Boundary DB format: zero-padded to 3 digits
        boundaries = [_make_boundary(B_ID_1, "congressional", "008")]

        locations = [_make_location("census")]

        cross_rows = [
            _make_cross_row("census", B_ID_1, "congressional", "008", True),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert len(result.districts) == 1
        district = result.districts[0]
        assert district.has_geometry is True
        assert district.boundary_identifier == "8"  # response uses voter's raw format
        assert len(district.providers) == 1
        assert district.providers[0].source_type == "census"
        assert district.providers[0].is_contained is True

    async def test_precinct_suffix_matched_against_fips_prefixed_db_identifier(
        self,
    ) -> None:
        """Voter with county_precinct='HO7' matches boundary with identifier '021HO7'."""
        voter = _make_voter()

        # Voter CSV format: precinct code without county FIPS prefix
        registered = {"county_precinct": "HO7"}

        # Boundary DB format: 3-digit county FIPS prefix + precinct code
        boundaries = [_make_boundary(B_ID_1, "county_precinct", "021HO7")]

        locations = [_make_location("google")]

        cross_rows = [
            _make_cross_row("google", B_ID_1, "county_precinct", "021HO7", True),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert len(result.districts) == 1
        district = result.districts[0]
        assert district.has_geometry is True
        assert district.boundary_identifier == "HO7"  # response uses voter's raw format
        assert len(district.providers) == 1
        assert district.providers[0].source_type == "google"
        assert district.providers[0].is_contained is True

    async def test_mixed_numeric_and_precinct_districts_all_populated(self) -> None:
        """Multiple district types with mismatched formats all resolve correctly."""
        voter = _make_voter()

        registered = {
            "congressional": "8",
            "state_senate": "1",
            "state_house": "142",  # already 3 digits — no padding needed
            "county_precinct": "HO7",
        }

        b_id_4 = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        boundaries = [
            _make_boundary(B_ID_1, "congressional", "008"),
            _make_boundary(B_ID_2, "state_senate", "001"),
            _make_boundary(B_ID_3, "state_house", "142"),
            _make_boundary(b_id_4, "county_precinct", "021HO7"),
        ]

        locations = [_make_location("census")]

        cross_rows = [
            _make_cross_row("census", B_ID_1, "congressional", "008", True),
            _make_cross_row("census", B_ID_2, "state_senate", "001", True),
            _make_cross_row("census", B_ID_3, "state_house", "142", True),
            _make_cross_row("census", b_id_4, "county_precinct", "021HO7", True),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert result.total_districts == 4
        by_type = {d.boundary_type: d for d in result.districts}

        # All districts found and populated
        for btype in ("congressional", "state_senate", "state_house", "county_precinct"):
            assert by_type[btype].has_geometry is True, f"{btype} should have geometry"
            assert len(by_type[btype].providers) == 1, f"{btype} should have 1 provider"

        # Response uses voter identifiers, not DB identifiers
        assert by_type["congressional"].boundary_identifier == "8"
        assert by_type["state_senate"].boundary_identifier == "1"
        assert by_type["state_house"].boundary_identifier == "142"
        assert by_type["county_precinct"].boundary_identifier == "HO7"

    async def test_padded_voter_numeric_id_matches_db_padded_boundary(self) -> None:
        """Voter with congressional='08' matches boundary '008'; raw format '08' is preserved.

        Regression for PR #98 Thread 1: str(int(db_identifier)) was '8', causing a miss
        when the voter's registered value was '08'.
        """
        voter = _make_voter()

        # Voter CSV stores '08' (two-digit zero-padded), DB stores '008' (three-digit)
        registered = {"congressional": "08"}
        boundaries = [_make_boundary(B_ID_1, "congressional", "008")]
        locations = [_make_location("census")]
        cross_rows = [_make_cross_row("census", B_ID_1, "congressional", "008", True)]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert len(result.districts) == 1
        district = result.districts[0]
        assert district.has_geometry is True
        assert district.boundary_identifier == "08"  # voter's raw format preserved
        assert len(district.providers) == 1

    async def test_short_voter_precinct_does_not_false_match_shorter_db_identifier(
        self,
    ) -> None:
        """Voter with county_precinct='7' does NOT match boundary 'HO7' (len ≤ 3).

        Regression for PR #98 Thread 3: missing len(db_identifier) > 3 guard caused
        '7'.endswith('7') → True against short non-FIPS-prefixed boundary identifiers.
        """
        voter = _make_voter()

        # Voter has precinct '7'; DB has 'HO7' (not a FIPS-prefixed identifier, len=3)
        registered = {"county_precinct": "7"}
        boundaries = [_make_boundary(B_ID_1, "county_precinct", "HO7")]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result([]),  # no locations needed — testing lookup only
        )

        with patch(
            "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
            return_value=registered,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        assert len(result.districts) == 1
        district = result.districts[0]
        assert district.has_geometry is False  # short DB identifier must not match


# ---------------------------------------------------------------------------
# determined_identifier populated on mismatch (issue #99)
# ---------------------------------------------------------------------------


class TestDeterminedIdentifier:
    """determined_identifier is populated when is_contained=False, None when True."""

    async def test_mismatch_populates_determined_identifier(self) -> None:
        """When a provider misses a boundary, determined_identifier reflects the actual containing district."""
        voter = _make_voter()
        registered = {"congressional": "5", "state_senate": "34"}

        boundaries = [
            _make_boundary(B_ID_1, "congressional", "005"),
            _make_boundary(B_ID_2, "state_senate", "034"),
        ]

        google_point = MagicMock(name="google_point")
        locations = [_make_location("google", lat=33.5, lng=-84.3, point=google_point)]

        # google is NOT contained in state_senate but IS in congressional
        cross_rows = [
            _make_cross_row("google", B_ID_1, "congressional", "005", True),
            _make_cross_row("google", B_ID_2, "state_senate", "034", False),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        # find_boundaries_for_point returns: google point is actually in district "007"
        fake_determined = {"state_senate": "007", "congressional": "005"}

        with (
            patch(
                "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
                return_value=registered,
            ),
            patch(
                "voter_api.lib.analyzer.batch_check.find_boundaries_for_point",
                new_callable=AsyncMock,
                return_value=fake_determined,
            ) as mock_fbfp,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        # find_boundaries_for_point called once for google (first miss)
        mock_fbfp.assert_awaited_once_with(session, google_point)

        by_type = {d.boundary_type: d for d in result.districts}

        # congressional: contained → determined_identifier is None
        cong_providers = {p.source_type: p for p in by_type["congressional"].providers}
        assert cong_providers["google"].is_contained is True
        assert cong_providers["google"].determined_identifier is None

        # state_senate: not contained → determined_identifier = "007"
        senate_providers = {p.source_type: p for p in by_type["state_senate"].providers}
        assert senate_providers["google"].is_contained is False
        assert senate_providers["google"].determined_identifier == "007"

    async def test_contained_provider_leaves_determined_identifier_none(self) -> None:
        """When a provider is contained in all boundaries, determined_identifier stays None."""
        voter = _make_voter()
        registered = {"congressional": "5"}
        boundaries = [_make_boundary(B_ID_1, "congressional", "005")]
        locations = [_make_location("google")]
        cross_rows = [_make_cross_row("google", B_ID_1, "congressional", "005", True)]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        with (
            patch(
                "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
                return_value=registered,
            ),
            patch(
                "voter_api.lib.analyzer.batch_check.find_boundaries_for_point",
                new_callable=AsyncMock,
            ) as mock_fbfp,
        ):
            result = await check_batch_boundaries(session, VOTER_ID)

        # No misses → find_boundaries_for_point never called
        mock_fbfp.assert_not_awaited()

        district = result.districts[0]
        assert district.providers[0].is_contained is True
        assert district.providers[0].determined_identifier is None

    async def test_multiple_providers_find_boundaries_called_once_per_provider(self) -> None:
        """find_boundaries_for_point is called at most once per provider, not per row."""
        voter = _make_voter()
        registered = {"congressional": "5", "state_senate": "34"}

        boundaries = [
            _make_boundary(B_ID_1, "congressional", "005"),
            _make_boundary(B_ID_2, "state_senate", "034"),
        ]

        google_point = MagicMock(name="google_point")
        census_point = MagicMock(name="census_point")
        locations = [
            _make_location("google", point=google_point),
            _make_location("census", point=census_point),
        ]

        # Both providers miss both districts
        cross_rows = [
            _make_cross_row("google", B_ID_1, "congressional", "005", False),
            _make_cross_row("google", B_ID_2, "state_senate", "034", False),
            _make_cross_row("census", B_ID_1, "congressional", "005", False),
            _make_cross_row("census", B_ID_2, "state_senate", "034", False),
        ]

        session = _make_session(
            _scalar_one_or_none_result(voter),
            _scalars_all_result(boundaries),
            _scalars_all_result(locations),
            _all_result(cross_rows),
        )

        with (
            patch(
                "voter_api.lib.analyzer.batch_check.extract_registered_boundaries",
                return_value=registered,
            ),
            patch(
                "voter_api.lib.analyzer.batch_check.find_boundaries_for_point",
                new_callable=AsyncMock,
                return_value={},
            ) as mock_fbfp,
        ):
            await check_batch_boundaries(session, VOTER_ID)

        # Exactly 2 calls: one per provider (not 4 for each row)
        assert mock_fbfp.await_count == 2
