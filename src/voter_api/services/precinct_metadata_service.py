"""Precinct metadata service — manages GA SoS precinct shapefile attributes."""

import re
import uuid
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.precinct_metadata import PrecinctMetadata

# Mapping from GA SoS precinct shapefile column names to PrecinctMetadata fields.
_PRECINCT_FIELD_MAP: dict[str, str] = {
    "DISTRICT": "sos_district_id",
    "CTYSOSID": "sos_id",
    "FIPS": "fips",
    "FIPS2": "fips_county",
    "CTYNAME": "county_name",
    "CONTY": "county_number",
    "PRECINCT_I": "precinct_id",
    "PRECINCT_N": "precinct_name",
    "AREA": "area",
}


def _extract_precinct_fields(properties: dict) -> dict:
    """Extract and map precinct metadata fields from a shapefile properties dict.

    Args:
        properties: Raw shapefile properties (uppercase column names).

    Returns:
        Dict with snake_case PrecinctMetadata field names.
    """
    result: dict = {}
    for shp_col, meta_field in _PRECINCT_FIELD_MAP.items():
        val = properties.get(shp_col)
        if val is not None:
            if meta_field == "area":
                try:
                    val = Decimal(str(val))
                except (InvalidOperation, ValueError):
                    val = None
            else:
                val = str(val).strip()
            if val is not None:
                result[meta_field] = val
    return result


async def upsert_precinct_metadata(
    session: AsyncSession,
    boundary_id: uuid.UUID,
    properties: dict,
) -> PrecinctMetadata | None:
    """Extract precinct metadata from properties and upsert by boundary_id.

    Args:
        session: Database session.
        boundary_id: FK to the boundaries table.
        properties: Raw shapefile properties dict.

    Returns:
        The upserted PrecinctMetadata record, or None if required fields are missing.
    """
    fields = _extract_precinct_fields(properties)

    # Require the NOT NULL fields
    required = ("sos_district_id", "fips", "fips_county", "county_name", "precinct_id", "precinct_name")
    if not all(fields.get(f) for f in required):
        logger.debug(f"Skipping precinct metadata for boundary {boundary_id}: missing required fields")
        return None

    result = await session.execute(select(PrecinctMetadata).where(PrecinctMetadata.boundary_id == boundary_id))
    existing = result.scalar_one_or_none()

    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    record = PrecinctMetadata(boundary_id=boundary_id, **fields)
    session.add(record)
    return record


async def get_precinct_metadata_batch(
    session: AsyncSession,
    boundary_ids: list[uuid.UUID],
) -> dict[uuid.UUID, PrecinctMetadata]:
    """Look up precinct metadata for multiple boundaries in a single query.

    Args:
        session: Database session.
        boundary_ids: List of boundary UUIDs to look up.

    Returns:
        Dict mapping boundary_id to PrecinctMetadata record.
        Boundaries without metadata are omitted from the result.
    """
    if not boundary_ids:
        return {}

    result = await session.execute(select(PrecinctMetadata).where(PrecinctMetadata.boundary_id.in_(boundary_ids)))
    return {record.boundary_id: record for record in result.scalars().all()}


def _normalize_precinct_name(name: str) -> str:
    """Normalize a precinct name for fuzzy matching.

    Strips common prefixes/suffixes, lowercases, and removes
    non-alphanumeric characters for approximate comparison.

    Args:
        name: Raw precinct name from SOS data or shapefile.

    Returns:
        Normalized name string suitable for comparison.
    """
    n = name.strip().lower()
    for token in ("precinct", "pct", "prec", "prc"):
        n = re.sub(rf"\b{token}\b\.?", "", n)
    n = re.sub(r"[^a-z0-9\s]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    if n.isdigit():
        n = n.lstrip("0") or "0"
    return n


def _build_precinct_indexes(
    records: Sequence[PrecinctMetadata],
) -> tuple[dict[str, PrecinctMetadata], dict[str, PrecinctMetadata], dict[str, list[PrecinctMetadata]]]:
    """Build lookup indexes from a list of precinct metadata records.

    Args:
        records: PrecinctMetadata records for a single county.

    Returns:
        Tuple of (by_precinct_id, by_sos_id, by_normalized_name) dicts.
        by_normalized_name maps to a list to detect collisions.
    """
    by_precinct_id: dict[str, PrecinctMetadata] = {}
    by_sos_id: dict[str, PrecinctMetadata] = {}
    by_normalized_name: dict[str, list[PrecinctMetadata]] = {}

    for record in records:
        pid_key = record.precinct_id.upper()
        if pid_key in by_precinct_id:
            logger.warning(
                "Duplicate precinct_id '{}' in county '{}': precinct '{}' overwrites '{}'",
                pid_key,
                record.county_name,
                record.precinct_id,
                by_precinct_id[pid_key].precinct_id,
            )
        by_precinct_id[pid_key] = record
        if record.sos_id:
            sos_key = record.sos_id.upper()
            if sos_key in by_sos_id:
                logger.warning(
                    "Duplicate sos_id '{}' in county '{}': precinct '{}' overwrites '{}'",
                    sos_key,
                    record.county_name,
                    record.precinct_id,
                    by_sos_id[sos_key].precinct_id,
                )
            by_sos_id[sos_key] = record
        normalized = _normalize_precinct_name(record.precinct_name)
        if normalized:
            by_normalized_name.setdefault(normalized, []).append(record)

    return by_precinct_id, by_sos_id, by_normalized_name


def _match_ids_to_index(
    ids: list[str],
    index: dict[str, PrecinctMetadata],
) -> tuple[dict[str, PrecinctMetadata], list[str]]:
    """Match a list of IDs against a lookup index.

    Args:
        ids: Uppercased IDs to match.
        index: Lookup dict mapping uppercased key to PrecinctMetadata.

    Returns:
        Tuple of (matched dict, unmatched IDs list).
    """
    matched: dict[str, PrecinctMetadata] = {}
    unmatched: list[str] = []
    for uid in ids:
        if uid in index:
            matched[uid] = index[uid]
        else:
            unmatched.append(uid)
    return matched, unmatched


def _match_by_name(
    ids: list[str],
    precinct_names: dict[str, str],
    name_index: dict[str, list[PrecinctMetadata]],
) -> tuple[dict[str, PrecinctMetadata], list[str]]:
    """Match precinct IDs via fuzzy name normalization.

    Args:
        ids: Uppercased SOS precinct IDs still unmatched.
        precinct_names: Mapping of uppercased precinct_id to SOS name.
        name_index: Mapping of normalized name to list of PrecinctMetadata.

    Returns:
        Tuple of (matched dict, unmatched IDs list).
    """
    matched: dict[str, PrecinctMetadata] = {}
    unmatched: list[str] = []
    for uid in ids:
        sos_name = precinct_names.get(uid, uid)
        normalized_sos = _normalize_precinct_name(sos_name)
        candidates = name_index.get(normalized_sos, []) if normalized_sos else []
        if len(candidates) == 1:
            matched[uid] = candidates[0]
        else:
            if len(candidates) > 1:
                logger.warning(
                    "Precinct {} ('{}') has {} name-collision candidates — skipping fuzzy match",
                    uid,
                    sos_name,
                    len(candidates),
                )
            unmatched.append(uid)
    return matched, unmatched


async def get_precinct_metadata_by_county_multi_strategy(
    session: AsyncSession,
    county_name: str,
    precinct_ids: list[str],
    precinct_names: dict[str, str] | None = None,
) -> dict[str, PrecinctMetadata]:
    """Look up precinct metadata using multi-strategy matching.

    Tries three strategies in order, all county-scoped:
    1. Exact match on precinct_id (PRECINCT_I from shapefile)
    2. Exact match on sos_id (CTYSOSID from shapefile)
    3. Fuzzy match on normalized precinct_name

    Args:
        session: Database session.
        county_name: County name to match (case-insensitive).
        precinct_ids: List of SOS precinct IDs to match.
        precinct_names: Optional dict mapping uppercased precinct_id
            to SOS precinct name (for fuzzy name matching).

    Returns:
        Dict mapping uppercased SOS precinct_id to PrecinctMetadata record.
    """
    if not precinct_ids:
        return {}

    if precinct_names:
        precinct_names = {k.upper(): v for k, v in precinct_names.items()}

    all_result = await session.execute(
        select(PrecinctMetadata).where(func.upper(PrecinctMetadata.county_name) == county_name.upper())
    )
    county_records = all_result.scalars().all()
    if not county_records:
        return {}

    by_precinct_id, by_sos_id, by_normalized_name = _build_precinct_indexes(county_records)
    upper_ids = [pid.upper() for pid in precinct_ids]

    # Strategy 1: exact match on precinct_id.
    result, unmatched = _match_ids_to_index(upper_ids, by_precinct_id)
    s1_count = len(result)

    # Strategy 2: exact match on sos_id.
    sos_matched, unmatched = _match_ids_to_index(unmatched, by_sos_id)
    result.update(sos_matched)
    s2_count = len(sos_matched)

    # Strategy 3: fuzzy name matching for remaining.
    # Filter name index to exclude records already matched by strategies 1/2
    # to prevent two SOS IDs mapping to the same boundary geometry.
    s3_count = 0
    if precinct_names and unmatched:
        already_matched = {id(rec) for rec in result.values()}
        filtered_name_index = {k: [r for r in v if id(r) not in already_matched] for k, v in by_normalized_name.items()}
        name_matched, unmatched = _match_by_name(unmatched, precinct_names, filtered_name_index)
        result.update(name_matched)
        s3_count = len(name_matched)

    for uid in unmatched:
        sos_name = precinct_names.get(uid, uid) if precinct_names else uid
        logger.warning(
            "Precinct {} ('{}') in county {} matched no strategy",
            uid,
            sos_name,
            county_name,
        )

    logger.info(
        "County '{}': matched {}/{} precincts (s1={}, s2={}, s3={}, unmatched={})",
        county_name,
        len(result),
        len(upper_ids),
        s1_count,
        s2_count,
        s3_count,
        len(unmatched),
    )

    return result


async def get_precinct_metadata_by_boundary(
    session: AsyncSession,
    boundary_id: uuid.UUID,
) -> PrecinctMetadata | None:
    """Look up precinct metadata by boundary FK.

    Args:
        session: Database session.
        boundary_id: The boundary UUID to look up.

    Returns:
        PrecinctMetadata record or None if not found.
    """
    result = await session.execute(select(PrecinctMetadata).where(PrecinctMetadata.boundary_id == boundary_id))
    return result.scalar_one_or_none()
