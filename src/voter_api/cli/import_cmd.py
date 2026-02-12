"""Import CLI commands for voter files and boundary files."""

import asyncio
import tempfile
from pathlib import Path

import typer

import_app = typer.Typer()


@import_app.command("voters")
def import_voters(
    file: Path = typer.Argument(..., help="Path to voter CSV file", exists=True),  # noqa: B008
    batch_size: int = typer.Option(1000, "--batch-size", help="Records per batch"),  # noqa: B008
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


async def _import_all_boundaries(
    data_dir: Path,
    skip_checksum: bool,
    fail_fast: bool,
    skip_files: list[str],
) -> None:
    """Async implementation of all-boundaries import."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.lib.boundary_loader import (
        ImportResult,
        find_shp_in_zip,
        get_manifest,
        load_boundaries,
        resolve_zip_path,
        verify_sha512,
    )
    from voter_api.services.boundary_service import import_boundaries

    manifest = get_manifest()
    skip_set = set(skip_files)
    entries = [e for e in manifest if e.zip_filename not in skip_set]

    if not entries:
        typer.echo("No boundary files to import (all skipped).")
        raise typer.Exit(code=0)

    typer.echo(f"Importing {len(entries)} boundary file(s) from {data_dir.resolve()}\n")

    settings = get_settings()
    init_engine(settings.database_url)

    results: list[ImportResult] = []

    try:
        factory = get_session_factory()

        for entry in entries:
            result = ImportResult(entry=entry)
            zip_path = resolve_zip_path(data_dir, entry)

            typer.echo(f"[{len(results) + 1}/{len(entries)}] {entry.zip_filename} ({entry.boundary_type})")

            if not zip_path.exists():
                result.error = f"File not found: {zip_path}"
                typer.echo(f"  SKIP: {result.error}")
                results.append(result)
                if fail_fast:
                    break
                continue

            # Checksum verification
            if not skip_checksum:
                try:
                    verify_sha512(zip_path)
                except ValueError as e:
                    result.error = str(e)
                    typer.echo(f"  FAIL: {result.error}")
                    results.append(result)
                    if fail_fast:
                        break
                    continue

            # Extract and import
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    shp_path = find_shp_in_zip(zip_path, Path(tmp_dir))

                    # Filter to Georgia counties if state_fips is set
                    if entry.state_fips:
                        boundary_data = _filter_by_state_fips(shp_path, entry.state_fips)
                    else:
                        boundary_data = load_boundaries(shp_path)

                    # Import via service with its own session
                    async with factory() as session:
                        if entry.state_fips:
                            # Use filtered data directly via boundary_service internals
                            imported = await _import_filtered_boundaries(
                                session, boundary_data, entry.boundary_type, entry.source, entry.county
                            )
                        else:
                            imported = await import_boundaries(
                                session,
                                file_path=shp_path,
                                boundary_type=entry.boundary_type,
                                source=entry.source,
                                county=entry.county,
                            )

                    result.success = True
                    result.count = len(imported)
                    typer.echo(f"  OK: {result.count} boundaries imported")

            except Exception as e:
                result.error = str(e)
                typer.echo(f"  FAIL: {result.error}")
                if fail_fast:
                    results.append(result)
                    break

            results.append(result)

    finally:
        await dispose_engine()

    # Print summary
    _print_summary(results)

    if any(not r.success for r in results):
        raise typer.Exit(code=1)


def _filter_by_state_fips(shp_path: Path, state_fips: str) -> list:
    """Read a shapefile and filter to rows matching a state FIPS code.

    Args:
        shp_path: Path to the .shp file.
        state_fips: State FIPS code to filter on (e.g., "13" for Georgia).

    Returns:
        List of BoundaryData objects for the matching state.
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

    return boundaries


async def _import_filtered_boundaries(
    session: object,
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
