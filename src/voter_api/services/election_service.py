"""Election service — business logic for election tracking.

Orchestrates election CRUD, result fetching, and data assembly.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voter_api.core.config import get_settings
from voter_api.lib.election_tracker import (
    FetchError,
    IngestionResult,
    fetch_election_results,
    ingest_election_results,
)
from voter_api.models.election import Election, ElectionCountyResult, ElectionResult
from voter_api.schemas.election import (
    CandidateResult,
    CountyResultSummary,
    ElectionCreateRequest,
    ElectionDetailResponse,
    ElectionResultFeature,
    ElectionResultFeatureCollection,
    ElectionResultsResponse,
    ElectionSummary,
    ElectionUpdateRequest,
    FeedImportedElection,
    FeedImportPreviewResponse,
    FeedImportRequest,
    FeedImportResponse,
    FeedRaceSummary,
    PrecinctCandidateResult,
    PrecinctElectionResultFeature,
    PrecinctElectionResultFeatureCollection,
    RawCountyResult,
    RawElectionResultsResponse,
    RefreshResponse,
    VoteMethodResult,
)


class DuplicateElectionError(ValueError):
    """Raised when attempting to create an election that already exists."""


def _ballot_option_to_candidate(opt: dict) -> CandidateResult:
    """Convert a JSONB ballot option dict to a CandidateResult schema."""
    return CandidateResult(
        id=opt.get("id", ""),
        name=opt.get("name", ""),
        political_party=opt.get("politicalParty", ""),
        ballot_order=opt.get("ballotOrder", 1),
        vote_count=opt.get("voteCount", 0),
        group_results=[
            VoteMethodResult(
                group_name=gr.get("groupName", ""),
                vote_count=gr.get("voteCount", 0),
            )
            for gr in opt.get("groupResults", [])
        ],
    )


async def create_election(
    session: AsyncSession,
    request: ElectionCreateRequest,
) -> Election:
    """Create a new election record.

    Args:
        session: Async database session.
        request: Election creation request.

    Returns:
        The created Election instance.

    Raises:
        DuplicateElectionError: If a duplicate election exists (by name+date or feed+ballot_item).
    """
    if request.ballot_item_id is not None:
        existing = await session.execute(
            select(Election).where(
                Election.data_source_url == str(request.data_source_url),
                Election.ballot_item_id == request.ballot_item_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            msg = (
                f"An election for ballot item '{request.ballot_item_id}' "
                f"from '{request.data_source_url}' already exists."
            )
            raise DuplicateElectionError(msg)
    else:
        existing = await session.execute(
            select(Election).where(
                Election.name == request.name,
                Election.election_date == request.election_date,
            )
        )
        if existing.scalar_one_or_none() is not None:
            msg = f"An election with name '{request.name}' and date '{request.election_date}' already exists."
            raise DuplicateElectionError(msg)

    election = Election(
        name=request.name,
        election_date=request.election_date,
        election_type=request.election_type,
        district=request.district,
        data_source_url=str(request.data_source_url),
        refresh_interval_seconds=request.refresh_interval_seconds,
        ballot_item_id=request.ballot_item_id,
    )
    session.add(election)
    await session.commit()
    await session.refresh(election)
    return election


async def get_election_by_id(
    session: AsyncSession,
    election_id: uuid.UUID,
) -> Election | None:
    """Get an election by ID with its result eagerly loaded.

    Args:
        session: Async database session.
        election_id: The election UUID.

    Returns:
        Election instance or None if not found.
    """
    result = await session.execute(
        select(Election).options(selectinload(Election.result)).where(Election.id == election_id)
    )
    return result.scalar_one_or_none()


async def update_election(
    session: AsyncSession,
    election_id: uuid.UUID,
    request: ElectionUpdateRequest,
) -> Election | None:
    """Update election metadata.

    Args:
        session: Async database session.
        election_id: The election UUID.
        request: Partial update fields.

    Returns:
        Updated Election instance or None if not found.
    """
    election = await get_election_by_id(session, election_id)
    if election is None:
        return None

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "data_source_url" and value is not None:
            value = str(value)
        setattr(election, field, value)

    await session.commit()
    await session.refresh(election)
    return election


def build_detail_response(election: Election) -> ElectionDetailResponse:
    """Build an ElectionDetailResponse from an Election model instance."""
    precincts_reporting = None
    precincts_participating = None
    if election.result:
        precincts_reporting = election.result.precincts_reporting
        precincts_participating = election.result.precincts_participating

    return ElectionDetailResponse(
        id=election.id,
        name=election.name,
        election_date=election.election_date,
        election_type=election.election_type,
        district=election.district,
        status=election.status,
        last_refreshed_at=election.last_refreshed_at,
        precincts_reporting=precincts_reporting,
        precincts_participating=precincts_participating,
        ballot_item_id=election.ballot_item_id,
        data_source_url=election.data_source_url,
        refresh_interval_seconds=election.refresh_interval_seconds,
        created_at=election.created_at,
        updated_at=election.updated_at,
    )


async def get_election_results(
    session: AsyncSession,
    election_id: uuid.UUID,
) -> ElectionResultsResponse | None:
    """Assemble full election results from statewide + county data.

    Args:
        session: Async database session.
        election_id: The election UUID.

    Returns:
        ElectionResultsResponse or None if election not found.
    """
    election = await get_election_by_id(session, election_id)
    if election is None:
        return None

    # Statewide candidates
    candidates: list[CandidateResult] = []
    precincts_participating = None
    precincts_reporting = None
    if election.result:
        precincts_participating = election.result.precincts_participating
        precincts_reporting = election.result.precincts_reporting
        for opt in election.result.results_data:
            candidates.append(_ballot_option_to_candidate(opt))

    # County results
    county_query = await session.execute(
        select(ElectionCountyResult).where(ElectionCountyResult.election_id == election_id)
    )
    county_rows = county_query.scalars().all()

    county_results: list[CountyResultSummary] = []
    for row in county_rows:
        county_candidates = [_ballot_option_to_candidate(opt) for opt in row.results_data]
        county_results.append(
            CountyResultSummary(
                county_name=row.county_name,
                precincts_participating=row.precincts_participating,
                precincts_reporting=row.precincts_reporting,
                candidates=county_candidates,
            )
        )

    return ElectionResultsResponse(
        election_id=election.id,
        election_name=election.name,
        election_date=election.election_date,
        status=election.status,
        last_refreshed_at=election.last_refreshed_at,
        precincts_participating=precincts_participating,
        precincts_reporting=precincts_reporting,
        candidates=candidates,
        county_results=county_results,
    )


async def get_raw_election_results(
    session: AsyncSession,
    election_id: uuid.UUID,
) -> RawElectionResultsResponse | None:
    """Assemble raw election results preserving original SOS field names.

    Returns the stored JSONB data verbatim without camelCase-to-snake_case
    transformation applied by get_election_results().

    Args:
        session: Async database session.
        election_id: The election UUID.

    Returns:
        RawElectionResultsResponse or None if election not found.
    """
    election = await get_election_by_id(session, election_id)
    if election is None:
        return None

    statewide_results: list[dict[str, Any]] = []
    precincts_participating = None
    precincts_reporting = None
    source_created_at = None
    if election.result:
        precincts_participating = election.result.precincts_participating
        precincts_reporting = election.result.precincts_reporting
        source_created_at = election.result.source_created_at
        statewide_results = election.result.results_data

    county_query = await session.execute(
        select(ElectionCountyResult).where(ElectionCountyResult.election_id == election_id)
    )
    county_rows = county_query.scalars().all()

    county_results: list[RawCountyResult] = []
    for row in county_rows:
        county_results.append(
            RawCountyResult(
                county_name=row.county_name,
                precincts_participating=row.precincts_participating,
                precincts_reporting=row.precincts_reporting,
                results=row.results_data,
            )
        )

    return RawElectionResultsResponse(
        election_id=election.id,
        election_name=election.name,
        election_date=election.election_date,
        status=election.status,
        last_refreshed_at=election.last_refreshed_at,
        source_created_at=source_created_at,
        precincts_participating=precincts_participating,
        precincts_reporting=precincts_reporting,
        statewide_results=statewide_results,
        county_results=county_results,
    )


async def _persist_ingestion_result(
    session: AsyncSession,
    election_id: uuid.UUID,
    ingestion: IngestionResult,
) -> int:
    """Persist ingestion results to database using upsert semantics.

    Args:
        session: Async database session.
        election_id: The UUID of the election to update.
        ingestion: Extracted result data from the ingester library.

    Returns:
        Number of county results upserted.
    """
    now = datetime.now(UTC)

    # --- Statewide result upsert ---
    existing_result = await session.execute(select(ElectionResult).where(ElectionResult.election_id == election_id))
    result_row = existing_result.scalar_one_or_none()

    if result_row is None:
        result_row = ElectionResult(
            election_id=election_id,
            precincts_participating=ingestion.statewide.precincts_participating,
            precincts_reporting=ingestion.statewide.precincts_reporting,
            results_data=ingestion.statewide.results_data,
            source_created_at=ingestion.statewide.source_created_at,
            fetched_at=now,
        )
        session.add(result_row)
    else:
        result_row.precincts_participating = ingestion.statewide.precincts_participating
        result_row.precincts_reporting = ingestion.statewide.precincts_reporting
        result_row.results_data = ingestion.statewide.results_data
        result_row.source_created_at = ingestion.statewide.source_created_at
        result_row.fetched_at = now

    # --- County results upsert ---
    counties_updated = 0
    for county in ingestion.counties:
        existing_county = await session.execute(
            select(ElectionCountyResult).where(
                ElectionCountyResult.election_id == election_id,
                ElectionCountyResult.county_name == county.county_name,
            )
        )
        county_row = existing_county.scalar_one_or_none()

        if county_row is None:
            county_row = ElectionCountyResult(
                election_id=election_id,
                county_name=county.county_name,
                county_name_normalized=county.county_name_normalized,
                precincts_participating=county.precincts_participating,
                precincts_reporting=county.precincts_reporting,
                results_data=county.results_data,
            )
            session.add(county_row)
        else:
            county_row.precincts_participating = county.precincts_participating
            county_row.precincts_reporting = county.precincts_reporting
            county_row.results_data = county.results_data

        counties_updated += 1

    await session.flush()
    return counties_updated


async def refresh_single_election(
    session: AsyncSession,
    election_id: uuid.UUID,
) -> RefreshResponse:
    """Fetch, parse, and ingest results for a single election.

    Args:
        session: Async database session.
        election_id: The election UUID.

    Returns:
        RefreshResponse with updated counts.

    Raises:
        ValueError: If election not found.
        FetchError: If data source fetch fails.
    """
    election = await get_election_by_id(session, election_id)
    if election is None:
        msg = "Election not found."
        raise ValueError(msg)

    settings = get_settings()
    feed = await fetch_election_results(
        election.data_source_url,
        allowed_domains=settings.election_allowed_domain_list,
    )
    ingestion = ingest_election_results(feed, ballot_item_id=election.ballot_item_id)
    counties_updated = await _persist_ingestion_result(session, election.id, ingestion)

    now = datetime.now(UTC)
    election.last_refreshed_at = now
    await session.commit()

    # Re-fetch to get updated result
    await session.refresh(election, ["result"])
    precincts_reporting = None
    precincts_participating = None
    if election.result:
        precincts_reporting = election.result.precincts_reporting
        precincts_participating = election.result.precincts_participating

    return RefreshResponse(
        election_id=election.id,
        refreshed_at=now,
        precincts_reporting=precincts_reporting,
        precincts_participating=precincts_participating,
        counties_updated=counties_updated,
    )


# --- US5: List & Filter ---


async def list_elections(
    session: AsyncSession,
    *,
    status: str | None = None,
    election_type: str | None = None,
    district: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ElectionSummary], int]:
    """List elections with optional filters and pagination.

    Args:
        session: Async database session.
        status: Filter by election status.
        election_type: Filter by election type.
        district: Filter by district (case-insensitive partial match).
        date_from: Filter elections on or after this date.
        date_to: Filter elections on or before this date.
        page: Page number (1-indexed).
        page_size: Results per page.

    Returns:
        Tuple of (election summaries, total count).
    """
    query = select(Election).options(selectinload(Election.result))
    count_query = select(func.count(Election.id))

    filters = []
    if status:
        filters.append(Election.status == status)
    if election_type:
        filters.append(Election.election_type == election_type)
    if district:
        filters.append(Election.district.ilike(f"%{district}%"))
    if date_from:
        filters.append(Election.election_date >= date_from)
    if date_to:
        filters.append(Election.election_date <= date_to)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(Election.election_date.desc()).offset(offset).limit(page_size)
    result = await session.execute(query)
    elections = result.scalars().all()

    items = []
    for election in elections:
        precincts_reporting = None
        precincts_participating = None
        if election.result:
            precincts_reporting = election.result.precincts_reporting
            precincts_participating = election.result.precincts_participating

        items.append(
            ElectionSummary(
                id=election.id,
                name=election.name,
                election_date=election.election_date,
                election_type=election.election_type,
                district=election.district,
                status=election.status,
                last_refreshed_at=election.last_refreshed_at,
                precincts_reporting=precincts_reporting,
                precincts_participating=precincts_participating,
                ballot_item_id=election.ballot_item_id,
            )
        )

    return items, total


# --- US2: GeoJSON ---


async def get_election_results_geojson(
    session: AsyncSession,
    election_id: uuid.UUID,
) -> ElectionResultFeatureCollection | None:
    """Build a GeoJSON FeatureCollection of county election results.

    Joins county results through county_metadata to boundaries for geometry.

    Args:
        session: Async database session.
        election_id: The election UUID.

    Returns:
        ElectionResultFeatureCollection or None if election not found.
    """
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping

    from voter_api.models.boundary import Boundary
    from voter_api.models.county_metadata import CountyMetadata

    election = await get_election_by_id(session, election_id)
    if election is None:
        return None

    # Query county results with geometry via two-hop join
    query = (
        select(
            ElectionCountyResult,
            Boundary.geometry,
        )
        .outerjoin(
            CountyMetadata,
            func.upper(ElectionCountyResult.county_name_normalized) == func.upper(CountyMetadata.name),
        )
        .outerjoin(
            Boundary,
            and_(
                Boundary.boundary_identifier == CountyMetadata.geoid,
                Boundary.boundary_type == "county",
            ),
        )
        .where(ElectionCountyResult.election_id == election_id)
    )
    result = await session.execute(query)
    rows = result.all()

    features: list[ElectionResultFeature] = []
    for county_result, geometry in rows:
        geom_dict: dict[str, Any] | None = None
        if geometry is not None:
            geom_shape = to_shape(geometry)
            geom_dict = mapping(geom_shape)

        candidates = [_ballot_option_to_candidate(opt) for opt in county_result.results_data]

        features.append(
            ElectionResultFeature(
                geometry=geom_dict,
                properties={
                    "county_name": county_result.county_name,
                    "precincts_reporting": county_result.precincts_reporting,
                    "precincts_participating": county_result.precincts_participating,
                    "candidates": [c.model_dump() for c in candidates],
                },
            )
        )

    return ElectionResultFeatureCollection(
        election_id=election.id,
        election_name=election.name,
        election_date=election.election_date,
        status=election.status,
        last_refreshed_at=election.last_refreshed_at,
        features=features,
    )


# --- US2b: Precinct-level GeoJSON ---


def _transpose_precinct_results(county_results_data: list[dict]) -> dict[str, dict]:
    """Transpose candidate-centric SoS data into precinct-centric structure.

    SoS data is shaped as candidate -> precincts[]. This function inverts it
    to precinct -> candidates[] for GeoJSON feature generation.

    Args:
        county_results_data: Raw JSONB ballot options from a county result row.

    Returns:
        Dict keyed by uppercased precinct_id, each value containing
        precinct_id, precinct_name, reporting_status, and candidates list.
    """
    precincts: dict[str, dict] = {}
    for opt in county_results_data:
        precinct_results = opt.get("precinctResults") or []
        for pr in precinct_results:
            pid = str(pr.get("id", "")).upper()
            if not pid:
                continue

            if pid not in precincts:
                precincts[pid] = {
                    "precinct_id": pid,
                    "precinct_name": pr.get("name", pid),
                    "reporting_status": pr.get("reportingStatus"),
                    "candidates": [],
                }

            group_results = [
                VoteMethodResult(
                    group_name=gr.get("groupName", ""),
                    vote_count=gr.get("voteCount", 0),
                )
                for gr in pr.get("groupResults", [])
            ]

            precincts[pid]["candidates"].append(
                PrecinctCandidateResult(
                    id=opt.get("id", ""),
                    name=opt.get("name", ""),
                    political_party=opt.get("politicalParty", ""),
                    ballot_order=opt.get("ballotOrder", 1),
                    vote_count=pr.get("voteCount", 0),
                    reporting_status=pr.get("reportingStatus"),
                    group_results=group_results,
                )
            )

    return precincts


async def get_election_precinct_results_geojson(
    session: AsyncSession,
    election_id: uuid.UUID,
    county: str | None = None,
) -> PrecinctElectionResultFeatureCollection | None:
    """Build a GeoJSON FeatureCollection of precinct-level election results.

    Extracts per-precinct data from the JSONB column, joins to precinct_metadata
    and boundaries for geometry.

    Args:
        session: Async database session.
        election_id: The election UUID.
        county: Optional county name filter (case-insensitive).

    Returns:
        PrecinctElectionResultFeatureCollection or None if election not found.
    """
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping

    from voter_api.models.boundary import Boundary
    from voter_api.services.precinct_metadata_service import (
        get_precinct_metadata_by_county_multi_strategy,
    )

    election = await get_election_by_id(session, election_id)
    if election is None:
        return None

    # Query county results, optionally filtered by county
    query = select(ElectionCountyResult).where(ElectionCountyResult.election_id == election_id)
    if county:
        query = query.where(func.upper(ElectionCountyResult.county_name_normalized) == county.upper())
    result = await session.execute(query)
    county_rows = result.scalars().all()

    features: list[PrecinctElectionResultFeature] = []

    for county_row in county_rows:
        # Transpose candidate-centric -> precinct-centric
        precinct_map = _transpose_precinct_results(county_row.results_data)
        if not precinct_map:
            continue

        # Batch lookup precinct metadata for geometry
        precinct_ids = list(precinct_map.keys())
        precinct_names = {pid: pdata["precinct_name"] for pid, pdata in precinct_map.items()}
        metadata_map = await get_precinct_metadata_by_county_multi_strategy(
            session, county_row.county_name_normalized, precinct_ids, precinct_names
        )

        # Batch fetch boundary geometries
        boundary_ids = [m.boundary_id for m in metadata_map.values()]
        geom_map: dict[uuid.UUID, Any] = {}
        if boundary_ids:
            geom_result = await session.execute(
                select(Boundary.id, Boundary.geometry).where(Boundary.id.in_(boundary_ids))
            )
            geom_map = {row.id: row.geometry for row in geom_result.all()}

        # Build features
        for pid, precinct_data in precinct_map.items():
            geom_dict: dict[str, Any] | None = None
            meta = metadata_map.get(pid)
            if meta is None:
                logger.warning(
                    "Precinct {} in county {} has no metadata match — skipping",
                    pid,
                    county_row.county_name,
                )
            elif meta.boundary_id in geom_map:
                geometry = geom_map[meta.boundary_id]
                if geometry is not None:
                    geom_dict = mapping(to_shape(geometry))

            if geom_dict is None:
                if meta is not None:
                    logger.warning(
                        "Precinct {} in county {} has no geometry — skipping",
                        pid,
                        county_row.county_name,
                    )
                continue

            candidates = precinct_data["candidates"]
            total_votes = sum(c.vote_count for c in candidates)

            features.append(
                PrecinctElectionResultFeature(
                    geometry=geom_dict,
                    properties={
                        "precinct_id": precinct_data["precinct_id"],
                        "precinct_name": precinct_data["precinct_name"],
                        "county_name": county_row.county_name,
                        "total_votes": total_votes,
                        "reporting_status": precinct_data["reporting_status"],
                        "candidates": [c.model_dump() for c in candidates],
                    },
                )
            )

    return PrecinctElectionResultFeatureCollection(
        election_id=election.id,
        election_name=election.name,
        election_date=election.election_date,
        status=election.status,
        last_refreshed_at=election.last_refreshed_at,
        features=features,
    )


# --- US3: Background Refresh ---


async def refresh_all_active_elections(session: AsyncSession) -> int:
    """Refresh results for all active elections.

    Args:
        session: Async database session.

    Returns:
        Number of elections successfully refreshed.
    """
    result = await session.execute(select(Election).where(Election.status == "active"))
    elections = result.scalars().all()

    refreshed = 0
    for election in elections:
        try:
            await refresh_single_election(session, election.id)
            refreshed += 1
        except Exception:
            logger.exception("Failed to refresh election {}", election.id)

    return refreshed


async def preview_feed_import(
    data_source_url: str,
) -> FeedImportPreviewResponse:
    """Fetch and analyze a feed to preview available races before import.

    Args:
        data_source_url: The SoS feed URL to preview.

    Returns:
        FeedImportPreviewResponse with race summaries.

    Raises:
        FetchError: If feed cannot be fetched or parsed.
        ValueError: If feed contains an invalid election date.
    """
    settings = get_settings()
    feed = await fetch_election_results(
        data_source_url,
        allowed_domains=settings.election_allowed_domain_list,
    )

    races = []
    for ballot_item in feed.results.ballotItems:
        races.append(
            FeedRaceSummary(
                ballot_item_id=ballot_item.id,
                name=ballot_item.name,
                candidate_count=len(ballot_item.ballotOptions),
                statewide_precincts_participating=ballot_item.precinctsParticipating,
                statewide_precincts_reporting=ballot_item.precinctsReporting,
            )
        )

    try:
        election_date = date.fromisoformat(feed.electionDate)
    except ValueError as e:
        msg = f"Feed contains invalid election date '{feed.electionDate}': {e}"
        raise ValueError(msg) from e

    return FeedImportPreviewResponse(
        data_source_url=data_source_url,
        election_date=election_date,
        election_name=feed.electionName,
        races=races,
    )


async def import_feed(
    session: AsyncSession,
    request: FeedImportRequest,
) -> FeedImportResponse:
    """Import all races from an SoS feed as separate elections.

    Creates one Election record per ballot item in the feed. Optionally
    performs an initial refresh for each election.

    Args:
        session: Async database session.
        request: Feed import configuration.

    Returns:
        FeedImportResponse with created election details.

    Raises:
        FetchError: If feed cannot be fetched or parsed.
        ValueError: If feed contains no races.
    """
    settings = get_settings()
    feed = await fetch_election_results(
        str(request.data_source_url),
        allowed_domains=settings.election_allowed_domain_list,
    )

    if not feed.results.ballotItems:
        msg = "Feed contains no ballot items (races)."
        raise ValueError(msg)

    election_date = date.fromisoformat(feed.electionDate)
    created_elections: list[FeedImportedElection] = []
    skipped = 0

    for ballot_item in feed.results.ballotItems:
        election_name = f"{feed.electionName} - {ballot_item.name}"
        district = ballot_item.name

        create_request = ElectionCreateRequest(
            name=election_name,
            election_date=election_date,
            election_type=request.election_type,
            district=district,
            data_source_url=request.data_source_url,
            refresh_interval_seconds=request.refresh_interval_seconds,
            ballot_item_id=ballot_item.id,
        )

        try:
            election = await create_election(session, create_request)
            logger.info(
                "Created election {} for ballot item {} ({})",
                election.id,
                ballot_item.id,
                ballot_item.name,
            )
        except DuplicateElectionError as e:
            logger.warning("Skipping ballot item {}: {}", ballot_item.id, e)
            skipped += 1
            continue

        refreshed = False
        precincts_reporting = None
        precincts_participating = None

        if request.auto_refresh:
            try:
                refresh_result = await refresh_single_election(session, election.id)
                refreshed = True
                precincts_reporting = refresh_result.precincts_reporting
                precincts_participating = refresh_result.precincts_participating
            except (FetchError, ValueError) as e:
                logger.warning(
                    "Initial refresh failed for election {} ({}): {}",
                    election.id,
                    ballot_item.id,
                    e,
                )

        created_elections.append(
            FeedImportedElection(
                election_id=election.id,
                ballot_item_id=ballot_item.id,
                name=election_name,
                election_date=election_date,
                refreshed=refreshed,
                precincts_reporting=precincts_reporting,
                precincts_participating=precincts_participating,
            )
        )

    return FeedImportResponse(
        elections_skipped=skipped,
        elections=created_elections,
    )


async def election_refresh_loop(
    interval: int,
) -> None:
    """Background asyncio loop that refreshes active elections.

    Args:
        interval: Seconds between refresh cycles.
    """
    from voter_api.core.database import get_session_factory

    logger.info("Election auto-refresh loop started (interval={}s)", interval)

    while True:
        try:
            await asyncio.sleep(interval)
            factory = get_session_factory()
            async with factory() as session:
                count = await refresh_all_active_elections(session)
                if count > 0:
                    logger.info("Refreshed {} active election(s)", count)
        except asyncio.CancelledError:
            logger.info("Election refresh loop cancelled")
            break
        except Exception:
            logger.exception("Election refresh loop error")
