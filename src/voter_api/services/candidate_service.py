"""Candidate service — business logic for candidate management.

Provides CRUD operations for candidates and their links,
including pagination, filtering, and SOS result cross-referencing.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voter_api.models.candidate import Candidate, CandidateLink
from voter_api.models.election import ElectionResult
from voter_api.schemas.candidacy import CandidacySummaryResponse
from voter_api.schemas.candidate import (
    CandidateCreateRequest,
    CandidateDetailResponse,
    CandidateLinkCreateRequest,
    CandidateLinkResponse,
    CandidateUpdateRequest,
    FilingStatus,
)

# Fields allowed for partial update via PATCH
_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "full_name",
        "party",
        "bio",
        "photo_url",
        "ballot_order",
        "filing_status",
        "is_incumbent",
        "sos_ballot_option_id",
    }
)


async def list_candidates(
    session: AsyncSession,
    election_id: uuid.UUID,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Candidate], int]:
    """List candidates for an election with optional status filter.

    Args:
        session: Async database session.
        election_id: The election UUID.
        status: Optional filing status filter.
        page: Page number (1-indexed).
        page_size: Results per page.

    Returns:
        Tuple of (candidate list, total count).
    """
    query = (
        select(Candidate)
        .options(selectinload(Candidate.links), selectinload(Candidate.candidacies))
        .where(Candidate.election_id == election_id)
    )
    count_query = select(func.count(Candidate.id)).where(Candidate.election_id == election_id)

    if status:
        query = query.where(Candidate.filing_status == status)
        count_query = count_query.where(Candidate.filing_status == status)

    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = (
        query.order_by(Candidate.ballot_order.asc().nulls_last(), Candidate.full_name).offset(offset).limit(page_size)
    )
    result = await session.execute(query)
    candidates = list(result.scalars().all())

    return candidates, total


async def get_candidate(
    session: AsyncSession,
    candidate_id: uuid.UUID,
) -> Candidate | None:
    """Get a single candidate by ID with links eagerly loaded.

    Args:
        session: Async database session.
        candidate_id: The candidate UUID.

    Returns:
        Candidate instance or None if not found.
    """
    result = await session.execute(
        select(Candidate)
        .options(selectinload(Candidate.links), selectinload(Candidate.candidacies))
        .where(Candidate.id == candidate_id)
    )
    return result.scalar_one_or_none()


async def create_candidate(
    session: AsyncSession,
    election_id: uuid.UUID,
    request: CandidateCreateRequest,
) -> Candidate:
    """Create a new candidate with optional initial links.

    Args:
        session: Async database session.
        election_id: The election UUID.
        request: Candidate creation request.

    Returns:
        The created Candidate instance.

    Raises:
        ValueError: If a candidate with the same name already exists for this election.
    """
    candidate = Candidate(
        election_id=election_id,
        full_name=request.full_name,
        party=request.party,
        bio=request.bio,
        photo_url=request.photo_url,
        ballot_order=request.ballot_order,
        filing_status=request.filing_status.value,
        is_incumbent=request.is_incumbent,
        sos_ballot_option_id=request.sos_ballot_option_id,
    )

    session.add(candidate)

    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        msg = f"A candidate named '{request.full_name}' already exists for this election."
        raise ValueError(msg) from e

    # Create initial links
    for link_data in request.links:
        link = CandidateLink(
            candidate_id=candidate.id,
            link_type=link_data.link_type.value,
            url=link_data.url,
            label=link_data.label,
        )
        session.add(link)

    await session.commit()

    # Re-fetch with links and candidacies eagerly loaded
    result = await session.execute(
        select(Candidate)
        .options(selectinload(Candidate.links), selectinload(Candidate.candidacies))
        .where(Candidate.id == candidate.id)
    )
    return result.scalar_one()


async def update_candidate(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    request: CandidateUpdateRequest,
) -> Candidate | None:
    """Update a candidate's fields (partial update).

    Args:
        session: Async database session.
        candidate_id: The candidate UUID.
        request: Partial update fields.

    Returns:
        Updated Candidate instance or None if not found.

    Raises:
        ValueError: If update causes a name conflict.
    """
    candidate = await get_candidate(session, candidate_id)
    if candidate is None:
        return None

    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in _UPDATABLE_FIELDS:
            if field == "filing_status" and value is not None:
                value = FilingStatus(value).value
            setattr(candidate, field, value)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        candidate_name = update_data.get("full_name")
        if candidate_name:
            msg = f"A candidate named '{candidate_name}' already exists for this election."
        else:
            msg = "A candidate with these details already exists for this election."
        raise ValueError(msg) from e

    await session.refresh(candidate)
    return candidate


async def delete_candidate(
    session: AsyncSession,
    candidate_id: uuid.UUID,
) -> bool:
    """Delete a candidate and all associated links.

    Args:
        session: Async database session.
        candidate_id: The candidate UUID.

    Returns:
        True if deleted, False if not found.
    """
    candidate = await get_candidate(session, candidate_id)
    if candidate is None:
        return False

    await session.delete(candidate)
    await session.commit()
    return True


async def add_candidate_link(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    request: CandidateLinkCreateRequest,
) -> CandidateLink | None:
    """Add a link to a candidate.

    Args:
        session: Async database session.
        candidate_id: The candidate UUID.
        request: Link creation request.

    Returns:
        The created CandidateLink or None if candidate not found.
    """
    candidate = await get_candidate(session, candidate_id)
    if candidate is None:
        return None

    link = CandidateLink(
        candidate_id=candidate_id,
        link_type=request.link_type.value,
        url=request.url,
        label=request.label,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def delete_candidate_link(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    link_id: uuid.UUID,
) -> bool:
    """Delete a specific link from a candidate.

    Args:
        session: Async database session.
        candidate_id: The candidate UUID.
        link_id: The link UUID.

    Returns:
        True if deleted, False if candidate or link not found.
    """
    result = await session.execute(
        select(CandidateLink).where(
            CandidateLink.id == link_id,
            CandidateLink.candidate_id == candidate_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        return False

    await session.delete(link)
    await session.commit()
    return True


def build_candidate_detail_response(
    candidate: Candidate,
    *,
    result_vote_count: int | None = None,
    result_political_party: str | None = None,
) -> CandidateDetailResponse:
    """Build a CandidateDetailResponse from a Candidate model instance.

    Args:
        candidate: The Candidate ORM instance.
        result_vote_count: Optional vote count from SOS results.
        result_political_party: Optional party from SOS results.

    Returns:
        CandidateDetailResponse schema instance.
    """
    # Build candidacy summaries from loaded relationship
    candidacies = []
    raw_candidacies = getattr(candidate, "candidacies", None)
    if raw_candidacies and isinstance(raw_candidacies, list):
        candidacies = [
            CandidacySummaryResponse(
                id=c.id,
                election_id=c.election_id,
                party=c.party,
                filing_status=c.filing_status,
                contest_name=c.contest_name,
            )
            for c in raw_candidacies
        ]

    # Extract external_ids safely (may be None, dict, or mock)
    raw_external_ids = getattr(candidate, "external_ids", None)
    external_ids = raw_external_ids if isinstance(raw_external_ids, dict) else None

    return CandidateDetailResponse(
        id=candidate.id,
        election_id=candidate.election_id,
        full_name=candidate.full_name,
        party=candidate.party,
        photo_url=candidate.photo_url,
        email=candidate.email,
        ballot_order=candidate.ballot_order,
        filing_status=candidate.filing_status,
        is_incumbent=candidate.is_incumbent,
        created_at=candidate.created_at,
        bio=candidate.bio,
        sos_ballot_option_id=candidate.sos_ballot_option_id,
        updated_at=candidate.updated_at,
        links=[
            CandidateLinkResponse(
                id=link.id,
                link_type=link.link_type,
                url=link.url,
                label=link.label,
            )
            for link in candidate.links
        ],
        candidacies=candidacies,
        external_ids=external_ids,
        result_vote_count=result_vote_count,
        result_political_party=result_political_party,
    )


async def get_candidate_with_results(
    session: AsyncSession,
    candidate_id: uuid.UUID,
) -> CandidateDetailResponse | None:
    """Get candidate detail enriched with SOS result data when available.

    If the candidate has a ``sos_ballot_option_id`` set and the election
    has results with a matching ballot option, the response includes
    ``result_vote_count`` and ``result_political_party``.

    Args:
        session: Async database session.
        candidate_id: The candidate UUID.

    Returns:
        CandidateDetailResponse or None if not found.
    """
    candidate = await get_candidate(session, candidate_id)
    if candidate is None:
        return None

    result_vote_count = None
    result_political_party = None

    if candidate.sos_ballot_option_id:
        # Look up the election's result data
        result = await session.execute(
            select(ElectionResult).where(ElectionResult.election_id == candidate.election_id)
        )
        election_result = result.scalar_one_or_none()
        if election_result and election_result.results_data:
            for option in election_result.results_data:
                if option.get("id") == candidate.sos_ballot_option_id:
                    result_vote_count = option.get("voteCount")
                    result_political_party = option.get("politicalParty")
                    break

    return build_candidate_detail_response(
        candidate,
        result_vote_count=result_vote_count,
        result_political_party=result_political_party,
    )
