"""Export service — orchestrates bulk data export operations."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.exporter import export_voters
from voter_api.models.analysis_result import AnalysisResult
from voter_api.models.export_job import ExportJob
from voter_api.models.voter import Voter


async def create_export_job(
    session: AsyncSession,
    *,
    output_format: str,
    filters: dict,
    triggered_by: uuid.UUID | None = None,
) -> ExportJob:
    """Create a new export job record.

    Args:
        session: Database session.
        output_format: Output format (csv, json, geojson).
        filters: Filter criteria dict.
        triggered_by: User ID who triggered the export.

    Returns:
        The created ExportJob.
    """
    job = ExportJob(
        output_format=output_format,
        filters=filters,
        triggered_by=triggered_by,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    logger.info(f"Created export job {job.id} (format={output_format})")
    return job


async def process_export(
    session: AsyncSession,
    job: ExportJob,
    export_dir: Path,
) -> ExportJob:
    """Process an export job.

    Applies filters, fetches voter records, writes to file using the
    appropriate format writer.

    Args:
        session: Database session.
        job: The ExportJob to process.
        export_dir: Directory to write export files to.

    Returns:
        The updated ExportJob with file info.
    """
    job.status = "running"
    await session.commit()

    try:
        export_dir.mkdir(parents=True, exist_ok=True)

        # Build voter query from filters
        filters = job.filters or {}
        records = await _fetch_export_records(session, filters)

        # Generate output file path
        ext_map = {"csv": "csv", "json": "json", "geojson": "geojson"}
        ext = ext_map.get(job.output_format, "dat")
        output_path = export_dir / f"export_{job.id}.{ext}"

        # Export using the library
        result = export_voters(records, job.output_format, output_path)

        # Update job
        job.status = "completed"
        job.completed_at = datetime.now(UTC)
        job.record_count = result.record_count
        job.file_path = str(result.output_path)
        job.file_size_bytes = result.file_size_bytes
        await session.commit()
        await session.refresh(job)

        logger.info(f"Export job {job.id} completed: {result.record_count} records, {result.file_size_bytes} bytes")

    except Exception:
        job.status = "failed"
        await session.commit()
        logger.exception(f"Export job {job.id} failed")
        raise

    return job


EXPORT_STREAM_BATCH_SIZE = 1000


def _build_export_query(filters: dict) -> select:
    """Build the SQLAlchemy query for export with applied filters.

    Args:
        filters: Filter criteria.

    Returns:
        Configured select query.
    """
    query = select(Voter)

    # Apply standard voter filters
    if filters.get("county"):
        query = query.where(Voter.county == filters["county"])
    if filters.get("status"):
        query = query.where(Voter.status == filters["status"])
    if filters.get("first_name"):
        query = query.where(Voter.first_name.ilike(f"%{filters['first_name']}%"))
    if filters.get("last_name"):
        query = query.where(Voter.last_name.ilike(f"%{filters['last_name']}%"))
    if filters.get("residence_city"):
        query = query.where(Voter.residence_city == filters["residence_city"])
    if filters.get("residence_zipcode"):
        query = query.where(Voter.residence_zipcode == filters["residence_zipcode"])
    if filters.get("congressional_district"):
        query = query.where(Voter.congressional_district == filters["congressional_district"])
    if filters.get("state_senate_district"):
        query = query.where(Voter.state_senate_district == filters["state_senate_district"])
    if filters.get("state_house_district"):
        query = query.where(Voter.state_house_district == filters["state_house_district"])
    if filters.get("county_precinct"):
        query = query.where(Voter.county_precinct == filters["county_precinct"])
    if "present_in_latest_import" in filters and filters["present_in_latest_import"] is not None:
        query = query.where(Voter.present_in_latest_import == filters["present_in_latest_import"])

    # Analysis-specific filters (join to analysis_results)
    if filters.get("analysis_run_id") or filters.get("match_status"):
        query = query.join(AnalysisResult, AnalysisResult.voter_id == Voter.id)
        if filters.get("analysis_run_id"):
            run_id = uuid.UUID(str(filters["analysis_run_id"]))
            query = query.where(AnalysisResult.analysis_run_id == run_id)
        if filters.get("match_status"):
            query = query.where(AnalysisResult.match_status == filters["match_status"])

    return query.order_by(Voter.last_name, Voter.first_name)


def _voter_to_dict(voter: Voter) -> dict:
    """Convert a Voter ORM object to an export dict."""
    record = {
        "voter_registration_number": voter.voter_registration_number,
        "county": voter.county,
        "status": voter.status,
        "last_name": voter.last_name,
        "first_name": voter.first_name,
        "middle_name": voter.middle_name,
        "residence_street_number": voter.residence_street_number,
        "residence_street_name": voter.residence_street_name,
        "residence_street_type": voter.residence_street_type,
        "residence_city": voter.residence_city,
        "residence_zipcode": voter.residence_zipcode,
        "congressional_district": voter.congressional_district,
        "state_senate_district": voter.state_senate_district,
        "state_house_district": voter.state_house_district,
        "county_precinct": voter.county_precinct,
    }

    # Add geocoded location for GeoJSON
    primary_loc = next(
        (loc for loc in (voter.geocoded_locations or []) if loc.is_primary),
        None,
    )
    if primary_loc:
        record["latitude"] = primary_loc.latitude
        record["longitude"] = primary_loc.longitude

    return record


async def _fetch_export_records(
    session: AsyncSession,
    filters: dict,
) -> list[dict]:
    """Fetch voter records applying export filters using streaming.

    Uses server-side cursor with yield_per() to avoid loading all
    records into memory at once.

    Args:
        session: Database session.
        filters: Filter criteria.

    Returns:
        List of voter record dicts.
    """
    query = _build_export_query(filters)

    result = await session.stream(query)

    records = []
    async for partition in result.scalars().partitions(EXPORT_STREAM_BATCH_SIZE):
        for voter in partition:
            records.append(_voter_to_dict(voter))

    return records


async def get_export_job(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> ExportJob | None:
    """Get an export job by ID."""
    result = await session.execute(select(ExportJob).where(ExportJob.id == job_id))
    return result.scalar_one_or_none()


async def list_export_jobs(
    session: AsyncSession,
    *,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ExportJob], int]:
    """List export jobs with optional status filter.

    Args:
        session: Database session.
        status_filter: Optional status to filter by.
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (jobs, total count).
    """
    query = select(ExportJob)
    count_query = select(func.count(ExportJob.id))

    if status_filter:
        query = query.where(ExportJob.status == status_filter)
        count_query = count_query.where(ExportJob.status == status_filter)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(ExportJob.requested_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(query)
    jobs = list(result.scalars().all())

    return jobs, total
