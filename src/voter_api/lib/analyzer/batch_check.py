"""Batch boundary check library — cross-joins provider locations against registered district boundaries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from geoalchemy2.functions import ST_Contains
from sqlalchemy import select, tuple_

from voter_api.lib.analyzer.comparator import extract_registered_boundaries
from voter_api.models.boundary import Boundary
from voter_api.models.geocoded_location import GeocodedLocation
from voter_api.models.voter import Voter

if TYPE_CHECKING:
    import uuid

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

    # Query boundaries matching voter's registered districts
    boundary_pairs = list(registered.items())
    boundary_result = await session.execute(
        select(Boundary).where(tuple_(Boundary.boundary_type, Boundary.boundary_identifier).in_(boundary_pairs))
    )
    boundaries = boundary_result.scalars().all()
    boundary_ids = [b.id for b in boundaries]

    # Build a lookup: (boundary_type, boundary_identifier) -> Boundary
    boundary_lookup: dict[tuple[str, str], Boundary] = {(b.boundary_type, b.boundary_identifier): b for b in boundaries}

    # Query geocoded locations for this voter
    loc_result = await session.execute(select(GeocodedLocation).where(GeocodedLocation.voter_id == voter_id))
    locations = loc_result.scalars().all()

    # US2 edge case: no geocoded locations
    if not locations:
        # Populate districts with has_geometry status, empty providers
        districts = []
        for btype, bident in registered.items():
            b = boundary_lookup.get((btype, bident))
            districts.append(
                _DistrictBoundaryResult(
                    boundary_id=b.id if b else None,
                    boundary_type=btype,
                    boundary_identifier=bident,
                    has_geometry=b is not None,
                    providers=[],
                )
            )
        return BatchBoundaryCheckResult(
            voter_id=voter_id,
            districts=districts,
            provider_summary=[],
            total_locations=0,
            total_districts=len(registered),
        )

    # CROSS JOIN: geocoded_locations × boundaries with ST_Contains
    # Only execute if we have boundary_ids to avoid full-table scan
    cross_rows: list[Any] = []
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
                ST_Contains(Boundary.geometry, GeocodedLocation.point).label("is_contained"),
            )
            .where(GeocodedLocation.voter_id == voter_id)
            .where(Boundary.id.in_(boundary_ids))
            .order_by(GeocodedLocation.source_type, Boundary.boundary_type)
        )
        cross_result = await session.execute(cross_stmt)
        cross_rows = cross_result.all()

    # Aggregate cross-join rows into district results
    # Group by (boundary_id, boundary_type, boundary_identifier)
    district_providers: dict[tuple, list[_ProviderResult]] = defaultdict(list)
    for row in cross_rows:
        key = (row.boundary_id, row.boundary_type, row.boundary_identifier)
        district_providers[key].append(
            _ProviderResult(source_type=row.source_type, is_contained=bool(row.is_contained))
        )

    # Compute provider summaries from cross-join rows
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

    provider_summary = [
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

    # Build district results list
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
            # Registered district not in DB (no boundary geometry loaded)
            districts.append(
                _DistrictBoundaryResult(
                    boundary_id=None,
                    boundary_type=btype,
                    boundary_identifier=bident,
                    has_geometry=False,
                    providers=[],
                )
            )

    return BatchBoundaryCheckResult(
        voter_id=voter_id,
        districts=districts,
        provider_summary=provider_summary,
        total_locations=len(locations),
        total_districts=len(registered),
    )
