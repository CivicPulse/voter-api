"""Unit tests for the Open States provider."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from voter_api.lib.officials.base import OfficialsProviderError
from voter_api.lib.officials.open_states import OpenStatesProvider

# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

_SAMPLE_PERSON = {
    "id": "ocd-person/abc-123",
    "name": "Sally Harrell",
    "given_name": "Sally",
    "family_name": "Harrell",
    "party": "Democratic",
    "image": "https://example.com/photo.jpg",
    "email": "sally@senate.ga.gov",
    "openstates_url": "https://openstates.org/person/sally-harrell/",
    "links": [{"url": "https://harrell.senate.ga.gov"}],
    "current_role": {
        "title": "Senator",
        "org_classification": "upper",
        "district": "39",
        "division_id": "ocd-division/country:us/state:ga/sldu:39",
    },
    "offices": [
        {
            "name": "Capitol Office",
            "address": "121-C State Capitol, Atlanta, GA 30334",
            "voice": "404-463-1367",
            "classification": "capitol",
        }
    ],
}

_SAMPLE_HOUSE_PERSON = {
    "id": "ocd-person/def-456",
    "name": "Stacey Evans",
    "given_name": "Stacey",
    "family_name": "Evans",
    "party": "Democratic",
    "image": "https://example.com/evans.jpg",
    "email": "stacey@house.ga.gov",
    "openstates_url": None,
    "links": [{"url": "https://evans.house.ga.gov"}],
    "current_role": {
        "title": "Representative",
        "org_classification": "lower",
        "district": "57",
    },
    "offices": [],
}


def _paginated_response(results: list, page: int = 1, max_page: int = 1) -> dict:
    return {
        "results": results,
        "pagination": {
            "per_page": 10,
            "page": page,
            "max_page": max_page,
            "total_items": len(results),
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenStatesProviderName:
    def test_provider_name(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        assert provider.provider_name == "open_states"


class TestFieldMapping:
    """Test mapping of Open States person data to OfficialRecord."""

    @pytest.mark.asyncio
    async def test_maps_senate_person(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        record = provider._map_person(_SAMPLE_PERSON)

        assert record.source_name == "open_states"
        assert record.source_record_id == "ocd-person/abc-123"
        assert record.boundary_type == "state_senate"
        assert record.district_identifier == "39"
        assert record.full_name == "Sally Harrell"
        assert record.first_name == "Sally"
        assert record.last_name == "Harrell"
        assert record.party == "Democratic"
        assert record.title == "Senator"
        assert record.photo_url == "https://example.com/photo.jpg"
        assert record.email == "sally@senate.ga.gov"
        assert record.website == "https://openstates.org/person/sally-harrell/"
        assert record.phone == "404-463-1367"
        assert record.office_address == "121-C State Capitol, Atlanta, GA 30334"
        assert record.raw_data == _SAMPLE_PERSON

    @pytest.mark.asyncio
    async def test_maps_house_person(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        record = provider._map_person(_SAMPLE_HOUSE_PERSON)

        assert record.boundary_type == "state_house"
        assert record.district_identifier == "57"
        assert record.full_name == "Stacey Evans"
        # Falls back to first link when openstates_url is None
        assert record.website == "https://evans.house.ga.gov"
        # No offices
        assert record.phone is None
        assert record.office_address is None

    @pytest.mark.asyncio
    async def test_maps_person_no_links_no_offices(self) -> None:
        person = {
            "id": "ocd-person/xyz-789",
            "name": "Test Person",
            "current_role": {
                "org_classification": "upper",
                "district": "1",
            },
            "offices": [],
            "links": [],
        }
        provider = OpenStatesProvider(api_key="test-key")
        record = provider._map_person(person)

        assert record.website is None
        assert record.phone is None
        assert record.office_address is None


class TestBoundaryTypeMapping:
    """Test Open States org_classification to boundary type mapping."""

    @pytest.mark.asyncio
    async def test_upper_maps_to_state_senate(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        person = {**_SAMPLE_PERSON, "current_role": {**_SAMPLE_PERSON["current_role"], "org_classification": "upper"}}
        record = provider._map_person(person)
        assert record.boundary_type == "state_senate"

    @pytest.mark.asyncio
    async def test_lower_maps_to_state_house(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        person = {**_SAMPLE_PERSON, "current_role": {**_SAMPLE_PERSON["current_role"], "org_classification": "lower"}}
        record = provider._map_person(person)
        assert record.boundary_type == "state_house"

    @pytest.mark.asyncio
    async def test_unsupported_boundary_type_raises(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        with pytest.raises(OfficialsProviderError, match="Unsupported boundary type"):
            await provider.fetch_by_district("congressional", "5")


class TestFetchByDistrict:
    """Test fetch_by_district with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_single_page(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        mock_response = httpx.Response(
            200,
            json=_paginated_response([_SAMPLE_PERSON]),
            request=httpx.Request("GET", "https://v3.openstates.org/people"),
        )

        with patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response):
            records = await provider.fetch_by_district("state_senate", "39")

        assert len(records) == 1
        assert records[0].full_name == "Sally Harrell"

    @pytest.mark.asyncio
    async def test_multi_page(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        page1 = httpx.Response(
            200,
            json=_paginated_response([_SAMPLE_PERSON], page=1, max_page=2),
            request=httpx.Request("GET", "https://v3.openstates.org/people"),
        )
        page2 = httpx.Response(
            200,
            json=_paginated_response([_SAMPLE_HOUSE_PERSON], page=2, max_page=2),
            request=httpx.Request("GET", "https://v3.openstates.org/people"),
        )

        mock_get = AsyncMock(side_effect=[page1, page2])
        with patch.object(provider._client, "get", mock_get):
            records = await provider.fetch_by_district("state_senate", "39")

        assert len(records) == 2
        assert mock_get.call_count == 2


class TestFetchByPoint:
    """Test geo-lookup endpoint."""

    @pytest.mark.asyncio
    async def test_returns_records(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        mock_response = httpx.Response(
            200,
            json={"results": [_SAMPLE_PERSON, _SAMPLE_HOUSE_PERSON]},
            request=httpx.Request("GET", "https://v3.openstates.org/people.geo"),
        )

        with patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response):
            records = await provider.fetch_by_point(33.749, -84.388)

        assert len(records) == 2
        assert records[0].boundary_type == "state_senate"
        assert records[1].boundary_type == "state_house"


class TestErrorHandling:
    """Test error handling for HTTP errors."""

    @pytest.mark.asyncio
    async def test_http_401(self) -> None:
        provider = OpenStatesProvider(api_key="bad-key")
        mock_response = httpx.Response(
            401,
            json={"detail": "Invalid API key"},
            request=httpx.Request("GET", "https://v3.openstates.org/people"),
        )

        with (
            patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(OfficialsProviderError) as exc_info,
        ):
            await provider.fetch_by_district("state_senate", "39")

        assert exc_info.value.status_code == 401
        assert exc_info.value.provider_name == "open_states"

    @pytest.mark.asyncio
    async def test_http_429(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        mock_response = httpx.Response(
            429,
            json={"detail": "Rate limited"},
            request=httpx.Request("GET", "https://v3.openstates.org/people"),
        )

        with (
            patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(OfficialsProviderError) as exc_info,
        ):
            await provider.fetch_by_district("state_senate", "39")

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_http_500(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        mock_response = httpx.Response(
            500,
            text="Internal Server Error",
            request=httpx.Request("GET", "https://v3.openstates.org/people"),
        )

        with (
            patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(OfficialsProviderError) as exc_info,
        ):
            await provider.fetch_by_district("state_senate", "39")

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")

        with (
            patch.object(
                provider._client,
                "get",
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError("Connection refused"),
            ),
            pytest.raises(OfficialsProviderError, match="Request failed"),
        ):
            await provider.fetch_by_district("state_senate", "39")


class TestFetchAllForChamber:
    """Test bulk chamber fetch."""

    @pytest.mark.asyncio
    async def test_fetches_all_upper(self) -> None:
        provider = OpenStatesProvider(api_key="test-key")
        mock_response = httpx.Response(
            200,
            json=_paginated_response([_SAMPLE_PERSON]),
            request=httpx.Request("GET", "https://v3.openstates.org/people"),
        )

        with patch.object(provider._client, "get", new_callable=AsyncMock, return_value=mock_response):
            records = await provider.fetch_all_for_chamber("upper")

        assert len(records) == 1
        assert records[0].boundary_type == "state_senate"
