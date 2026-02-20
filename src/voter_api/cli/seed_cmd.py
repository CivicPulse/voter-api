"""CLI command for downloading and importing seed data.

The ``voter-api seed`` command fetches a remote manifest, downloads data
files with checksum verification, and imports them using the existing
import pipelines in dependency order: county-districts → boundaries → voters.
"""

from __future__ import annotations

import asyncio
from pathlib import Path  # noqa: TC003 - Typer needs Path at runtime

import typer

from voter_api.lib.data_loader.downloader import download_file, resolve_download_path
from voter_api.lib.data_loader.manifest import fetch_manifest
from voter_api.lib.data_loader.types import (
    DownloadResult,
    FileCategory,
    SeedResult,
)

# Map user-facing CLI category names to manifest FileCategory values.
_CATEGORY_MAP: dict[str, FileCategory] = {
    "boundaries": FileCategory.BOUNDARY,
    "voters": FileCategory.VOTER,
    "county-districts": FileCategory.COUNTY_DISTRICT,
}

_VALID_CATEGORIES = ", ".join(sorted(_CATEGORY_MAP.keys()))


def _validate_data_root(value: str | None) -> str | None:
    """Validate and normalize the --data-root CLI override.

    Enforces HTTPS-only URLs and ensures a trailing slash to match the
    behavior of the Settings.data_root_url validator.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.startswith("https://"):
        raise typer.BadParameter("data_root must use https://")
    if not value.endswith("/"):
        value += "/"
    return value


def seed(
    data_root: str | None = typer.Option(
        None,
        "--data-root",
        help="Override the Data Root URL (default: from DATA_ROOT_URL env var)",
        callback=_validate_data_root,
    ),
    data_dir: Path = typer.Option(
        "data",
        "--data-dir",
        help="Local directory for downloaded files",
    ),
    category: list[str] | None = typer.Option(
        None,
        "--category",
        help=f"Filter by category: {_VALID_CATEGORIES} (repeatable)",
    ),
    download_only: bool = typer.Option(
        False,
        "--download-only",
        help="Download files without importing",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop on first download or import error",
    ),
    skip_checksum: bool = typer.Option(
        False,
        "--skip-checksum",
        help="Skip SHA512 checksum verification",
    ),
    max_voters: int | None = typer.Option(
        None,
        "--max-voters",
        help="Limit total voter records imported (e.g., 10000 for preview environments)",
    ),
) -> None:
    """Download seed data and import into the database.

    Fetches the remote manifest, downloads all listed files (skipping
    cached files with matching checksums), then imports in dependency
    order: county-districts → boundaries → voters.
    """
    # Validate categories
    category_filters: set[FileCategory] | None = None
    if category:
        category_filters = set()
        for cat in category:
            if cat not in _CATEGORY_MAP:
                typer.echo(
                    f"Error: Invalid category '{cat}'. Valid options: {_VALID_CATEGORIES}",
                    err=True,
                )
                raise typer.Exit(code=1)
            category_filters.add(_CATEGORY_MAP[cat])

    asyncio.run(
        _run_seed(
            data_root=data_root,
            data_dir=data_dir,
            category_filters=category_filters,
            download_only=download_only,
            fail_fast=fail_fast,
            skip_checksum=skip_checksum,
            max_voters=max_voters,
        )
    )


async def _run_seed(
    *,
    data_root: str | None,
    data_dir: Path,
    category_filters: set[FileCategory] | None,
    download_only: bool,
    fail_fast: bool,
    skip_checksum: bool,
    max_voters: int | None = None,
) -> None:
    """Async implementation of the seed workflow.

    Args:
        data_root: Override Data Root URL, or None to use config.
        data_dir: Local directory for downloaded files.
        category_filters: If set, only process these categories.
        download_only: If True, skip database imports.
        fail_fast: If True, stop on first error.
        skip_checksum: If True, skip SHA512 verification.
        max_voters: If set, limit total voter records imported.
    """
    from voter_api.core.config import get_settings

    settings = get_settings()
    root_url = data_root or settings.data_root_url

    # --- Phase 1: Fetch manifest ---
    typer.echo(f"Fetching manifest from {root_url}")
    try:
        manifest = await fetch_manifest(root_url)
    except Exception as exc:
        typer.echo(f"Error fetching manifest: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Manifest loaded: {len(manifest.files)} files")

    # Filter by category
    entries = list(manifest.files)
    if category_filters:
        entries = [e for e in entries if e.category in category_filters]
        cats = ", ".join(c.value for c in category_filters)
        typer.echo(f"Filtered to {len(entries)} files matching categories: {cats}")

    if not entries:
        typer.echo("No files to process.")
        raise typer.Exit(code=0)

    # --- Phase 2: Download files ---
    typer.echo(f"\nDownloading {len(entries)} file(s) to {data_dir.resolve()}")
    seed_result = SeedResult()

    for i, entry in enumerate(entries, 1):
        dest = resolve_download_path(entry, data_dir)
        url = f"{root_url.rstrip('/')}/{entry.filename}"

        typer.echo(f"\n[{i}/{len(entries)}] {entry.filename} ({entry.size_bytes:,} bytes)")

        result = await download_file(
            url=url,
            dest=dest,
            expected_sha512=entry.sha512,
            size_bytes=entry.size_bytes,
            skip_checksum=skip_checksum,
            entry=entry,
        )
        seed_result.downloads.append(result)

        if result.success:
            if result.downloaded:
                seed_result.total_downloaded_bytes += entry.size_bytes
                typer.echo(f"  Downloaded: {dest}")
            else:
                seed_result.total_skipped += 1
                typer.echo(f"  Cached: {dest}")
        else:
            typer.echo(f"  FAILED: {result.error}", err=True)
            seed_result.success = False
            if fail_fast:
                typer.echo("Stopping (--fail-fast).", err=True)
                raise typer.Exit(code=1)

    # --- Download summary ---
    downloaded_count = sum(1 for r in seed_result.downloads if r.downloaded)
    failed_count = sum(1 for r in seed_result.downloads if not r.success)
    typer.echo(
        f"\nDownload complete: {downloaded_count} downloaded, {seed_result.total_skipped} cached, {failed_count} failed"
    )

    if failed_count > 0 and fail_fast:
        raise typer.Exit(code=1)

    # --- Phase 3: Import (unless --download-only) ---
    if download_only:
        typer.echo("\n--download-only specified, skipping imports.")
        if not seed_result.success:
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    # Only import files that downloaded/cached successfully
    successful = [r for r in seed_result.downloads if r.success and r.local_path]

    await _run_imports(
        successful_downloads=successful,
        data_dir=data_dir,
        category_filters=category_filters,
        fail_fast=fail_fast,
        skip_checksum=skip_checksum,
        seed_result=seed_result,
        max_voters=max_voters,
    )

    if not seed_result.success:
        typer.echo("\nSeed completed with errors.", err=True)
        raise typer.Exit(code=1)

    typer.echo("\nSeed completed successfully.")


async def _run_imports(
    *,
    successful_downloads: list[DownloadResult],
    data_dir: Path,
    category_filters: set[FileCategory] | None,
    fail_fast: bool,
    skip_checksum: bool,
    seed_result: SeedResult,
    max_voters: int | None = None,
) -> None:
    """Run database imports in dependency order.

    Import order (FR-012): county-districts → boundaries → voters.
    Reference-category files are never imported.

    Args:
        successful_downloads: Download results with local_path set.
        data_dir: Local data directory.
        category_filters: Active category filters, or None for all.
        fail_fast: Stop on first error.
        skip_checksum: Pass to boundary import.
        seed_result: Mutable result to track import outcomes.
        max_voters: If set, limit total voter records imported.
    """
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, init_engine

    settings = get_settings()
    init_engine(settings.database_url, schema=settings.database_schema)

    try:
        # County-districts first
        county_files = [r for r in successful_downloads if r.entry.category == FileCategory.COUNTY_DISTRICT]
        if county_files and (category_filters is None or FileCategory.COUNTY_DISTRICT in category_filters):
            typer.echo("\n--- Importing county-district mappings ---")
            for r in county_files:
                assert r.local_path is not None
                try:
                    await _import_county_districts(r.local_path)
                    seed_result.import_results[f"county_district:{r.entry.filename}"] = "success"
                except Exception as exc:
                    typer.echo(f"  IMPORT FAILED: {r.entry.filename}: {exc}", err=True)
                    seed_result.success = False
                    seed_result.import_results[f"county_district:{r.entry.filename}"] = str(exc)
                    if fail_fast:
                        return

        # Boundaries second
        boundary_files = [r for r in successful_downloads if r.entry.category == FileCategory.BOUNDARY]
        if boundary_files and (category_filters is None or FileCategory.BOUNDARY in category_filters):
            typer.echo("\n--- Importing boundaries ---")
            try:
                await _import_all_boundaries(data_dir, skip_checksum, fail_fast, [])
                seed_result.import_results["boundary"] = "success"
            except Exception as exc:
                typer.echo(f"  IMPORT FAILED: boundaries: {exc}", err=True)
                seed_result.success = False
                seed_result.import_results["boundary"] = str(exc)
                if fail_fast:
                    return

        # Voters last — parallel processing with single index lifecycle
        voter_files = [r for r in successful_downloads if r.entry.category == FileCategory.VOTER]
        if voter_files and (category_filters is None or FileCategory.VOTER in category_filters):
            typer.echo("\n--- Importing voter files ---")
            voter_paths = [r.local_path for r in voter_files if r.local_path is not None]
            await _import_voters_batch(
                voter_paths,
                batch_size=settings.import_batch_size,
                seed_result=seed_result,
                fail_fast=fail_fast,
                max_voters=max_voters,
            )

    finally:
        await dispose_engine()


async def _import_county_districts(file_path: Path) -> None:
    """Import county-district mappings using the existing service.

    Args:
        file_path: Path to the county-districts CSV file.
    """
    from voter_api.core.database import get_session_factory
    from voter_api.services.county_district_service import import_county_districts

    factory = get_session_factory()
    async with factory() as session:
        inserted = await import_county_districts(session, file_path)
        typer.echo(f"  County-district import: {inserted} records")


async def _import_all_boundaries(
    data_dir: Path,
    skip_checksum: bool,
    fail_fast: bool,
    skip_files: list[str],
) -> None:
    """Import all boundaries using the existing import pipeline.

    Delegates to the same logic as ``voter-api import all-boundaries``.
    Re-initializes the database engine afterward because the delegated
    function disposes the engine in its own ``finally`` block.

    Args:
        data_dir: Directory containing boundary zip files.
        skip_checksum: Skip SHA512 checksum verification.
        fail_fast: Stop on first import error.
        skip_files: Filenames to skip.
    """
    from voter_api.cli.import_cmd import _import_all_boundaries as _do_import

    await _do_import(data_dir, skip_checksum, fail_fast, skip_files)

    # Re-init engine: _do_import disposes it in its finally block,
    # but seed_cmd._run_imports needs it for subsequent voter imports.
    from voter_api.core.config import get_settings
    from voter_api.core.database import init_engine

    settings = get_settings()
    init_engine(settings.database_url, schema=settings.database_schema)


async def _import_voters(file_path: Path, batch_size: int) -> None:
    """Import a voter CSV file using the existing service.

    Args:
        file_path: Path to the voter CSV file.
        batch_size: Records per batch.
    """
    from voter_api.core.database import get_session_factory
    from voter_api.services.import_service import create_import_job, process_voter_import

    factory = get_session_factory()
    async with factory() as session:
        job = await create_import_job(session, file_name=file_path.name)
        typer.echo(f"  Import job: {job.id} for {file_path.name}")
        job = await process_voter_import(session, job, file_path, batch_size)
        typer.echo(f"  Result: {job.records_succeeded or 0} succeeded, {job.records_failed or 0} failed")


async def _import_voters_batch(
    file_paths: list[Path],
    batch_size: int,
    seed_result: SeedResult,
    fail_fast: bool,
    max_voters: int | None = None,
) -> None:
    """Import multiple voter files with a single index lifecycle.

    When ``max_voters`` is None, files are processed concurrently via
    ``asyncio.gather``. When a limit is set, files are processed
    sequentially so a running budget can be tracked across files;
    processing stops once the budget is exhausted.

    Args:
        file_paths: Voter CSV file paths.
        batch_size: Records per batch per file.
        seed_result: Mutable result to track import outcomes.
        fail_fast: If True, propagate the first error.
        max_voters: If set, limit total voter records imported across
            all files. Files are processed sequentially when set.
    """
    from sqlalchemy import text

    from voter_api.core.database import get_session_factory
    from voter_api.services.import_service import (
        bulk_import_context,
        create_import_job,
        process_voter_import,
    )

    if not file_paths:
        return

    if max_voters is not None:
        typer.echo(f"  Voter import limited to {max_voters:,} records total")

    factory = get_session_factory()

    async def _process_one(file_path: Path, max_records: int | None = None) -> int:
        """Process a single voter file in its own session.

        Returns:
            Number of records successfully imported.
        """
        async with factory() as session:
            # Note: synchronous_commit is a PostgreSQL *connection*-level setting.
            # bulk_import_context() sets it on the lifecycle session used for
            # index/constraint management, but each call to factory() may use a
            # different DB connection. We therefore disable synchronous_commit on
            # every per-file import session as well.
            await session.execute(text("SET synchronous_commit = 'off'"))
            job = await create_import_job(session, file_name=file_path.name)
            typer.echo(f"  Import job: {job.id} for {file_path.name}")
            job = await process_voter_import(
                session,
                job,
                file_path,
                batch_size,
                skip_optimizations=True,
                max_records=max_records,
            )
            typer.echo(
                f"  Result ({file_path.name}): {job.records_succeeded or 0} succeeded, {job.records_failed or 0} failed"
            )
            return job.records_succeeded or 0

    # Use a dedicated session for the optimization lifecycle (drop/rebuild indexes)
    async with factory() as lifecycle_session, bulk_import_context(lifecycle_session):
        if max_voters is not None:
            # Sequential processing with a running budget
            remaining = max_voters
            for fp in file_paths:
                if remaining <= 0:
                    typer.echo(f"  Skipping {fp.name} (voter limit reached)")
                    break
                try:
                    imported = await _process_one(fp, max_records=remaining)
                    remaining -= imported
                    seed_result.import_results[f"voter:{fp.name}"] = "success"
                except Exception as exc:
                    typer.echo(f"  IMPORT FAILED: {fp.name}: {exc}", err=True)
                    seed_result.success = False
                    seed_result.import_results[f"voter:{fp.name}"] = str(exc)
                    if fail_fast:
                        return
        else:
            # Concurrent processing (no limit)
            tasks = [_process_one(fp) for fp in file_paths]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for fp, result in zip(file_paths, results, strict=True):
                if isinstance(result, Exception):
                    typer.echo(f"  IMPORT FAILED: {fp.name}: {result}", err=True)
                    seed_result.success = False
                    seed_result.import_results[f"voter:{fp.name}"] = str(result)
                    if fail_fast:
                        return
                else:
                    seed_result.import_results[f"voter:{fp.name}"] = "success"
