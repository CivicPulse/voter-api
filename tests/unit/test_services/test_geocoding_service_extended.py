"""Extended tests for the geocoding service module — covering uncovered lines."""

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.lib.geocoder.base import GeocodingProviderError, GeocodingResult
from voter_api.services.geocoding_service import (
    _geocode_with_retry,
    _set_primary,
    add_manual_location,
    create_geocoding_job,
    geocode_voter_all_providers,
    get_cache_stats,
    get_geocoding_job,
    get_voter_locations,
    set_primary_location,
    verify_address,
)


def _mock_geocoding_result(**overrides: object) -> GeocodingResult:
    """Create a GeocodingResult with Georgia coordinates."""
    kwargs = {
        "latitude": 33.749,
        "longitude": -84.388,
        "confidence_score": 0.95,
        "raw_response": {"match": True},
        "matched_address": "123 MAIN ST, ATLANTA, GA 30301",
    }
    kwargs.update(overrides)
    return GeocodingResult(**kwargs)


class TestCreateGeocodingJob:
    """Tests for create_geocoding_job."""

    @pytest.mark.asyncio
    async def test_creates_job_with_defaults(self) -> None:
        session = AsyncMock()

        await create_geocoding_job(session)

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        added = session.add.call_args[0][0]
        assert added.provider == "census"
        assert added.status == "pending"
        assert added.county is None
        assert added.force_regeocode is False

    @pytest.mark.asyncio
    async def test_creates_job_with_options(self) -> None:
        session = AsyncMock()
        user_id = uuid.uuid4()

        await create_geocoding_job(
            session,
            provider="google",
            county="FULTON",
            force_regeocode=True,
            triggered_by=user_id,
        )

        added = session.add.call_args[0][0]
        assert added.provider == "google"
        assert added.county == "FULTON"
        assert added.force_regeocode is True
        assert added.triggered_by == user_id


class TestGetGeocodingJob:
    """Tests for get_geocoding_job."""

    @pytest.mark.asyncio
    async def test_returns_job_when_found(self) -> None:
        session = AsyncMock()
        mock_job = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_job
        session.execute.return_value = result

        found = await get_geocoding_job(session, uuid.uuid4())
        assert found is mock_job

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        found = await get_geocoding_job(session, uuid.uuid4())
        assert found is None


class TestGetVoterLocations:
    """Tests for get_voter_locations."""

    @pytest.mark.asyncio
    async def test_returns_locations(self) -> None:
        session = AsyncMock()
        locs = [MagicMock(), MagicMock()]
        result = MagicMock()
        result.scalars.return_value.all.return_value = locs
        session.execute.return_value = result

        found = await get_voter_locations(session, uuid.uuid4())
        assert len(found) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_locations(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute.return_value = result

        found = await get_voter_locations(session, uuid.uuid4())
        assert found == []


class TestGetCacheStats:
    """Tests for get_cache_stats."""

    @pytest.mark.asyncio
    async def test_returns_stats(self) -> None:
        session = AsyncMock()

        row = MagicMock()
        row.provider = "census"
        row.cached_count = 100
        row.oldest_entry = datetime(2024, 1, 1, tzinfo=UTC)
        row.newest_entry = datetime(2024, 6, 1, tzinfo=UTC)

        result = MagicMock()
        result.all.return_value = [row]
        session.execute.return_value = result

        stats = await get_cache_stats(session)
        assert len(stats) == 1
        assert stats[0].provider == "census"
        assert stats[0].cached_count == 100

    @pytest.mark.asyncio
    async def test_returns_empty_stats(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result

        stats = await get_cache_stats(session)
        assert stats == []


class TestGeocodeWithRetry:
    """Tests for _geocode_with_retry."""

    @pytest.mark.asyncio
    async def test_returns_result_on_first_try(self) -> None:
        geocoder = AsyncMock()
        geo_result = _mock_geocoding_result()
        geocoder.geocode.return_value = geo_result
        semaphore = asyncio.Semaphore(5)

        result = await _geocode_with_retry(geocoder, "123 Main St", semaphore)
        assert result is geo_result
        assert geocoder.geocode.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_none_for_no_match(self) -> None:
        geocoder = AsyncMock()
        geocoder.geocode.return_value = None
        semaphore = asyncio.Semaphore(5)

        result = await _geocode_with_retry(geocoder, "nonexistent address", semaphore)
        assert result is None
        assert geocoder.geocode.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_provider_error(self) -> None:
        geocoder = AsyncMock()
        geo_result = _mock_geocoding_result()
        geocoder.geocode.side_effect = [
            GeocodingProviderError("census", "timeout"),
            geo_result,
        ]
        semaphore = asyncio.Semaphore(5)

        with patch("voter_api.services.geocoding_service.asyncio.sleep", new_callable=AsyncMock):
            result = await _geocode_with_retry(geocoder, "123 Main St", semaphore)

        assert result is geo_result
        assert geocoder.geocode.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self) -> None:
        geocoder = AsyncMock()
        geocoder.geocode.side_effect = GeocodingProviderError("census", "timeout")
        semaphore = asyncio.Semaphore(5)

        with (
            patch("voter_api.services.geocoding_service.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(GeocodingProviderError),
        ):
            await _geocode_with_retry(geocoder, "123 Main St", semaphore)

        assert geocoder.geocode.call_count == 3  # MAX_RETRIES


class TestVerifyAddress:
    """Tests for verify_address."""

    @pytest.mark.asyncio
    async def test_verifies_well_formed_address(self) -> None:
        session = AsyncMock()

        from voter_api.schemas.geocoding import AddressSuggestion

        suggestion = AddressSuggestion(
            address="123 MAIN ST, ATLANTA, GA 30301",
            latitude=33.749,
            longitude=-84.388,
            confidence_score=0.95,
        )
        with patch(
            "voter_api.services.geocoding_service.prefix_search",
            new_callable=AsyncMock,
            return_value=[suggestion],
        ):
            result = await verify_address(session, "123 Main St, Atlanta, GA 30301")

        assert result.input_address == "123 Main St, Atlanta, GA 30301"
        assert result.normalized_address is not None

    @pytest.mark.asyncio
    async def test_short_input_skips_suggestions(self) -> None:
        session = AsyncMock()

        result = await verify_address(session, "123")

        assert result.suggestions == []


class TestSetPrimaryLocation:
    """Tests for set_primary_location."""

    @pytest.mark.asyncio
    async def test_sets_primary_when_found(self) -> None:
        session = AsyncMock()
        voter_id = uuid.uuid4()
        location_id = uuid.uuid4()
        location = MagicMock()
        location.is_primary = False

        result = MagicMock()
        result.scalar_one_or_none.return_value = location
        session.execute.return_value = result

        found = await set_primary_location(session, voter_id, location_id)
        assert found is not None
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = AsyncMock()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        found = await set_primary_location(session, uuid.uuid4(), uuid.uuid4())
        assert found is None


class TestAddManualLocation:
    """Tests for add_manual_location."""

    @pytest.mark.asyncio
    async def test_adds_manual_location(self) -> None:
        session = AsyncMock()
        voter_id = uuid.uuid4()

        # Mock count query — first location for voter
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        session.execute.return_value = count_result

        with patch("voter_api.services.geocoding_service.from_shape", return_value="mock_point"):
            await add_manual_location(
                session,
                voter_id=voter_id,
                latitude=33.749,
                longitude=-84.388,
            )

        session.add.assert_called_once()
        session.commit.assert_awaited()
        added = session.add.call_args[0][0]
        assert added.source_type == "manual"
        assert added.is_primary is True  # First location is primary

    @pytest.mark.asyncio
    async def test_set_as_primary_on_existing_voter(self) -> None:
        session = AsyncMock()
        voter_id = uuid.uuid4()

        # Existing voter has locations
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        session.execute.return_value = count_result

        with (
            patch("voter_api.services.geocoding_service.from_shape", return_value="mock_point"),
            patch("voter_api.services.geocoding_service._set_primary", new_callable=AsyncMock),
        ):
            await add_manual_location(
                session,
                voter_id=voter_id,
                latitude=33.749,
                longitude=-84.388,
                set_as_primary=True,
            )

        session.add.assert_called_once()


class TestSetPrimary:
    """Tests for _set_primary helper."""

    @pytest.mark.asyncio
    async def test_sets_primary_and_clears_others(self) -> None:
        session = AsyncMock()
        location = MagicMock()
        voter_id = uuid.uuid4()

        await _set_primary(session, voter_id, location)

        session.execute.assert_awaited_once()
        assert location.is_primary is True
        session.flush.assert_awaited_once()


class TestGeocodeVoterAllProviders:
    """Tests for geocode_voter_all_providers."""

    def _make_mock_voter(self) -> MagicMock:
        """Create a mock voter with address components."""
        voter = MagicMock()
        voter.id = uuid.uuid4()
        voter.residence_street_number = "123"
        voter.residence_pre_direction = None
        voter.residence_street_name = "MAIN"
        voter.residence_street_type = "ST"
        voter.residence_post_direction = None
        voter.residence_apt_unit_number = None
        voter.residence_city = "ATLANTA"
        voter.residence_zipcode = "30301"
        return voter

    @pytest.mark.asyncio
    async def test_voter_not_found_raises_value_error(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        with pytest.raises(ValueError, match="not found"):
            await geocode_voter_all_providers(session, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_no_address_raises_value_error(self) -> None:
        session = AsyncMock()
        voter = self._make_mock_voter()
        result = MagicMock()
        result.scalar_one_or_none.return_value = voter
        session.execute.return_value = result

        with (
            patch(
                "voter_api.services.geocoding_service.reconstruct_address",
                return_value="",
            ),
            pytest.raises(ValueError, match="no reconstructable"),
        ):
            await geocode_voter_all_providers(session, voter.id)

    @pytest.mark.asyncio
    async def test_success_with_cache_hit(self) -> None:
        session = AsyncMock()
        voter = self._make_mock_voter()

        # First call: select voter; subsequent calls: various service internals
        voter_result = MagicMock()
        voter_result.scalar_one_or_none.return_value = voter
        session.execute.return_value = voter_result

        geo_result = _mock_geocoding_result()
        mock_locations = [MagicMock()]
        mock_geocoder = MagicMock()
        mock_geocoder.provider_name = "census"

        with (
            patch(
                "voter_api.services.geocoding_service.reconstruct_address",
                return_value="123 MAIN ST, ATLANTA, GA 30301",
            ),
            patch(
                "voter_api.services.geocoding_service.get_available_providers",
                return_value=["census"],
            ),
            patch(
                "voter_api.services.geocoding_service.get_geocoder",
                return_value=mock_geocoder,
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=geo_result,
            ),
            patch(
                "voter_api.services.geocoding_service._store_geocoded_location",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "voter_api.services.geocoding_service.get_voter_locations",
                new_callable=AsyncMock,
                return_value=mock_locations,
            ),
        ):
            result = await geocode_voter_all_providers(session, voter.id)

        assert result["voter_id"] == voter.id
        assert result["address"] == "123 MAIN ST, ATLANTA, GA 30301"
        assert len(result["providers"]) == 1
        assert result["providers"][0]["status"] == "success"
        assert result["providers"][0]["cached"] is True
        assert result["locations"] == mock_locations
        mock_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_out_of_bounds_coordinates_recorded_as_error(self) -> None:
        session = AsyncMock()
        voter = self._make_mock_voter()

        voter_result = MagicMock()
        voter_result.scalar_one_or_none.return_value = voter
        session.execute.return_value = voter_result

        # Coordinates outside Georgia bounding box
        out_of_bounds_result = _mock_geocoding_result(latitude=40.0, longitude=-74.0)
        mock_geocoder = AsyncMock()
        mock_geocoder.provider_name = "census"
        mock_geocoder.geocode = AsyncMock(return_value=out_of_bounds_result)

        with (
            patch(
                "voter_api.services.geocoding_service.reconstruct_address",
                return_value="123 MAIN ST, ATLANTA, GA 30301",
            ),
            patch(
                "voter_api.services.geocoding_service.get_available_providers",
                return_value=["census"],
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.get_geocoder",
                return_value=mock_geocoder,
            ),
            patch(
                "voter_api.services.geocoding_service.get_voter_locations",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await geocode_voter_all_providers(session, voter.id)

        assert result["providers"][0]["status"] == "error"
        assert result["providers"][0].get("error") is not None

    @pytest.mark.asyncio
    async def test_success_with_provider_call(self) -> None:
        session = AsyncMock()
        voter = self._make_mock_voter()

        voter_result = MagicMock()
        voter_result.scalar_one_or_none.return_value = voter
        session.execute.return_value = voter_result

        geo_result = _mock_geocoding_result()
        mock_geocoder = AsyncMock()
        mock_geocoder.provider_name = "census"
        mock_geocoder.geocode = AsyncMock(return_value=geo_result)

        with (
            patch(
                "voter_api.services.geocoding_service.reconstruct_address",
                return_value="123 MAIN ST, ATLANTA, GA 30301",
            ),
            patch(
                "voter_api.services.geocoding_service.get_available_providers",
                return_value=["census"],
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.get_geocoder",
                return_value=mock_geocoder,
            ),
            patch(
                "voter_api.services.geocoding_service.cache_store",
                new_callable=AsyncMock,
            ) as mock_cache_store,
            patch(
                "voter_api.services.geocoding_service._store_geocoded_location",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "voter_api.services.geocoding_service.get_voter_locations",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await geocode_voter_all_providers(session, voter.id)

        assert result["providers"][0]["status"] == "success"
        assert result["providers"][0]["cached"] is False
        mock_cache_store.assert_awaited_once()
        mock_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_error_recorded(self) -> None:
        session = AsyncMock()
        voter = self._make_mock_voter()

        voter_result = MagicMock()
        voter_result.scalar_one_or_none.return_value = voter
        session.execute.return_value = voter_result

        mock_geocoder = AsyncMock()
        mock_geocoder.provider_name = "census"
        mock_geocoder.geocode = AsyncMock(side_effect=GeocodingProviderError("census", "timeout"))

        with (
            patch(
                "voter_api.services.geocoding_service.reconstruct_address",
                return_value="123 MAIN ST, ATLANTA, GA 30301",
            ),
            patch(
                "voter_api.services.geocoding_service.get_available_providers",
                return_value=["census"],
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.get_geocoder",
                return_value=mock_geocoder,
            ),
            patch(
                "voter_api.services.geocoding_service.get_voter_locations",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await geocode_voter_all_providers(session, voter.id)

        assert result["providers"][0]["status"] == "error"
        assert "timeout" in result["providers"][0]["error"]

    @pytest.mark.asyncio
    async def test_no_match_recorded(self) -> None:
        session = AsyncMock()
        voter = self._make_mock_voter()

        voter_result = MagicMock()
        voter_result.scalar_one_or_none.return_value = voter
        session.execute.return_value = voter_result

        mock_geocoder = AsyncMock()
        mock_geocoder.provider_name = "census"
        mock_geocoder.geocode = AsyncMock(return_value=None)

        with (
            patch(
                "voter_api.services.geocoding_service.reconstruct_address",
                return_value="123 MAIN ST, ATLANTA, GA 30301",
            ),
            patch(
                "voter_api.services.geocoding_service.get_available_providers",
                return_value=["census"],
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.get_geocoder",
                return_value=mock_geocoder,
            ),
            patch(
                "voter_api.services.geocoding_service.get_voter_locations",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await geocode_voter_all_providers(session, voter.id)

        assert result["providers"][0]["status"] == "no_match"
        assert result["providers"][0]["cached"] is False
