"""Import CLI commands for voter files, boundary files, and voter history."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.cli.voter_history_cmd import import_voter_history

import_app = typer.Typer()
import_app.command("voter-history")(import_voter_history)


@import_app.command("voters")
def import_voters(
    file: Path = typer.Argument(..., help="Path to voter CSV file", exists=True),  # noqa: B008
    batch_size: int = typer.Option(5000, "--batch-size", help="Records per batch"),  # noqa: B008
) -> None:
    """Import voter data from a CSV file."""
    asyncio.run(_import_voters(file, batch_size))


async def _import_voters(file_path: Path, batch_size: int) -> None:
    """Async implementation of voter import."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.import_service import create_import_job, process_voter_import

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            job = await create_import_job(session, file_name=file_path.name)
            typer.echo(f"Import job created: {job.id}")
            typer.echo(f"Processing {file_path}...")

            job = await process_voter_import(session, job, file_path, batch_size)

            typer.echo(f"\nImport {'completed' if job.status == 'completed' else 'failed'}:")
            typer.echo(f"  Total records:  {job.total_records or 0}")
            typer.echo(f"  Succeeded:      {job.records_succeeded or 0}")
            typer.echo(f"  Failed:         {job.records_failed or 0}")
            typer.echo(f"  Inserted:       {job.records_inserted or 0}")
            typer.echo(f"  Updated:        {job.records_updated or 0}")
            typer.echo(f"  Soft-deleted:   {job.records_soft_deleted or 0}")
    finally:
        await dispose_engine()


@import_app.command("boundaries")
def import_boundaries_cmd(
    file: Path = typer.Argument(..., help="Path to shapefile or GeoJSON", exists=True),
    boundary_type: str = typer.Option(..., "--type", help="Boundary type (e.g., congressional)"),
    source: str = typer.Option(..., "--source", help="Data source (state or county)"),
    county: str | None = typer.Option(None, "--county", help="County name"),
) -> None:
    """Import boundary data from a shapefile or GeoJSON file."""
    asyncio.run(_import_boundaries(file, boundary_type, source, county))


async def _import_boundaries(file_path: Path, boundary_type: str, source: str, county: str | None) -> None:
    """Async implementation of boundary import."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.boundary_service import import_boundaries

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            boundaries = await import_boundaries(
                session,
                file_path=file_path,
                boundary_type=boundary_type,
                source=source,
                county=county,
            )
            typer.echo(f"Imported {len(boundaries)} boundaries")
            typer.echo(f"  Type:   {boundary_type}")
            typer.echo(f"  Source: {source}")
            typer.echo(f"  County: {county or 'all'}")
    finally:
        await dispose_engine()


@import_app.command("county-districts")
def import_county_districts_cmd(
    file: Path = typer.Argument(..., help="Path to county-districts CSV file", exists=True),  # noqa: B008
) -> None:
    """Import county-to-district mappings from a CSV file.

    Populates the county_districts table used for filtering multi-county
    districts (congressional, state senate, state house) by county.
    """
    asyncio.run(_import_county_districts(file))


async def _import_county_districts(file_path: Path) -> None:
    """Async implementation of county-districts import."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.county_district_service import import_county_districts

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            inserted = await import_county_districts(session, file_path)
            typer.echo(f"County-district import complete: {inserted} records inserted")
    finally:
        await dispose_engine()


@import_app.command("all-boundaries")
def import_all_boundaries(
    data_dir: Path = typer.Option("data", "--data-dir", help="Directory containing boundary zip files"),  # noqa: B008
    skip_checksum: bool = typer.Option(False, "--skip-checksum", help="Skip SHA512 checksum verification"),  # noqa: B008
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop on first import error"),  # noqa: B008
    skip: list[str] | None = typer.Option(None, "--skip", help="Zip filename(s) to skip (repeatable)"),  # noqa: B008
) -> None:
    """Import all boundary shapefiles from the data directory.

    Processes all zip files defined in the boundary manifest, extracting
    shapefiles and importing them with the correct type/source/county metadata.
    """
    asyncio.run(_import_all_boundaries(data_dir, skip_checksum, fail_fast, skip or []))


def _validate_boundary_entry(
    entry: Any,
    data_dir: Path,
    skip_checksum: bool,
) -> str | None:
    """Validate a single boundary entry (existence + checksum).

    Args:
        entry: Boundary manifest entry.
        data_dir: Directory containing boundary zip files.
        skip_checksum: Skip SHA512 verification.

    Returns:
        Error message string, or None if valid.
    """
    from voter_api.lib.boundary_loader import resolve_zip_path, verify_sha512

    zip_path = resolve_zip_path(data_dir, entry)
    if not zip_path.exists():
        return f"File not found: {zip_path}"

    if not skip_checksum:
        try:
            verify_sha512(zip_path)
        except ValueError as e:
            return str(e)

    return None


def _extract_boundary_entry(
    entry: Any,
    data_dir: Path,
    tmp_dirs: list[tempfile.TemporaryDirectory[str]],
) -> tuple[Path, list | None, list[dict] | None]:
    """Extract shapefile and optionally pre-filter by state FIPS.

    Args:
        entry: Boundary manifest entry.
        data_dir: Directory containing boundary zip files.
        tmp_dirs: Mutable list to track temp directories for cleanup.

    Returns:
        Tuple of (shp_path, boundary_data_or_None, metadata_or_None).
    """
    from voter_api.lib.boundary_loader import find_shp_in_zip, resolve_zip_path

    zip_path = resolve_zip_path(data_dir, entry)
    tmp_dir = tempfile.TemporaryDirectory()
    tmp_dirs.append(tmp_dir)
    shp_path = find_shp_in_zip(zip_path, Path(tmp_dir.name))

    if entry.state_fips:
        boundary_data, metadata_records = _filter_by_state_fips(shp_path, entry.state_fips)
        return shp_path, boundary_data, metadata_records

    return shp_path, None, None


def _validate_and_extract_boundaries(
    entries: list[Any],
    data_dir: Path,
    skip_checksum: bool,
    fail_fast: bool,
) -> tuple[list[Any], list[Any], list[tempfile.TemporaryDirectory[str]]]:
    """Validate checksums and extract shapefiles for boundary entries.

    Sequential, CPU-bound phase that prepares data for parallel DB import.

    Args:
        entries: Boundary manifest entries.
        data_dir: Directory containing boundary zip files.
        skip_checksum: Skip SHA512 verification.
        fail_fast: Stop on first error.

    Returns:
        Tuple of (failed_results, prepared_entries, tmp_dirs).
        prepared_entries items are (entry, shp_path, boundary_data_or_None, metadata_or_None).
    """
    from voter_api.lib.boundary_loader import ImportResult

    failed: list[Any] = []
    prepared: list[Any] = []
    tmp_dirs: list[tempfile.TemporaryDirectory[str]] = []

    for idx, entry in enumerate(entries, 1):
        typer.echo(f"[{idx}/{len(entries)}] {entry.zip_filename} ({entry.boundary_type})")

        error = _validate_boundary_entry(entry, data_dir, skip_checksum)
        if error:
            result = ImportResult(entry=entry)
            result.error = error
            typer.echo(f"  SKIP: {error}")
            failed.append(result)
            if fail_fast:
                break
            continue

        try:
            shp_path, boundary_data, metadata = _extract_boundary_entry(entry, data_dir, tmp_dirs)
            prepared.append((entry, shp_path, boundary_data, metadata))
        except Exception as e:
            result = ImportResult(entry=entry)
            result.error = str(e)
            typer.echo(f"  FAIL: {result.error}")
            failed.append(result)
            if fail_fast:
                break

    return failed, prepared, tmp_dirs


async def _import_one_boundary(
    factory: Any,
    entry: Any,
    shp_path: Path,
    boundary_data: list | None,
    metadata_records: list[dict] | None,
) -> tuple[bool, int, str | None]:
    """Import a single boundary file in its own session.

    Args:
        factory: Async session factory.
        entry: Boundary manifest entry.
        shp_path: Path to extracted shapefile.
        boundary_data: Pre-filtered boundary data (for state_fips entries), or None.
        metadata_records: County metadata dicts (for state_fips entries), or None.

    Returns:
        Tuple of (success, count, error_message_or_None).
    """
    from voter_api.services.boundary_service import import_boundaries

    async with factory() as session:
        if boundary_data is not None:
            imported = await _import_filtered_boundaries(
                session,
                boundary_data,
                entry.boundary_type,
                entry.source,
                entry.county,
            )
            meta_count = 0
            if metadata_records:
                from voter_api.services.county_metadata_service import import_county_metadata

                meta_count = await import_county_metadata(session, metadata_records)

            suffix = f", {meta_count} county metadata records" if metadata_records else ""
            typer.echo(f"  OK: {len(imported)} boundaries imported{suffix}")
            return True, len(imported), None

        imported = await import_boundaries(
            session,
            file_path=shp_path,
            boundary_type=entry.boundary_type,
            source=entry.source,
            county=entry.county,
        )
        typer.echo(f"  OK: {len(imported)} boundaries imported")
        return True, len(imported), None


async def _import_all_boundaries(
    data_dir: Path,
    skip_checksum: bool,
    fail_fast: bool,
    skip_files: list[str],
) -> None:
    """Async implementation of all-boundaries import.

    Validates and extracts shapefiles sequentially (fast, CPU-bound),
    then imports all boundary files into the database in parallel
    since each boundary type writes to non-overlapping rows.
    """
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.lib.boundary_loader import ImportResult, get_manifest

    manifest = get_manifest()
    skip_set = set(skip_files)
    entries = [e for e in manifest if e.zip_filename not in skip_set]

    if not entries:
        typer.echo("No boundary files to import (all skipped).")
        raise typer.Exit(code=0)

    typer.echo(f"Importing {len(entries)} boundary file(s) from {data_dir.resolve()}\n")

    settings = get_settings()
    init_engine(settings.database_url)

    failed_results, prepared, tmp_dirs = _validate_and_extract_boundaries(
        entries,
        data_dir,
        skip_checksum,
        fail_fast,
    )
    results: list[ImportResult] = list(failed_results)

    try:
        if prepared:
            factory = get_session_factory()

            import_outcomes = await asyncio.gather(
                *[_import_one_boundary(factory, entry, shp, bd, md) for entry, shp, bd, md in prepared],
                return_exceptions=True,
            )

            for i, outcome in enumerate(import_outcomes):
                entry = prepared[i][0]
                result = ImportResult(entry=entry)
                if isinstance(outcome, BaseException):
                    result.error = str(outcome)
                    typer.echo(f"  FAIL: {entry.zip_filename}: {outcome}")
                else:
                    success, count, error = outcome
                    result.success = success
                    result.count = count
                    result.error = error
                results.append(result)
    finally:
        for td in tmp_dirs:
            td.cleanup()
        await dispose_engine()

    _print_summary(results)

    if any(not r.success for r in results):
        raise typer.Exit(code=1)


# Mapping from TIGER/Line shapefile column names to CountyMetadata field names.
_TIGER_TO_METADATA: dict[str, str] = {
    "STATEFP": "fips_state",
    "COUNTYFP": "fips_county",
    "COUNTYNS": "gnis_code",
    "GEOID": "geoid",
    "GEOIDFQ": "geoid_fq",
    "NAME": "name",
    "NAMELSAD": "name_lsad",
    "LSAD": "lsad_code",
    "CLASSFP": "class_fp",
    "MTFCC": "mtfcc",
    "CSAFP": "csa_code",
    "CBSAFP": "cbsa_code",
    "METDIVFP": "metdiv_code",
    "FUNCSTAT": "functional_status",
    "ALAND": "land_area_m2",
    "AWATER": "water_area_m2",
    "INTPTLAT": "internal_point_lat",
    "INTPTLON": "internal_point_lon",
}


def _filter_by_state_fips(shp_path: Path, state_fips: str) -> tuple[list, list[dict]]:
    """Read a shapefile and filter to rows matching a state FIPS code.

    Also extracts county metadata records from the same GeoDataFrame,
    mapping TIGER/Line column names to snake_case CountyMetadata fields.

    Args:
        shp_path: Path to the .shp file.
        state_fips: State FIPS code to filter on (e.g., "13" for Georgia).

    Returns:
        Tuple of (BoundaryData list, metadata dicts list).
    """
    import geopandas as gpd
    from shapely.geometry import MultiPolygon, Polygon

    from voter_api.lib.boundary_loader.shapefile import BoundaryData, _extract_field, _serialize_value

    gdf = gpd.read_file(shp_path, engine="pyogrio")

    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Filter by STATEFP column
    if "STATEFP" in gdf.columns:
        gdf = gdf[gdf["STATEFP"] == state_fips]

    boundaries: list[BoundaryData] = []
    metadata_records: list[dict] = []

    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        elif not isinstance(geom, MultiPolygon):
            continue

        props = {col: _serialize_value(row[col]) for col in gdf.columns if col != "geometry" and row[col] is not None}
        name = _extract_field(row, ["NAME", "Name", "name", "NAMELSAD", "DISTRICT"])
        identifier = _extract_field(row, ["GEOID", "DISTRICT", "DISTRICTID", "ID", "PREC_ID", "PRECINCT"])

        boundaries.append(
            BoundaryData(
                name=name or f"Boundary {len(boundaries) + 1}",
                boundary_identifier=identifier or str(len(boundaries) + 1),
                geometry=geom,
                properties=props,
            )
        )

        # Extract metadata record using TIGER/Line column mapping
        meta: dict = {}
        for tiger_col, meta_field in _TIGER_TO_METADATA.items():
            if tiger_col in gdf.columns:
                val = _serialize_value(row[tiger_col])
                if val is not None:
                    meta[meta_field] = val
        if meta.get("geoid"):
            metadata_records.append(meta)

    return boundaries, metadata_records


async def _import_filtered_boundaries(
    session: AsyncSession,
    boundary_data: list,
    boundary_type: str,
    source: str,
    county: str | None,
) -> list:
    """Import pre-filtered boundary data directly into the database.

    Args:
        session: Async database session.
        boundary_data: List of BoundaryData objects.
        boundary_type: Boundary type string.
        source: Data source string.
        county: County name or None.

    Returns:
        List of imported Boundary records.
    """
    from geoalchemy2.shape import from_shape
    from loguru import logger
    from sqlalchemy import select

    from voter_api.models.boundary import Boundary

    logger.info(f"Importing {len(boundary_data)} filtered boundaries (type={boundary_type})")

    imported: list[Boundary] = []

    for bd in boundary_data:
        geom_wkb = from_shape(bd.geometry, srid=4326)

        result = await session.execute(
            select(Boundary).where(
                Boundary.boundary_type == boundary_type,
                Boundary.boundary_identifier == bd.boundary_identifier,
                Boundary.county == county if county else Boundary.county.is_(None),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.name = bd.name
            existing.geometry = geom_wkb
            existing.properties = bd.properties
            existing.source = source
            imported.append(existing)
        else:
            boundary = Boundary(
                name=bd.name,
                boundary_type=boundary_type,
                boundary_identifier=bd.boundary_identifier,
                source=source,
                county=county,
                geometry=geom_wkb,
                properties=bd.properties,
            )
            session.add(boundary)
            imported.append(boundary)

    await session.commit()
    logger.info(f"Imported {len(imported)} filtered boundaries")
    return imported


def _print_summary(results: list) -> None:
    """Print a summary table of import results."""
    typer.echo("\n" + "=" * 70)
    typer.echo("IMPORT SUMMARY")
    typer.echo("=" * 70)

    ok_count = sum(1 for r in results if r.success)
    fail_count = len(results) - ok_count
    total_boundaries = sum(r.count for r in results)

    for r in results:
        status = "OK" if r.success else "FAIL"
        count_str = f"{r.count} boundaries" if r.success else (r.error or "unknown error")
        typer.echo(f"  [{status:4s}] {r.entry.zip_filename:<45s} {count_str}")

    typer.echo("-" * 70)
    typer.echo(f"  Total: {ok_count} succeeded, {fail_count} failed, {total_boundaries} boundaries imported")
    typer.echo("=" * 70)
