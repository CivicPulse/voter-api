"""Batch boundary check library — cross-joins provider locations against registered district boundaries."""

from __future__ import annotations

import contextlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, or_, select, tuple_

from voter_api.lib.analyzer.comparator import (
    NUMERIC_DISTRICT_TYPES,
    PRECINCT_TYPES,
    extract_registered_boundaries,
)
from voter_api.models.boundary import Boundary
from voter_api.models.geocoded_location import GeocodedLocation
from voter_api.models.voter import Voter

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.engine import Row
    from sqlalchemy.ext.asyncio import AsyncSession


class VoterNotFoundError(Exception):
    """Raised when no voter with the given ID exists."""


@dataclass
class _ProviderResult:
    source_type: str
    is_contained: bool


@dataclass
class _DistrictBoundaryResult:
    boundary_id: uuid.UUID | None
    boundary_type: str
    boundary_identifier: str
    has_geometry: bool
    providers: list[_ProviderResult] = field(default_factory=list)


@dataclass
class _ProviderSummary:
    source_type: str
    latitude: float
    longitude: float
    confidence_score: float | None
    districts_matched: int
    districts_checked: int


@dataclass
class BatchBoundaryCheckResult:
    """Internal result from check_batch_boundaries."""

    voter_id: uuid.UUID
    districts: list[_DistrictBoundaryResult]
    provider_summary: list[_ProviderSummary]
    total_locations: int
    total_districts: int
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _build_provider_summary(
    locations: Sequence[GeocodedLocation],
    cross_rows: list[Row[Any]],
) -> list[_ProviderSummary]:
    """Build per-provider summary from geocoded locations and cross-join rows."""
    provider_counts: dict[str, dict[str, Any]] = {}
    for loc in locations:
        provider_counts[loc.source_type] = {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "confidence_score": loc.confidence_score,
            "matched": 0,
            "checked": 0,
        }
    for row in cross_rows:
        pc = provider_counts[row.source_type]
        pc["checked"] += 1
        if row.is_contained:
            pc["matched"] += 1
    return [
        _ProviderSummary(
            source_type=stype,
            latitude=pc["latitude"],
            longitude=pc["longitude"],
            confidence_score=pc["confidence_score"],
            districts_matched=pc["matched"],
            districts_checked=pc["checked"],
        )
        for stype, pc in provider_counts.items()
    ]


def _build_district_results(
    registered: dict[str, str],
    boundary_lookup: dict[tuple[str, str], Boundary],
    district_providers: dict[tuple[uuid.UUID, str, str], list[_ProviderResult]],
) -> list[_DistrictBoundaryResult]:
    """Build district boundary results from registered assignments."""
    districts: list[_DistrictBoundaryResult] = []
    for btype, bident in registered.items():
        b = boundary_lookup.get((btype, bident))
        if b is not None:
            key = (b.id, b.boundary_type, b.boundary_identifier)
            providers = district_providers.get(key, [])
            districts.append(
                _DistrictBoundaryResult(
                    boundary_id=b.id,
                    boundary_type=btype,
                    boundary_identifier=bident,
                    has_geometry=True,
                    providers=providers,
                )
            )
        else:
            districts.append(
                _DistrictBoundaryResult(
                    boundary_id=None,
                    boundary_type=btype,
                    boundary_identifier=bident,
                    has_geometry=False,
                    providers=[],
                )
            )
    return districts


def _voter_ident(boundary_type: str, db_identifier: str, registered: dict[str, str]) -> str:
    """Map a DB boundary identifier back to the voter's raw registered format."""
    if boundary_type in NUMERIC_DISTRICT_TYPES:
        with contextlib.suppress(ValueError):
            return str(int(db_identifier))  # '008' → '8'
    if boundary_type in PRECINCT_TYPES:
        voter_val = registered.get(boundary_type, "")
        if voter_val and db_identifier.endswith(voter_val):
            return voter_val  # '021HO7' → 'HO7'
    return db_identifier


async def check_batch_boundaries(
    session: AsyncSession,
    voter_id: uuid.UUID,
) -> BatchBoundaryCheckResult:
    """Cross-join all geocoded locations for a voter against their registered district boundaries.

    Args:
        session: Async database session.
        voter_id: UUID of the voter to check.

    Returns:
        BatchBoundaryCheckResult dataclass with districts list and provider_summary.

    Raises:
        VoterNotFoundError: If no voter with the given ID exists.
    """
    # Load voter
    result = await session.execute(select(Voter).where(Voter.id == voter_id))
    voter = result.scalar_one_or_none()
    if voter is None:
        raise VoterNotFoundError(f"Voter {voter_id} not found")

    # Get registered district assignments: {boundary_type: boundary_identifier}
    registered: dict[str, str] = extract_registered_boundaries(voter)

    # US3 edge case: no district assignments
    if not registered:
        # Still need geocoded locations for provider_summary
        loc_result = await session.execute(select(GeocodedLocation).where(GeocodedLocation.voter_id == voter_id))
        locations = loc_result.scalars().all()
        provider_summary = [
            _ProviderSummary(
                source_type=loc.source_type,
                latitude=loc.latitude,
                longitude=loc.longitude,
                confidence_score=loc.confidence_score,
                districts_matched=0,
                districts_checked=0,
            )
            for loc in locations
        ]
        return BatchBoundaryCheckResult(
            voter_id=voter_id,
            districts=[],
            provider_summary=provider_summary,
            total_locations=len(locations),
            total_districts=0,
        )

    # Normalize voter identifiers to match boundary DB storage format:
    #   Numeric types: voter stores '8', DB stores '008' → zero-pad to 3 digits
    #   Precinct types: voter stores 'HO7', DB stores '021HO7' → suffix-match
    numeric_pairs: list[tuple[str, str]] = []
    precinct_pairs: list[tuple[str, str]] = []

    for btype, bident in registered.items():
        if btype in NUMERIC_DISTRICT_TYPES:
            try:
                numeric_pairs.append((btype, str(int(bident)).zfill(3)))
            except ValueError:
                numeric_pairs.append((btype, bident))
        elif btype in PRECINCT_TYPES:
            precinct_pairs.append((btype, bident))
        else:
            numeric_pairs.append((btype, bident))

    conditions = []
    if numeric_pairs:
        conditions.append(tuple_(Boundary.boundary_type, Boundary.boundary_identifier).in_(numeric_pairs))
    for btype, bident in precinct_pairs:
        conditions.append(and_(Boundary.boundary_type == btype, Boundary.boundary_identifier.like(f"%{bident}")))

    boundaries: list[Boundary] = []
    if conditions:
        boundary_result = await session.execute(select(Boundary).where(or_(*conditions)))
        boundaries = list(boundary_result.scalars().all())

    # Build a lookup: (boundary_type, voter_identifier) -> Boundary
    # The DB unique constraint is on (type, identifier, county), so multiple rows can share
    # the same (type, identifier) across counties. Disambiguate by voter county; if still
    # ambiguous, omit the key so downstream treats it as has_geometry=False.
    # Use the voter's raw identifier as the key so boundary_lookup matches registered.items().
    grouped_boundaries: dict[tuple[str, str], list[Boundary]] = defaultdict(list)
    for boundary in boundaries:
        vident = _voter_ident(boundary.boundary_type, boundary.boundary_identifier, registered)
        grouped_boundaries[(boundary.boundary_type, vident)].append(boundary)

    boundary_lookup: dict[tuple[str, str], Boundary] = {}
    for bkey, bgroup in grouped_boundaries.items():
        if len(bgroup) == 1:
            boundary_lookup[bkey] = bgroup[0]
        else:
            # Multiple candidates: prefer the one matching voter's county
            county_matches = [b for b in bgroup if b.county == voter.county]
            if len(county_matches) == 1:
                boundary_lookup[bkey] = county_matches[0]
            # else: ambiguous — omit so callers treat it as has_geometry=False

    boundary_ids = [b.id for b in boundary_lookup.values()]

    # Query geocoded locations for this voter, ordered for deterministic provider_summary
    loc_result = await session.execute(
        select(GeocodedLocation).where(GeocodedLocation.voter_id == voter_id).order_by(GeocodedLocation.source_type)
    )
    locations = loc_result.scalars().all()

    # US2 edge case: no geocoded locations
    if not locations:
        # Populate districts with has_geometry status, empty providers
        districts_no_locs: list[_DistrictBoundaryResult] = []
        for btype, bident in registered.items():
            boundary_match = boundary_lookup.get((btype, bident))
            districts_no_locs.append(
                _DistrictBoundaryResult(
                    boundary_id=boundary_match.id if boundary_match else None,
                    boundary_type=btype,
                    boundary_identifier=bident,
                    has_geometry=boundary_match is not None,
                    providers=[],
                )
            )
        return BatchBoundaryCheckResult(
            voter_id=voter_id,
            districts=districts_no_locs,
            provider_summary=[],
            total_locations=0,
            total_districts=len(registered),
        )

    # CROSS JOIN: geocoded_locations × boundaries with ST_Contains
    # Only execute if we have boundary_ids to avoid full-table scan
    cross_rows: list[Row[Any]] = []
    if boundary_ids:
        cross_stmt = (
            select(
                GeocodedLocation.source_type,
                GeocodedLocation.latitude,
                GeocodedLocation.longitude,
                GeocodedLocation.confidence_score,
                Boundary.id.label("boundary_id"),
                Boundary.boundary_type,
                Boundary.boundary_identifier,
                func.ST_Contains(Boundary.geometry, GeocodedLocation.point).label("is_contained"),
            )
            .where(GeocodedLocation.voter_id == voter_id)
            .where(Boundary.id.in_(boundary_ids))
            .order_by(GeocodedLocation.source_type, Boundary.boundary_type)
        )
        cross_result = await session.execute(cross_stmt)
        cross_rows = list(cross_result.all())

    # Aggregate cross-join rows into district results
    # Group by (boundary_id, boundary_type, boundary_identifier)
    district_providers: dict[tuple[uuid.UUID, str, str], list[_ProviderResult]] = defaultdict(list)
    for row in cross_rows:
        district_key = (row.boundary_id, row.boundary_type, row.boundary_identifier)
        district_providers[district_key].append(
            _ProviderResult(source_type=row.source_type, is_contained=bool(row.is_contained))
        )

    provider_summary = _build_provider_summary(locations, cross_rows)
    districts = _build_district_results(registered, boundary_lookup, district_providers)

    return BatchBoundaryCheckResult(
        voter_id=voter_id,
        districts=districts,
        provider_summary=provider_summary,
        total_locations=len(locations),
        total_districts=len(registered),
    )
