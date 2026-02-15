"""Unit tests for the Congress.gov provider."""

from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from voter_api.lib.officials.base import OfficialsProviderError
from voter_api.lib.officials.congress_gov import CongressGovProvider

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

_SAMPLE_REP_SUMMARY = {
    "bioguideId": "W000788",
    "name": "Nikema Williams",
    "firstName": "Nikema",
    "lastName": "Williams",
    "partyName": "Democratic",
    "state": "Georgia",
    "district": 5,
    "url": "https://api.congress.gov/v3/member/W000788",
}

_SAMPLE_REP_DETAIL = {
    "bioguideId": "W000788",
    "directOrderName": "Nikema Williams",
    "firstName": "Nikema",
    "lastName": "Williams",
    "partyName": "Democratic",
    "depiction": {
        "imageUrl": "https://example.com/williams.jpg",
    },
    "officialWebsiteUrl": "https://nikemawilliams.house.gov",
    "phoneNumber": "202-225-3801",
    "officeAddress": "1406 Longworth HOB, Washington, DC 20515",
    "terms": [
        {"startYear": 2021, "endYear": 2023, "chamber": "House"},
        {"startYear": 2023, "endYear": 2025, "chamber": "House"},
        {"startYear": 2025, "endYear": 2027, "chamber": "House"},
    ],
}

_SAMPLE_SENATOR_SUMMARY = {
    "bioguideId": "W000790",
    "name": "Raphael Warnock",
    "firstName": "Raphael",
    "lastName": "Warnock",
    "partyName": "Democratic",
    "state": "Georgia",
    "district": None,
    "url": "https://api.congress.gov/v3/member/W000790",
}

_SAMPLE_SENATOR_DETAIL = {
    "bioguideId": "W000790",
    "directOrderName": "Raphael Warnock",
    "firstName": "Raphael",
    "lastName": "Warnock",
    "partyName": "Democratic",
    "depiction": {
        "imageUrl": "https://example.com/warnock.jpg",
    },
    "officialWebsiteUrl": "https://warnock.senate.gov",
    "phoneNumber": "202-224-3643",
    "officeAddress": "388 Russell SOB, Washington, DC 20510",
    "terms": [
        {"startYear": 2021, "endYear": 2027, "chamber": "Senate"},
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCongressGovProviderName:
    def test_provider_name(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        assert provider.provider_name == "congress_gov"

    def test_default_congress(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        assert provider._congress == 119

    def test_custom_congress(self) -> None:
        provider = CongressGovProvider(api_key="test-key", congress=118)
        assert provider._congress == 118


class TestFieldMapping:
    """Test mapping of Congress.gov member data to OfficialRecord."""

    def test_maps_representative(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        record = provider._map_member(_SAMPLE_REP_SUMMARY, _SAMPLE_REP_DETAIL)

        assert record.source_name == "congress_gov"
        assert record.source_record_id == "W000788"
        assert record.boundary_type == "congressional"
        assert record.district_identifier == "5"
        assert record.full_name == "Nikema Williams"
        assert record.first_name == "Nikema"
        assert record.last_name == "Williams"
        assert record.party == "Democratic"
        assert record.title == "U.S. Representative"
        assert record.photo_url == "https://example.com/williams.jpg"
        assert record.website == "https://nikemawilliams.house.gov"
        assert record.phone == "202-225-3801"
        assert record.office_address == "1406 Longworth HOB, Washington, DC 20515"
        assert record.term_start_date == date(2025, 1, 3)
        assert record.raw_data == {"summary": _SAMPLE_REP_SUMMARY, "detail": _SAMPLE_REP_DETAIL}

    def test_maps_senator(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        record = provider._map_member(_SAMPLE_SENATOR_SUMMARY, _SAMPLE_SENATOR_DETAIL)

        assert record.boundary_type == "us_senate"
        assert record.district_identifier == "GA"
        assert record.title == "U.S. Senator"
        assert record.full_name == "Raphael Warnock"
        assert record.term_start_date == date(2021, 1, 3)

    def test_maps_member_no_depiction(self) -> None:
        """Member without a photo."""
        provider = CongressGovProvider(api_key="test-key")
        summary = {**_SAMPLE_REP_SUMMARY}
        detail = {**_SAMPLE_REP_DETAIL, "depiction": None}
        record = provider._map_member(summary, detail)

        assert record.photo_url is None

    def test_maps_member_no_terms(self) -> None:
        """Member without term data."""
        provider = CongressGovProvider(api_key="test-key")
        summary = {**_SAMPLE_REP_SUMMARY}
        detail = {**_SAMPLE_REP_DETAIL, "terms": []}
        record = provider._map_member(summary, detail)

        assert record.term_start_date is None

    def test_maps_member_minimal_detail(self) -> None:
        """Member with empty detail response."""
        provider = CongressGovProvider(api_key="test-key")
        record = provider._map_member(_SAMPLE_REP_SUMMARY, {})

        assert record.full_name == "Nikema Williams"  # falls back to summary name
        assert record.first_name == "Nikema"  # falls back to summary
        assert record.photo_url is None
        assert record.website is None


class TestSenatorDetection:
    """Test that senators are correctly identified by null district."""

    def test_senator_has_null_district(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        record = provider._map_member(_SAMPLE_SENATOR_SUMMARY, _SAMPLE_SENATOR_DETAIL)
        assert record.boundary_type == "us_senate"
        assert record.district_identifier == "GA"

    def test_representative_has_numbered_district(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        record = provider._map_member(_SAMPLE_REP_SUMMARY, _SAMPLE_REP_DETAIL)
        assert record.boundary_type == "congressional"
        assert record.district_identifier == "5"


class TestFetchByDistrict:
    """Test fetch_by_district with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_fetch_house_district(self) -> None:
        provider = CongressGovProvider(api_key="test-key")

        list_response = httpx.Response(
            200,
            json={"members": [_SAMPLE_REP_SUMMARY]},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/congress/119/GA/5"),
        )
        detail_response = httpx.Response(
            200,
            json={"member": _SAMPLE_REP_DETAIL},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/W000788"),
        )

        mock_get = AsyncMock(side_effect=[list_response, detail_response])
        with patch.object(provider._client, "get", mock_get):
            records = await provider.fetch_by_district("congressional", "5")

        assert len(records) == 1
        assert records[0].full_name == "Nikema Williams"
        assert records[0].boundary_type == "congressional"

    @pytest.mark.asyncio
    async def test_fetch_senators(self) -> None:
        provider = CongressGovProvider(api_key="test-key")

        # List response includes both reps and senators
        list_response = httpx.Response(
            200,
            json={"members": [_SAMPLE_REP_SUMMARY, _SAMPLE_SENATOR_SUMMARY]},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/congress/119/GA"),
        )
        senator_detail = httpx.Response(
            200,
            json={"member": _SAMPLE_SENATOR_DETAIL},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/W000790"),
        )

        mock_get = AsyncMock(side_effect=[list_response, senator_detail])
        with patch.object(provider._client, "get", mock_get):
            records = await provider.fetch_by_district("us_senate", "GA")

        # Should only return the senator, not the rep
        assert len(records) == 1
        assert records[0].boundary_type == "us_senate"
        assert records[0].full_name == "Raphael Warnock"

    @pytest.mark.asyncio
    async def test_unsupported_boundary_type(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        with pytest.raises(OfficialsProviderError, match="Unsupported boundary type"):
            await provider.fetch_by_district("state_senate", "39")


class TestFetchAllGaMembers:
    """Test bulk GA member fetch."""

    @pytest.mark.asyncio
    async def test_fetches_all_members(self) -> None:
        provider = CongressGovProvider(api_key="test-key")

        list_response = httpx.Response(
            200,
            json={"members": [_SAMPLE_REP_SUMMARY, _SAMPLE_SENATOR_SUMMARY]},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/congress/119/GA"),
        )
        rep_detail = httpx.Response(
            200,
            json={"member": _SAMPLE_REP_DETAIL},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/W000788"),
        )
        senator_detail = httpx.Response(
            200,
            json={"member": _SAMPLE_SENATOR_DETAIL},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/W000790"),
        )

        mock_get = AsyncMock(side_effect=[list_response, rep_detail, senator_detail])
        with patch.object(provider._client, "get", mock_get):
            records = await provider.fetch_all_ga_members()

        assert len(records) == 2
        # Includes both rep and senator
        boundary_types = {r.boundary_type for r in records}
        assert boundary_types == {"congressional", "us_senate"}


class TestErrorHandling:
    """Test error handling for HTTP errors."""

    @pytest.mark.asyncio
    async def test_http_401(self) -> None:
        provider = CongressGovProvider(api_key="bad-key")
        mock_response = httpx.Response(
            401,
            json={"error": "Unauthorized"},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/congress/119/GA/5"),
        )

        with (
            patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(OfficialsProviderError) as exc_info,
        ):
            await provider.fetch_by_district("congressional", "5")

        assert exc_info.value.status_code == 401
        assert exc_info.value.provider_name == "congress_gov"

    @pytest.mark.asyncio
    async def test_http_429(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        mock_response = httpx.Response(
            429,
            json={"error": "Rate limited"},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/congress/119/GA/5"),
        )

        with (
            patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(OfficialsProviderError) as exc_info,
        ):
            await provider.fetch_by_district("congressional", "5")

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_http_500(self) -> None:
        provider = CongressGovProvider(api_key="test-key")
        mock_response = httpx.Response(
            500,
            text="Internal Server Error",
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/congress/119/GA/5"),
        )

        with (
            patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(OfficialsProviderError) as exc_info,
        ):
            await provider.fetch_by_district("congressional", "5")

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        provider = CongressGovProvider(api_key="test-key")

        with (
            patch.object(
                provider._client,
                "get",
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError("Connection refused"),
            ),
            pytest.raises(OfficialsProviderError, match="Request failed"),
        ):
            await provider.fetch_by_district("congressional", "5")

    @pytest.mark.asyncio
    async def test_detail_fetch_error(self) -> None:
        """Error on the detail fetch should propagate."""
        provider = CongressGovProvider(api_key="test-key")

        list_response = httpx.Response(
            200,
            json={"members": [_SAMPLE_REP_SUMMARY]},
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/congress/119/GA/5"),
        )
        detail_error = httpx.Response(
            500,
            text="Internal Server Error",
            request=httpx.Request("GET", "https://api.congress.gov/v3/member/W000788"),
        )

        mock_get = AsyncMock(side_effect=[list_response, detail_error])
        with patch.object(provider._client, "get", mock_get), pytest.raises(OfficialsProviderError) as exc_info:
            await provider.fetch_by_district("congressional", "5")

        assert exc_info.value.status_code == 500
