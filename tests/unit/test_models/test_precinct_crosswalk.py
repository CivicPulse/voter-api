"""Unit tests for the PrecinctCrosswalk model."""

from voter_api.models.precinct_crosswalk import PrecinctCrosswalk


class TestPrecinctCrosswalkModel:
    """Tests for PrecinctCrosswalk ORM model."""

    def test_tablename(self) -> None:
        """Table name should be 'precinct_crosswalk'."""
        assert PrecinctCrosswalk.__tablename__ == "precinct_crosswalk"

    def test_has_required_columns(self) -> None:
        """Model should expose all expected column attributes."""
        columns = {c.name for c in PrecinctCrosswalk.__table__.columns}
        expected = {
            "id",
            "county_code",
            "county_name",
            "voter_precinct_code",
            "boundary_precinct_identifier",
            "source",
            "confidence",
            "created_at",
        }
        assert expected <= columns

    def test_unique_constraint_exists(self) -> None:
        """Unique constraint on (county_name, voter_precinct_code) should exist."""
        constraint_names = {c.name for c in PrecinctCrosswalk.__table__.constraints if hasattr(c, "name") and c.name}
        assert "uq_precinct_crosswalk_county_precinct" in constraint_names

    def test_source_server_default(self) -> None:
        """Source column should default to 'spatial_join'."""
        col = PrecinctCrosswalk.__table__.c.source
        assert str(col.server_default.arg) == "spatial_join"

    def test_confidence_server_default(self) -> None:
        """Confidence column should default to 0.0."""
        col = PrecinctCrosswalk.__table__.c.confidence
        assert str(col.server_default.arg) == "0.0"
