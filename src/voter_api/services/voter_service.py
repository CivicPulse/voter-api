"""Voter service — multi-parameter search and detail retrieval."""

import asyncio
import uuid

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from voter_api.models.voter import Voter


async def search_voters(
    session: AsyncSession,
    *,
    voter_registration_number: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    county: str | None = None,
    residence_city: str | None = None,
    residence_zipcode: str | None = None,
    status: str | None = None,
    congressional_district: str | None = None,
    state_senate_district: str | None = None,
    state_house_district: str | None = None,
    county_precinct: str | None = None,
    present_in_latest_import: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Voter], int]:
    """Search voters with multi-parameter filters using AND logic.

    Args:
        session: Database session.
        voter_registration_number: Exact match on registration number.
        first_name: Partial match (ILIKE) on first name.
        last_name: Partial match (ILIKE) on last name.
        county: Exact match on county.
        residence_city: Exact match on city.
        residence_zipcode: Exact match on zipcode.
        status: Exact match on status.
        congressional_district: Exact match.
        state_senate_district: Exact match.
        state_house_district: Exact match.
        county_precinct: Exact match.
        present_in_latest_import: Filter by import presence.
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (voters, total count).
    """
    query = select(Voter)
    count_query = select(func.count(Voter.id))

    # Exact match filters
    if voter_registration_number:
        query = query.where(Voter.voter_registration_number == voter_registration_number)
        count_query = count_query.where(Voter.voter_registration_number == voter_registration_number)

    # Partial match (ILIKE) for name fields
    if first_name:
        pattern = f"%{first_name}%"
        query = query.where(Voter.first_name.ilike(pattern))
        count_query = count_query.where(Voter.first_name.ilike(pattern))

    if last_name:
        pattern = f"%{last_name}%"
        query = query.where(Voter.last_name.ilike(pattern))
        count_query = count_query.where(Voter.last_name.ilike(pattern))

    # Exact match filters
    if county:
        query = query.where(Voter.county == county)
        count_query = count_query.where(Voter.county == county)

    if residence_city:
        query = query.where(Voter.residence_city == residence_city)
        count_query = count_query.where(Voter.residence_city == residence_city)

    if residence_zipcode:
        query = query.where(Voter.residence_zipcode == residence_zipcode)
        count_query = count_query.where(Voter.residence_zipcode == residence_zipcode)

    if status:
        query = query.where(Voter.status == status)
        count_query = count_query.where(Voter.status == status)

    if congressional_district:
        query = query.where(Voter.congressional_district == congressional_district)
        count_query = count_query.where(Voter.congressional_district == congressional_district)

    if state_senate_district:
        query = query.where(Voter.state_senate_district == state_senate_district)
        count_query = count_query.where(Voter.state_senate_district == state_senate_district)

    if state_house_district:
        query = query.where(Voter.state_house_district == state_house_district)
        count_query = count_query.where(Voter.state_house_district == state_house_district)

    if county_precinct:
        query = query.where(Voter.county_precinct == county_precinct)
        count_query = count_query.where(Voter.county_precinct == county_precinct)

    if present_in_latest_import is not None:
        query = query.where(Voter.present_in_latest_import == present_in_latest_import)
        count_query = count_query.where(Voter.present_in_latest_import == present_in_latest_import)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = (
        query.options(selectinload(Voter.geocoded_locations))
        .order_by(Voter.last_name, Voter.first_name)
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(query)
    voters = list(result.scalars().all())

    return voters, total


async def get_voter_detail(
    session: AsyncSession,
    voter_id: uuid.UUID,
) -> Voter | None:
    """Get a single voter by ID with eager-loaded relationships.

    Args:
        session: Database session.
        voter_id: The voter's UUID.

    Returns:
        Voter with geocoded_locations loaded, or None.
    """
    query = select(Voter).options(selectinload(Voter.geocoded_locations)).where(Voter.id == voter_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_voter_filter_options(session: AsyncSession) -> dict[str, list[str]]:
    """Return distinct non-null values for voter search filter dropdowns.

    Args:
        session: Database session.

    Returns:
        Dict mapping filter field names to sorted lists of distinct values.
    """

    async def _distinct_sorted(
        column: InstrumentedAttribute[str | None],
        *,
        filter_nulls: bool,
    ) -> list[str]:
        stmt = select(distinct(column))
        if filter_nulls:
            stmt = stmt.where(column.isnot(None))
        stmt = stmt.order_by(column)
        result = await session.execute(stmt)
        return [row for (row,) in result.all()]

    # status and county are non-nullable in the Voter model; district fields are nullable.
    (
        statuses,
        counties,
        congressional_districts,
        state_senate_districts,
        state_house_districts,
    ) = await asyncio.gather(
        _distinct_sorted(Voter.status, filter_nulls=False),
        _distinct_sorted(Voter.county, filter_nulls=False),
        _distinct_sorted(Voter.congressional_district, filter_nulls=True),
        _distinct_sorted(Voter.state_senate_district, filter_nulls=True),
        _distinct_sorted(Voter.state_house_district, filter_nulls=True),
    )

    return {
        "statuses": statuses,
        "counties": counties,
        "congressional_districts": congressional_districts,
        "state_senate_districts": state_senate_districts,
        "state_house_districts": state_house_districts,
    }


def build_voter_detail_dict(voter: Voter) -> dict:
    """Build the voter detail response dict with nested objects.

    Args:
        voter: The voter model instance.

    Returns:
        Dict suitable for VoterDetailResponse construction.
    """
    # Find primary geocoded location
    primary_location = next(
        (loc for loc in (voter.geocoded_locations or []) if loc.is_primary),
        None,
    )

    return {
        "id": voter.id,
        "county": voter.county,
        "voter_registration_number": voter.voter_registration_number,
        "status": voter.status,
        "status_reason": voter.status_reason,
        "last_name": voter.last_name,
        "first_name": voter.first_name,
        "middle_name": voter.middle_name,
        "suffix": voter.suffix,
        "birth_year": voter.birth_year,
        "race": voter.race,
        "gender": voter.gender,
        "residence_address": {
            "street_number": voter.residence_street_number,
            "pre_direction": voter.residence_pre_direction,
            "street_name": voter.residence_street_name,
            "street_type": voter.residence_street_type,
            "post_direction": voter.residence_post_direction,
            "apt_unit_number": voter.residence_apt_unit_number,
            "city": voter.residence_city,
            "zipcode": voter.residence_zipcode,
        },
        "mailing_address": {
            "street_number": voter.mailing_street_number,
            "street_name": voter.mailing_street_name,
            "apt_unit_number": voter.mailing_apt_unit_number,
            "city": voter.mailing_city,
            "zipcode": voter.mailing_zipcode,
            "state": voter.mailing_state,
            "country": voter.mailing_country,
        },
        "registered_districts": {
            "county_precinct": voter.county_precinct,
            "county_precinct_description": voter.county_precinct_description,
            "municipal_precinct": voter.municipal_precinct,
            "municipal_precinct_description": voter.municipal_precinct_description,
            "congressional_district": voter.congressional_district,
            "state_senate_district": voter.state_senate_district,
            "state_house_district": voter.state_house_district,
            "judicial_district": voter.judicial_district,
            "county_commission_district": voter.county_commission_district,
            "school_board_district": voter.school_board_district,
            "city_council_district": voter.city_council_district,
            "municipal_school_board_district": voter.municipal_school_board_district,
            "water_board_district": voter.water_board_district,
            "super_council_district": voter.super_council_district,
            "super_commissioner_district": voter.super_commissioner_district,
            "super_school_board_district": voter.super_school_board_district,
            "fire_district": voter.fire_district,
            "combo": voter.combo,
            "land_lot": voter.land_lot,
            "land_district": voter.land_district,
        },
        "registration_date": voter.registration_date,
        "last_modified_date": voter.last_modified_date,
        "date_of_last_contact": voter.date_of_last_contact,
        "last_vote_date": voter.last_vote_date,
        "voter_created_date": voter.voter_created_date,
        "last_party_voted": voter.last_party_voted,
        "municipality": voter.municipality,
        "present_in_latest_import": voter.present_in_latest_import,
        "soft_deleted_at": voter.soft_deleted_at,
        "created_at": voter.created_at,
        "updated_at": voter.updated_at,
        "primary_geocoded_location": (
            {
                "latitude": primary_location.latitude,
                "longitude": primary_location.longitude,
                "source_type": primary_location.source_type,
                "confidence_score": primary_location.confidence_score,
            }
            if primary_location
            else None
        ),
    }
