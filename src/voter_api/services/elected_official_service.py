"""Elected official service — CRUD, source management, and approval workflow."""

import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.officials.base import OfficialRecord
from voter_api.models.elected_official import ElectedOfficial, ElectedOfficialSource

# Fields that may be set via the update endpoint.  Anything outside this set
# is silently ignored, preventing mass-assignment of internal fields such as
# ``status``, ``approved_by_id``, or ``id``.
_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "full_name",
        "first_name",
        "last_name",
        "party",
        "title",
        "photo_url",
        "term_start_date",
        "term_end_date",
        "last_election_date",
        "next_election_date",
        "website",
        "email",
        "phone",
        "office_address",
        "external_ids",
    }
)

# ---------------------------------------------------------------------------
# Read operations (public)
# ---------------------------------------------------------------------------


async def list_officials(
    session: AsyncSession,
    *,
    boundary_type: str | None = None,
    district_identifier: str | None = None,
    party: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ElectedOfficial], int]:
    """List elected officials with optional filters.

    Args:
        session: Database session.
        boundary_type: Filter by boundary type.
        district_identifier: Filter by district identifier.
        party: Filter by party affiliation.
        status: Filter by approval status (auto/approved/manual).
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (officials, total count).
    """
    query = select(ElectedOfficial)
    count_query = select(func.count(ElectedOfficial.id))

    if boundary_type:
        query = query.where(ElectedOfficial.boundary_type == boundary_type)
        count_query = count_query.where(ElectedOfficial.boundary_type == boundary_type)
    if district_identifier:
        query = query.where(ElectedOfficial.district_identifier == district_identifier)
        count_query = count_query.where(ElectedOfficial.district_identifier == district_identifier)
    if party:
        query = query.where(ElectedOfficial.party == party)
        count_query = count_query.where(ElectedOfficial.party == party)
    if status:
        query = query.where(ElectedOfficial.status == status)
        count_query = count_query.where(ElectedOfficial.status == status)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = (
        query.order_by(ElectedOfficial.boundary_type, ElectedOfficial.district_identifier)
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(query)
    officials = list(result.scalars().all())

    return officials, total


async def get_official(session: AsyncSession, official_id: uuid.UUID) -> ElectedOfficial | None:
    """Get an elected official by ID (with sources eager-loaded)."""
    result = await session.execute(select(ElectedOfficial).where(ElectedOfficial.id == official_id))
    return result.scalar_one_or_none()


async def get_officials_for_district(
    session: AsyncSession,
    boundary_type: str,
    district_identifier: str,
) -> list[ElectedOfficial]:
    """Get all elected officials for a specific district.

    Args:
        session: Database session.
        boundary_type: Boundary type.
        district_identifier: District identifier.

    Returns:
        List of officials for the district.
    """
    result = await session.execute(
        select(ElectedOfficial).where(
            ElectedOfficial.boundary_type == boundary_type,
            ElectedOfficial.district_identifier == district_identifier,
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Write operations (admin)
# ---------------------------------------------------------------------------


async def create_official(
    session: AsyncSession,
    *,
    boundary_type: str,
    district_identifier: str,
    full_name: str,
    first_name: str | None = None,
    last_name: str | None = None,
    party: str | None = None,
    title: str | None = None,
    photo_url: str | None = None,
    term_start_date: object = None,
    term_end_date: object = None,
    last_election_date: object = None,
    next_election_date: object = None,
    website: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    office_address: str | None = None,
    external_ids: dict | None = None,
    status: str = "manual",
) -> ElectedOfficial:
    """Create a new elected official record.

    Args:
        session: Database session.
        **kwargs: Official fields.

    Returns:
        The created ElectedOfficial.
    """
    official = ElectedOfficial(
        boundary_type=boundary_type,
        district_identifier=district_identifier,
        full_name=full_name,
        first_name=first_name,
        last_name=last_name,
        party=party,
        title=title,
        photo_url=photo_url,
        term_start_date=term_start_date,
        term_end_date=term_end_date,
        last_election_date=last_election_date,
        next_election_date=next_election_date,
        website=website,
        email=email,
        phone=phone,
        office_address=office_address,
        external_ids=external_ids,
        status=status,
    )
    session.add(official)
    await session.commit()
    await session.refresh(official)
    logger.info(f"Created elected official {official.id} ({full_name}) for {boundary_type}/{district_identifier}")
    return official


async def update_official(
    session: AsyncSession,
    official: ElectedOfficial,
    updates: dict,
) -> ElectedOfficial:
    """Update an elected official with the given fields.

    Args:
        session: Database session.
        official: The official to update.
        updates: Dict of field_name -> new_value (only non-None values applied).

    Returns:
        The updated ElectedOfficial.
    """
    for field_name, value in updates.items():
        if value is not None and field_name in _UPDATABLE_FIELDS:
            setattr(official, field_name, value)
    await session.commit()
    await session.refresh(official)
    logger.info(f"Updated elected official {official.id}")
    return official


async def delete_official(session: AsyncSession, official: ElectedOfficial) -> None:
    """Delete an elected official and its source records (cascade).

    Args:
        session: Database session.
        official: The official to delete.
    """
    await session.delete(official)
    await session.commit()
    logger.info(f"Deleted elected official {official.id}")


async def approve_official(
    session: AsyncSession,
    official: ElectedOfficial,
    approved_by_id: uuid.UUID,
    source_id: uuid.UUID | None = None,
) -> ElectedOfficial:
    """Approve an elected official record, optionally promoting source data.

    If source_id is provided, copies the source's normalized fields into
    the canonical record before marking it approved.

    Args:
        session: Database session.
        official: The official to approve.
        approved_by_id: ID of the admin user approving.
        source_id: Optional source record to promote.

    Returns:
        The approved ElectedOfficial.
    """
    if source_id:
        source = await get_source(session, source_id)
        if source and source.elected_official_id == official.id:
            _promote_source_fields(official, source)

    official.status = "approved"
    official.approved_by_id = approved_by_id
    official.approved_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(official)
    logger.info(f"Approved elected official {official.id} by user {approved_by_id}")
    return official


# ---------------------------------------------------------------------------
# Source operations
# ---------------------------------------------------------------------------


async def get_source(session: AsyncSession, source_id: uuid.UUID) -> ElectedOfficialSource | None:
    """Get a source record by ID."""
    result = await session.execute(select(ElectedOfficialSource).where(ElectedOfficialSource.id == source_id))
    return result.scalar_one_or_none()


async def list_sources_for_district(
    session: AsyncSession,
    boundary_type: str,
    district_identifier: str,
    *,
    current_only: bool = True,
) -> list[ElectedOfficialSource]:
    """List source records for a district.

    Args:
        session: Database session.
        boundary_type: Boundary type.
        district_identifier: District identifier.
        current_only: If True, only return is_current=True sources.

    Returns:
        List of source records.
    """
    query = select(ElectedOfficialSource).where(
        ElectedOfficialSource.boundary_type == boundary_type,
        ElectedOfficialSource.district_identifier == district_identifier,
    )
    if current_only:
        query = query.where(ElectedOfficialSource.is_current.is_(True))
    query = query.order_by(ElectedOfficialSource.source_name, ElectedOfficialSource.fetched_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def upsert_source_records(
    session: AsyncSession,
    records: list[OfficialRecord],
) -> list[ElectedOfficialSource]:
    """Upsert source records from a provider fetch.

    For each record, marks any previous record from the same source+record_id
    as not current, then inserts or updates the new one.

    Args:
        session: Database session.
        records: Normalized records from a provider.

    Returns:
        List of upserted source records.
    """
    upserted: list[ElectedOfficialSource] = []

    for rec in records:
        # Find existing source by unique key
        result = await session.execute(
            select(ElectedOfficialSource).where(
                ElectedOfficialSource.source_name == rec.source_name,
                ElectedOfficialSource.source_record_id == rec.source_record_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.boundary_type = rec.boundary_type
            existing.district_identifier = rec.district_identifier
            existing.full_name = rec.full_name
            existing.first_name = rec.first_name
            existing.last_name = rec.last_name
            existing.party = rec.party
            existing.title = rec.title
            existing.photo_url = rec.photo_url
            existing.term_start_date = rec.term_start_date
            existing.term_end_date = rec.term_end_date
            existing.website = rec.website
            existing.email = rec.email
            existing.phone = rec.phone
            existing.office_address = rec.office_address
            existing.raw_data = rec.raw_data
            existing.fetched_at = datetime.now(UTC)
            existing.is_current = True
            upserted.append(existing)
        else:
            source = ElectedOfficialSource(
                source_name=rec.source_name,
                source_record_id=rec.source_record_id,
                boundary_type=rec.boundary_type,
                district_identifier=rec.district_identifier,
                full_name=rec.full_name,
                first_name=rec.first_name,
                last_name=rec.last_name,
                party=rec.party,
                title=rec.title,
                photo_url=rec.photo_url,
                term_start_date=rec.term_start_date,
                term_end_date=rec.term_end_date,
                website=rec.website,
                email=rec.email,
                phone=rec.phone,
                office_address=rec.office_address,
                raw_data=rec.raw_data,
                fetched_at=datetime.now(UTC),
                is_current=True,
            )
            session.add(source)
            upserted.append(source)

        # Try to auto-link to existing official
        if upserted[-1].elected_official_id is None:
            official = await _find_matching_official(session, rec)
            if official:
                upserted[-1].elected_official_id = official.id

    await session.commit()
    logger.info(f"Upserted {len(upserted)} source records")
    return upserted


async def auto_create_officials_from_sources(
    session: AsyncSession,
    boundary_type: str,
    district_identifier: str,
) -> list[ElectedOfficial]:
    """Auto-create elected official records from unlinked source records.

    For each current source record in the district that isn't linked to
    an official, creates a new official with status='auto' and links
    the source.

    Args:
        session: Database session.
        boundary_type: Boundary type.
        district_identifier: District identifier.

    Returns:
        List of newly created officials.
    """
    # Find unlinked current sources for this district
    result = await session.execute(
        select(ElectedOfficialSource).where(
            ElectedOfficialSource.boundary_type == boundary_type,
            ElectedOfficialSource.district_identifier == district_identifier,
            ElectedOfficialSource.is_current.is_(True),
            ElectedOfficialSource.elected_official_id.is_(None),
        )
    )
    unlinked = list(result.scalars().all())

    created: list[ElectedOfficial] = []
    for source in unlinked:
        # Check if an official already exists for this person in this district
        existing = await _find_matching_official(
            session,
            OfficialRecord(
                source_name=source.source_name,
                source_record_id=source.source_record_id,
                boundary_type=source.boundary_type,
                district_identifier=source.district_identifier,
                full_name=source.full_name,
            ),
        )
        if existing:
            source.elected_official_id = existing.id
            continue

        official = ElectedOfficial(
            boundary_type=source.boundary_type,
            district_identifier=source.district_identifier,
            full_name=source.full_name,
            first_name=source.first_name,
            last_name=source.last_name,
            party=source.party,
            title=source.title,
            photo_url=source.photo_url,
            term_start_date=source.term_start_date,
            term_end_date=source.term_end_date,
            website=source.website,
            email=source.email,
            phone=source.phone,
            office_address=source.office_address,
            status="auto",
        )
        session.add(official)
        await session.flush()  # get the ID

        source.elected_official_id = official.id
        created.append(official)

    await session.commit()
    if created:
        logger.info(f"Auto-created {len(created)} officials for {boundary_type}/{district_identifier}")
    return created


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _find_matching_official(
    session: AsyncSession,
    record: OfficialRecord,
) -> ElectedOfficial | None:
    """Find an existing official matching a source record by district + name."""
    result = await session.execute(
        select(ElectedOfficial).where(
            ElectedOfficial.boundary_type == record.boundary_type,
            ElectedOfficial.district_identifier == record.district_identifier,
            func.upper(ElectedOfficial.full_name) == func.upper(record.full_name),
        )
    )
    return result.scalar_one_or_none()


def _promote_source_fields(official: ElectedOfficial, source: ElectedOfficialSource) -> None:
    """Copy normalized fields from a source record into the canonical official."""
    official.full_name = source.full_name
    official.first_name = source.first_name
    official.last_name = source.last_name
    official.party = source.party
    official.title = source.title
    official.photo_url = source.photo_url
    official.term_start_date = source.term_start_date
    official.term_end_date = source.term_end_date
    official.website = source.website
    official.email = source.email
    official.phone = source.phone
    official.office_address = source.office_address
