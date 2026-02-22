"""Unit tests for GeocodeQuality enum and select_best_result() ranking."""

import pytest

from voter_api.lib.geocoder.base import GeocodeQuality, GeocodeServiceType, GeocodingResult
from voter_api.services.geocoding_service import select_best_result


class TestGeocodeQuality:
    """Tests for GeocodeQuality enum values and ordering."""

    def test_quality_values(self) -> None:
        assert GeocodeQuality.EXACT == "exact"
        assert GeocodeQuality.INTERPOLATED == "interpolated"
        assert GeocodeQuality.APPROXIMATE == "approximate"
        assert GeocodeQuality.NO_MATCH == "no_match"
        assert GeocodeQuality.FAILED == "failed"

    def test_quality_from_string(self) -> None:
        assert GeocodeQuality("exact") == GeocodeQuality.EXACT
        assert GeocodeQuality("interpolated") == GeocodeQuality.INTERPOLATED

    def test_invalid_quality_raises(self) -> None:
        with pytest.raises(ValueError):
            GeocodeQuality("invalid")


class TestGeocodeServiceType:
    """Tests for GeocodeServiceType enum."""

    def test_service_type_values(self) -> None:
        assert GeocodeServiceType.INDIVIDUAL == "individual"
        assert GeocodeServiceType.BATCH == "batch"


class TestSelectBestResult:
    """Tests for select_best_result() ranking logic."""

    def _result(
        self,
        quality: GeocodeQuality,
        confidence: float = 0.5,
    ) -> GeocodingResult:
        return GeocodingResult(
            latitude=33.75,
            longitude=-84.39,
            confidence_score=confidence,
            quality=quality,
        )

    def test_empty_returns_none(self) -> None:
        assert select_best_result([]) is None

    def test_exact_beats_interpolated(self) -> None:
        results = [
            ("provider_a", self._result(GeocodeQuality.INTERPOLATED, 0.9)),
            ("provider_b", self._result(GeocodeQuality.EXACT, 0.8)),
        ]
        best = select_best_result(results)
        assert best is not None
        assert best[0] == "provider_b"

    def test_interpolated_beats_approximate(self) -> None:
        results = [
            ("provider_a", self._result(GeocodeQuality.APPROXIMATE, 0.9)),
            ("provider_b", self._result(GeocodeQuality.INTERPOLATED, 0.5)),
        ]
        best = select_best_result(results)
        assert best is not None
        assert best[0] == "provider_b"

    def test_confidence_tiebreaker_same_quality(self) -> None:
        results = [
            ("provider_a", self._result(GeocodeQuality.EXACT, 0.8)),
            ("provider_b", self._result(GeocodeQuality.EXACT, 0.95)),
        ]
        best = select_best_result(results)
        assert best is not None
        assert best[0] == "provider_b"

    def test_none_quality_treated_as_no_match(self) -> None:
        """Results with None quality are ranked below APPROXIMATE."""
        results = [
            ("provider_a", GeocodingResult(latitude=33.75, longitude=-84.39, quality=None)),
            ("provider_b", self._result(GeocodeQuality.APPROXIMATE, 0.5)),
        ]
        best = select_best_result(results)
        assert best is not None
        assert best[0] == "provider_b"

    def test_single_result(self) -> None:
        results = [("provider_a", self._result(GeocodeQuality.INTERPOLATED, 0.7))]
        best = select_best_result(results)
        assert best is not None
        assert best[0] == "provider_a"

    def test_none_confidence_treated_as_zero(self) -> None:
        results = [
            (
                "provider_a",
                GeocodingResult(latitude=33.75, longitude=-84.39, quality=GeocodeQuality.EXACT, confidence_score=None),
            ),
            ("provider_b", self._result(GeocodeQuality.EXACT, 0.5)),
        ]
        best = select_best_result(results)
        assert best is not None
        assert best[0] == "provider_b"
