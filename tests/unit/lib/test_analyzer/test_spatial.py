"""Tests for the analyzer spatial module (unit-level, no DB)."""

from voter_api.lib.analyzer import (
    BOUNDARY_TYPE_TO_VOTER_FIELD,
    ComparisonResult,
    compare_boundaries,
    extract_registered_boundaries,
    find_voter_boundaries,
    find_voter_boundaries_batch,
)


class TestAnalyzerPublicAPI:
    """Verify the analyzer library exports are available."""

    def test_exports_spatial_functions(self) -> None:
        assert callable(find_voter_boundaries)
        assert callable(find_voter_boundaries_batch)

    def test_exports_comparator_functions(self) -> None:
        assert callable(compare_boundaries)
        assert callable(extract_registered_boundaries)

    def test_exports_comparator_types(self) -> None:
        assert ComparisonResult is not None
        assert isinstance(BOUNDARY_TYPE_TO_VOTER_FIELD, dict)

    def test_comparison_result_dataclass(self) -> None:
        result = ComparisonResult(
            match_status="match",
            determined_boundaries={"congressional": "05"},
            registered_boundaries={"congressional": "05"},
        )
        assert result.match_status == "match"
        assert result.mismatch_details == []
