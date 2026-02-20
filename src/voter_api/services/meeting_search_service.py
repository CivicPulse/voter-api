"""Meeting search service — full-text search across agenda items and attachment filenames."""

from loguru import logger
from sqlalchemy import Float, String, cast, func, literal, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.agenda_item import AgendaItem
from voter_api.models.governing_body import GoverningBody
from voter_api.models.meeting import ApprovalStatus, Meeting
from voter_api.models.meeting_attachment import MeetingAttachment
from voter_api.models.user import User

MIN_QUERY_LENGTH = 2


async def search_meetings(
    session: AsyncSession,
    *,
    query: str,
    page: int = 1,
    page_size: int = 20,
    current_user: User | None = None,
) -> tuple[list[dict], int]:
    """Full-text search across agenda items and attachment filenames.

    Searches the tsvector column on agenda_items (title + description) and
    does ILIKE matching on attachment original_filename. Results include
    meeting context (date, type, governing body).

    Args:
        session: Database session.
        query: Search query string (minimum 2 characters).
        page: Page number (1-based).
        page_size: Items per page.
        current_user: Authenticated user (for approval visibility).

    Returns:
        Tuple of (results, total_count). Each result is a dict matching
        SearchResultItem fields.

    Raises:
        ValueError: If query is too short.
    """
    if len(query.strip()) < MIN_QUERY_LENGTH:
        raise ValueError(f"Search query must be at least {MIN_QUERY_LENGTH} characters")

    ts_query = func.plainto_tsquery("english", query)

    # Base visibility filter for meetings
    meeting_visible = Meeting.deleted_at.is_(None)
    if current_user and current_user.role != "admin":
        meeting_visible = meeting_visible & (
            (Meeting.approval_status == ApprovalStatus.APPROVED) | (Meeting.submitted_by == current_user.id)
        )

    # Subquery 1: FTS on agenda items
    agenda_query = (
        select(
            AgendaItem.id.label("agenda_item_id"),
            AgendaItem.title.label("title"),
            func.left(AgendaItem.description, 200).label("description_excerpt"),
            Meeting.id.label("meeting_id"),
            Meeting.meeting_date.label("meeting_date"),
            Meeting.meeting_type.label("meeting_type"),
            Meeting.governing_body_id.label("governing_body_id"),
            GoverningBody.name.label("governing_body_name"),
            literal("agenda_item").label("match_source"),
            cast(func.ts_rank(AgendaItem.search_vector, ts_query), Float).label("relevance_score"),
        )
        .join(Meeting, AgendaItem.meeting_id == Meeting.id)
        .join(GoverningBody, Meeting.governing_body_id == GoverningBody.id)
        .where(
            AgendaItem.deleted_at.is_(None),
            meeting_visible,
            AgendaItem.search_vector.op("@@")(ts_query),
        )
    )

    # Subquery 2: ILIKE on attachment filenames
    # Escape SQL wildcard characters so user input is treated as a literal string.
    escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like_pattern = f"%{escaped_query}%"
    attachment_query = (
        select(
            AgendaItem.id.label("agenda_item_id"),
            AgendaItem.title.label("title"),
            MeetingAttachment.original_filename.label("description_excerpt"),
            Meeting.id.label("meeting_id"),
            Meeting.meeting_date.label("meeting_date"),
            Meeting.meeting_type.label("meeting_type"),
            Meeting.governing_body_id.label("governing_body_id"),
            GoverningBody.name.label("governing_body_name"),
            literal("attachment_filename").label("match_source"),
            cast(literal(0.1), Float).label("relevance_score"),
        )
        .join(AgendaItem, MeetingAttachment.agenda_item_id == AgendaItem.id)
        .join(Meeting, AgendaItem.meeting_id == Meeting.id)
        .join(GoverningBody, Meeting.governing_body_id == GoverningBody.id)
        .where(
            MeetingAttachment.deleted_at.is_(None),
            AgendaItem.deleted_at.is_(None),
            meeting_visible,
            cast(MeetingAttachment.original_filename, String).ilike(like_pattern, escape="\\"),
        )
    )

    # Also search meeting-level attachments (no agenda item)
    meeting_attachment_query = (
        select(
            literal(None).cast(type_=AgendaItem.id.type).label("agenda_item_id"),
            MeetingAttachment.original_filename.label("title"),
            literal(None).cast(type_=String).label("description_excerpt"),
            Meeting.id.label("meeting_id"),
            Meeting.meeting_date.label("meeting_date"),
            Meeting.meeting_type.label("meeting_type"),
            Meeting.governing_body_id.label("governing_body_id"),
            GoverningBody.name.label("governing_body_name"),
            literal("attachment_filename").label("match_source"),
            cast(literal(0.05), Float).label("relevance_score"),
        )
        .join(Meeting, MeetingAttachment.meeting_id == Meeting.id)
        .join(GoverningBody, Meeting.governing_body_id == GoverningBody.id)
        .where(
            MeetingAttachment.deleted_at.is_(None),
            MeetingAttachment.agenda_item_id.is_(None),
            meeting_visible,
            cast(MeetingAttachment.original_filename, String).ilike(like_pattern, escape="\\"),
        )
    )

    combined = union_all(agenda_query, attachment_query, meeting_attachment_query).subquery()

    # Count total
    count_query = select(func.count()).select_from(combined)
    total = (await session.execute(count_query)).scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    results_query = select(combined).order_by(text("relevance_score DESC")).offset(offset).limit(page_size)
    result = await session.execute(results_query)
    rows = result.mappings().all()

    items = [dict(row) for row in rows]
    logger.info(f"Search '{query}' returned {total} results (page {page})")
    return items, total
