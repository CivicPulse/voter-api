"""Integration tests for the `voter-api seed` CLI command.

Tests cover US1 (full seed), US2 (category filter), and US3 (download-only).
All HTTP requests and database imports are mocked — these tests verify the
CLI orchestration logic, not the underlying download or import implementations.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_httpx import HTTPXMock

from typer.testing import CliRunner

from voter_api.cli.app import app

runner = CliRunner()


def _make_manifest(files: list[dict] | None = None) -> str:
    """Build a valid manifest JSON string for testing."""
    if files is None:
        files = [
            {
                "filename": "counties-by-districts-2023.csv",
                "sha512": "a" * 128,
                "category": "county_district",
                "size_bytes": 4563,
            },
            {
                "filename": "congress-2023-shape.zip",
                "sha512": "b" * 128,
                "category": "boundary",
                "size_bytes": 1000,
            },
            {
                "filename": "Bibb-20260203.csv",
                "sha512": "c" * 128,
                "category": "voter",
                "size_bytes": 2000,
            },
            {
                "filename": "doc.pdf",
                "sha512": "d" * 128,
                "category": "reference",
                "size_bytes": 500,
            },
            {
                "filename": "2024.zip",
                "sha512": "e" * 128,
                "category": "voter_history",
                "size_bytes": 3000,
            },
        ]
    return json.dumps(
        {
            "version": "1",
            "updated_at": "2026-02-20T09:00:00Z",
            "files": files,
        }
    )


# ---------------------------------------------------------------------------
# US1: Bootstrap a Dev/Test Environment
# ---------------------------------------------------------------------------


class TestSeedFullBootstrap:
    """US1: Full seed command downloads and imports everything."""

    def test_seed_with_download_only_no_db(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify seed --download-only works end-to-end without DB."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create files with real checksums for the manifest
        county_content = b"county data"
        county_sha = hashlib.sha512(county_content).hexdigest()
        boundary_content = b"boundary data"
        boundary_sha = hashlib.sha512(boundary_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "counties.csv",
                        "sha512": county_sha,
                        "category": "county_district",
                        "size_bytes": len(county_content),
                    },
                    {
                        "filename": "congress.zip",
                        "sha512": boundary_sha,
                        "category": "boundary",
                        "size_bytes": len(boundary_content),
                    },
                ],
            }
        )

        httpx_mock.add_response(
            url="https://test.example.com/manifest.json",
            text=manifest,
        )
        httpx_mock.add_response(
            url="https://test.example.com/counties.csv",
            content=county_content,
        )
        httpx_mock.add_response(
            url="https://test.example.com/congress.zip",
            content=boundary_content,
        )

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://test.example.com/",
                "--data-dir",
                str(data_dir),
                "--download-only",
            ],
        )

        assert result.exit_code == 0, result.output
        assert (data_dir / "counties.csv").exists()
        assert (data_dir / "congress.zip").exists()

    def test_seed_unreachable_url(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify clear error when Data Root URL is unreachable."""
        import httpx

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://unreachable.example.com/manifest.json",
        )

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://unreachable.example.com/",
                "--data-dir",
                str(data_dir),
            ],
        )

        assert result.exit_code != 0
        assert "Connection refused" in result.output or "error" in result.output.lower()

    def test_seed_skip_if_cached(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify cached files with matching checksums are not re-downloaded."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        content = b"cached boundary data"
        sha = hashlib.sha512(content).hexdigest()

        # Write the file to simulate a cached download
        (data_dir / "congress.zip").write_bytes(content)

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "congress.zip",
                        "sha512": sha,
                        "category": "boundary",
                        "size_bytes": len(content),
                    },
                ],
            }
        )

        httpx_mock.add_response(
            url="https://test.example.com/manifest.json",
            text=manifest,
        )
        # No mock for the file download — should not be requested

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://test.example.com/",
                "--data-dir",
                str(data_dir),
                "--download-only",
            ],
        )

        assert result.exit_code == 0, result.output
        # File should still exist unchanged
        assert (data_dir / "congress.zip").read_bytes() == content

    def test_seed_fail_fast_stops_on_first_error(
        self,
        tmp_path: Path,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Verify --fail-fast stops after first download failure."""
        import httpx

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "counties.csv",
                        "sha512": "a" * 128,
                        "category": "county_district",
                        "size_bytes": 100,
                    },
                    {
                        "filename": "congress.zip",
                        "sha512": "b" * 128,
                        "category": "boundary",
                        "size_bytes": 200,
                    },
                ],
            }
        )

        httpx_mock.add_response(
            url="https://test.example.com/manifest.json",
            text=manifest,
        )
        # First file fails
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://test.example.com/counties.csv",
        )
        # Second file should not be attempted with --fail-fast

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://test.example.com/",
                "--data-dir",
                str(data_dir),
                "--fail-fast",
                "--download-only",
            ],
        )

        assert result.exit_code != 0

    def test_seed_import_order_enforcement(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify imports run in order: county-districts → boundaries → elections → voters → voter-history."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "voter").mkdir()

        # Create files with matching checksums
        order_log: list[str] = []

        county_content = b"county csv data"
        county_sha = hashlib.sha512(county_content).hexdigest()
        boundary_content = b"boundary zip data"
        boundary_sha = hashlib.sha512(boundary_content).hexdigest()
        voter_content = b"voter csv data"
        voter_sha = hashlib.sha512(voter_content).hexdigest()
        vh_content = b"voter history zip data"
        vh_sha = hashlib.sha512(vh_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "Bibb.csv",
                        "sha512": voter_sha,
                        "category": "voter",
                        "size_bytes": len(voter_content),
                    },
                    {
                        "filename": "congress.zip",
                        "sha512": boundary_sha,
                        "category": "boundary",
                        "size_bytes": len(boundary_content),
                    },
                    {
                        "filename": "counties.csv",
                        "sha512": county_sha,
                        "category": "county_district",
                        "size_bytes": len(county_content),
                    },
                    {
                        "filename": "2024.zip",
                        "sha512": vh_sha,
                        "category": "voter_history",
                        "size_bytes": len(vh_content),
                    },
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/Bibb.csv", content=voter_content)
        httpx_mock.add_response(url="https://test.example.com/congress.zip", content=boundary_content)
        httpx_mock.add_response(url="https://test.example.com/counties.csv", content=county_content)
        httpx_mock.add_response(url="https://test.example.com/2024.zip", content=vh_content)

        async def mock_county_districts(file_path: Path) -> None:
            order_log.append("county_district")

        async def mock_all_boundaries(
            data_dir: Path,
            skip_checksum: bool,
            fail_fast: bool,
            skip_files: list[str],
        ) -> None:
            order_log.append("boundary")

        async def mock_voters_batch(
            file_paths: list[Path],
            batch_size: int,
            seed_result: object,
            fail_fast: bool,
            max_voters: int | None = None,
        ) -> None:
            order_log.append("voter")

        def mock_seed_elections(source_url: str) -> int:
            order_log.append("election")
            return 0

        def mock_voter_history_batch(
            batch_size: int,
            seed_result: object,
            fail_fast: bool,
            vh_files: list[object],
        ) -> None:
            order_log.append("voter_history")

        with (
            patch(
                "voter_api.cli.seed_cmd._import_county_districts",
                side_effect=mock_county_districts,
            ),
            patch(
                "voter_api.cli.seed_cmd._import_all_boundaries",
                side_effect=mock_all_boundaries,
            ),
            patch(
                "voter_api.cli.seed_cmd._seed_elections_from_api",
                side_effect=mock_seed_elections,
            ),
            patch(
                "voter_api.cli.seed_cmd._import_voters_batch",
                side_effect=mock_voters_batch,
            ),
            patch(
                "voter_api.cli.seed_cmd._import_voter_history_batch",
                side_effect=mock_voter_history_batch,
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "seed",
                    "--data-root",
                    "https://test.example.com/",
                    "--data-dir",
                    str(data_dir),
                ],
            )

        assert result.exit_code == 0, result.output
        # Verify order: county_district, boundary, election, voter, voter_history
        assert order_log == ["county_district", "boundary", "election", "voter", "voter_history"]


# ---------------------------------------------------------------------------
# US2: Selective Import by Data Type
# ---------------------------------------------------------------------------


class TestSeedCategoryFilter:
    """US2: --category option filters downloads and imports."""

    def test_category_boundaries_only(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify --category boundaries downloads only boundary files."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        boundary_content = b"boundary data"
        boundary_sha = hashlib.sha512(boundary_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "counties.csv",
                        "sha512": "a" * 128,
                        "category": "county_district",
                        "size_bytes": 100,
                    },
                    {
                        "filename": "congress.zip",
                        "sha512": boundary_sha,
                        "category": "boundary",
                        "size_bytes": len(boundary_content),
                    },
                    {
                        "filename": "Bibb.csv",
                        "sha512": "c" * 128,
                        "category": "voter",
                        "size_bytes": 200,
                    },
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/congress.zip", content=boundary_content)

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://test.example.com/",
                "--data-dir",
                str(data_dir),
                "--category",
                "boundaries",
                "--download-only",
            ],
        )

        assert result.exit_code == 0, result.output
        assert (data_dir / "congress.zip").exists()
        assert not (data_dir / "counties.csv").exists()
        assert not (data_dir / "voter" / "Bibb.csv").exists()

    def test_category_voters_only(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify --category voters downloads only voter files."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        voter_content = b"voter data"
        voter_sha = hashlib.sha512(voter_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "congress.zip",
                        "sha512": "b" * 128,
                        "category": "boundary",
                        "size_bytes": 100,
                    },
                    {
                        "filename": "Bibb.csv",
                        "sha512": voter_sha,
                        "category": "voter",
                        "size_bytes": len(voter_content),
                    },
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/Bibb.csv", content=voter_content)

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://test.example.com/",
                "--data-dir",
                str(data_dir),
                "--category",
                "voters",
                "--download-only",
            ],
        )

        assert result.exit_code == 0, result.output
        assert (data_dir / "voter" / "Bibb.csv").exists()
        assert not (data_dir / "congress.zip").exists()

    def test_category_voter_history_only(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify --category voter-history downloads only voter history files."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        vh_content = b"voter history data"
        vh_sha = hashlib.sha512(vh_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "congress.zip",
                        "sha512": "b" * 128,
                        "category": "boundary",
                        "size_bytes": 100,
                    },
                    {
                        "filename": "2024.zip",
                        "sha512": vh_sha,
                        "category": "voter_history",
                        "size_bytes": len(vh_content),
                    },
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/2024.zip", content=vh_content)

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://test.example.com/",
                "--data-dir",
                str(data_dir),
                "--category",
                "voter-history",
                "--download-only",
            ],
        )

        assert result.exit_code == 0, result.output
        assert (data_dir / "2024.zip").exists()
        assert not (data_dir / "congress.zip").exists()

    def test_invalid_category_shows_error(self, tmp_path: Path) -> None:
        """Verify invalid category value produces an error."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://test.example.com/",
                "--data-dir",
                str(data_dir),
                "--category",
                "invalid-category",
            ],
        )

        assert result.exit_code != 0

    def test_category_elections_only(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """--category elections seeds elections from API without downloading files."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Manifest has boundary + voter files — none should be downloaded
        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "congress.zip",
                        "sha512": "b" * 128,
                        "category": "boundary",
                        "size_bytes": 100,
                    },
                    {
                        "filename": "Bibb.csv",
                        "sha512": "c" * 128,
                        "category": "voter",
                        "size_bytes": 200,
                    },
                ],
            }
        )
        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)

        election_calls: list[str] = []

        async def mock_seed_elections(source_url: str) -> int:
            election_calls.append(source_url)
            return 3

        with (
            patch(
                "voter_api.cli.seed_cmd._seed_elections_from_api",
                side_effect=mock_seed_elections,
            ),
            patch("voter_api.cli.seed_cmd._import_voters_batch", new_callable=AsyncMock) as mock_voters,
        ):
            result = runner.invoke(
                app,
                [
                    "seed",
                    "--data-root",
                    "https://test.example.com/",
                    "--data-dir",
                    str(data_dir),
                    "--category",
                    "elections",
                ],
            )

        assert result.exit_code == 0, result.output
        # Elections were seeded from the API
        assert len(election_calls) == 1
        # No voter files downloaded or imported
        assert not (data_dir / "voter" / "Bibb.csv").exists()
        assert not (data_dir / "congress.zip").exists()
        mock_voters.assert_not_called()

    def test_category_elections_skipped_without_voter_category(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """--category boundaries does NOT trigger election seeding."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        boundary_content = b"boundary data"
        boundary_sha = hashlib.sha512(boundary_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "congress.zip",
                        "sha512": boundary_sha,
                        "category": "boundary",
                        "size_bytes": len(boundary_content),
                    },
                ],
            }
        )
        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/congress.zip", content=boundary_content)

        with (
            patch(
                "voter_api.cli.seed_cmd._import_all_boundaries",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.cli.seed_cmd._seed_elections_from_api",
                new_callable=AsyncMock,
            ) as mock_elections,
        ):
            result = runner.invoke(
                app,
                [
                    "seed",
                    "--data-root",
                    "https://test.example.com/",
                    "--data-dir",
                    str(data_dir),
                    "--category",
                    "boundaries",
                ],
            )

        assert result.exit_code == 0, result.output
        # Elections must NOT be seeded when only boundaries category is selected
        mock_elections.assert_not_called()


# ---------------------------------------------------------------------------
# Election boundary_id resolution
# ---------------------------------------------------------------------------


class TestElectionBoundaryResolution:
    """Verify boundary_id is nulled out when referenced boundary doesn't exist locally."""

    def test_elections_seed_nullifies_missing_boundary_ids(self) -> None:
        """boundary_id is set to None for records referencing unknown local boundaries."""
        import uuid
        from datetime import date

        known_id = str(uuid.uuid4())
        unknown_id = str(uuid.uuid4())
        election_id_1 = str(uuid.uuid4())
        election_id_2 = str(uuid.uuid4())

        raw_records = [
            {
                "id": election_id_1,
                "name": "Election With Known Boundary",
                "election_date": date(2024, 11, 5),
                "election_type": "general",
                "district": "State",
                "boundary_id": known_id,
                "district_type": None,
                "district_identifier": None,
                "district_party": None,
                "status": "scheduled",
                "data_source_url": "https://example.com",
                "refresh_interval_seconds": 3600,
                "ballot_item_id": None,
                "last_refreshed_at": None,
                "creation_method": "manual",
            },
            {
                "id": election_id_2,
                "name": "Election With Unknown Boundary",
                "election_date": date(2024, 11, 5),
                "election_type": "general",
                "district": "State",
                "boundary_id": unknown_id,
                "district_type": None,
                "district_identifier": None,
                "district_party": None,
                "status": "scheduled",
                "data_source_url": "https://example.com",
                "refresh_interval_seconds": 3600,
                "ballot_item_id": None,
                "last_refreshed_at": None,
                "creation_method": "manual",
            },
        ]

        # Mock fetch_elections_from_api to return our test records
        # Mock the session: boundary query returns only the known_id
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([(known_id,)]))
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value = mock_context

        with (
            patch(
                "voter_api.lib.data_loader.election_seeder.fetch_elections_from_api",
                new_callable=AsyncMock,
                return_value=raw_records,
            ),
            patch("voter_api.core.database.get_session_factory", return_value=mock_factory),
            patch("sqlalchemy.dialects.postgresql.insert", autospec=False),
        ):
            import asyncio

            from voter_api.cli.seed_cmd import _seed_elections_from_api

            asyncio.run(_seed_elections_from_api("https://example.com"))

        # Record with known boundary_id should keep its value
        assert raw_records[0]["boundary_id"] == known_id
        # Record with unknown boundary_id should be nulled out
        assert raw_records[1]["boundary_id"] is None

    def test_elections_seed_all_nullified_when_no_boundaries(self) -> None:
        """All boundary_ids are nulled out when no boundaries exist locally."""
        import uuid
        from datetime import date

        boundary_id = str(uuid.uuid4())

        raw_records = [
            {
                "id": str(uuid.uuid4()),
                "name": "Election",
                "election_date": date(2024, 11, 5),
                "election_type": "general",
                "district": "State",
                "boundary_id": boundary_id,
                "district_type": None,
                "district_identifier": None,
                "district_party": None,
                "status": "scheduled",
                "data_source_url": "https://example.com",
                "refresh_interval_seconds": 3600,
                "ballot_item_id": None,
                "last_refreshed_at": None,
                "creation_method": "manual",
            },
        ]

        # Session returns empty result (no boundaries exist)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value = mock_context

        with (
            patch(
                "voter_api.lib.data_loader.election_seeder.fetch_elections_from_api",
                new_callable=AsyncMock,
                return_value=raw_records,
            ),
            patch("voter_api.core.database.get_session_factory", return_value=mock_factory),
            patch("sqlalchemy.dialects.postgresql.insert", autospec=False),
        ):
            import asyncio

            from voter_api.cli.seed_cmd import _seed_elections_from_api

            asyncio.run(_seed_elections_from_api("https://example.com"))

        assert raw_records[0]["boundary_id"] is None

    def test_elections_seed_preserves_null_boundary_id(self) -> None:
        """Records with no boundary_id (None) are unaffected by the resolution step."""
        from datetime import date

        raw_records = [
            {
                "id": "some-id",
                "name": "Election",
                "election_date": date(2024, 11, 5),
                "election_type": "general",
                "district": "State",
                "boundary_id": None,
                "district_type": None,
                "district_identifier": None,
                "district_party": None,
                "status": "scheduled",
                "data_source_url": "https://example.com",
                "refresh_interval_seconds": 3600,
                "ballot_item_id": None,
                "last_refreshed_at": None,
                "creation_method": "manual",
            },
        ]

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_factory.return_value = mock_context

        with (
            patch(
                "voter_api.lib.data_loader.election_seeder.fetch_elections_from_api",
                new_callable=AsyncMock,
                return_value=raw_records,
            ),
            patch("voter_api.core.database.get_session_factory", return_value=mock_factory),
            patch("sqlalchemy.dialects.postgresql.insert", autospec=False),
        ):
            import asyncio

            from voter_api.cli.seed_cmd import _seed_elections_from_api

            asyncio.run(_seed_elections_from_api("https://example.com"))

        # No boundary query should be made (no candidate IDs to check) — only the upsert execute
        assert mock_session.execute.call_count == 1
        assert raw_records[0]["boundary_id"] is None


# ---------------------------------------------------------------------------
# US3: Download Only
# ---------------------------------------------------------------------------


class TestSeedDownloadOnly:
    """US3: --download-only flag skips database imports."""

    def test_download_only_no_import(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify --download-only downloads files without importing."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        content = b"test file"
        sha = hashlib.sha512(content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "test.zip",
                        "sha512": sha,
                        "category": "boundary",
                        "size_bytes": len(content),
                    },
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/test.zip", content=content)

        # Patch imports to verify they're NOT called
        with (
            patch(
                "voter_api.cli.seed_cmd._import_county_districts",
                new_callable=AsyncMock,
            ) as mock_cd,
            patch(
                "voter_api.cli.seed_cmd._import_all_boundaries",
                new_callable=AsyncMock,
            ) as mock_boundaries,
            patch(
                "voter_api.cli.seed_cmd._import_voters_batch",
                new_callable=AsyncMock,
            ) as mock_voters,
        ):
            result = runner.invoke(
                app,
                [
                    "seed",
                    "--data-root",
                    "https://test.example.com/",
                    "--data-dir",
                    str(data_dir),
                    "--download-only",
                ],
            )

        assert result.exit_code == 0, result.output
        assert (data_dir / "test.zip").exists()
        mock_cd.assert_not_called()
        mock_boundaries.assert_not_called()
        mock_voters.assert_not_called()

    def test_download_only_with_category(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify --download-only --category voters downloads only voter files."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        voter_content = b"voter data"
        voter_sha = hashlib.sha512(voter_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "congress.zip",
                        "sha512": "b" * 128,
                        "category": "boundary",
                        "size_bytes": 100,
                    },
                    {
                        "filename": "Bibb.csv",
                        "sha512": voter_sha,
                        "category": "voter",
                        "size_bytes": len(voter_content),
                    },
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/Bibb.csv", content=voter_content)

        result = runner.invoke(
            app,
            [
                "seed",
                "--data-root",
                "https://test.example.com/",
                "--data-dir",
                str(data_dir),
                "--download-only",
                "--category",
                "voters",
            ],
        )

        assert result.exit_code == 0, result.output
        assert (data_dir / "voter" / "Bibb.csv").exists()
        assert not (data_dir / "congress.zip").exists()


# ---------------------------------------------------------------------------
# US4: Max Voters Limit
# ---------------------------------------------------------------------------


class TestSeedMaxVoters:
    """US4: --max-voters flag limits total voter records imported."""

    def test_max_voters_passed_to_voter_batch(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify --max-voters is threaded through to _import_voters_batch."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        voter_content = b"voter csv data"
        voter_sha = hashlib.sha512(voter_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "Bibb.csv",
                        "sha512": voter_sha,
                        "category": "voter",
                        "size_bytes": len(voter_content),
                    },
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/Bibb.csv", content=voter_content)

        captured_kwargs: dict = {}

        async def mock_voters_batch(
            file_paths: list[Path],
            batch_size: int,
            seed_result: object,
            fail_fast: bool,
            max_voters: int | None = None,
        ) -> None:
            captured_kwargs["max_voters"] = max_voters

        with (
            patch(
                "voter_api.cli.seed_cmd._import_county_districts",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.cli.seed_cmd._import_all_boundaries",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.cli.seed_cmd._seed_elections_from_api",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.cli.seed_cmd._import_voters_batch",
                side_effect=mock_voters_batch,
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "seed",
                    "--data-root",
                    "https://test.example.com/",
                    "--data-dir",
                    str(data_dir),
                    "--max-voters",
                    "10000",
                ],
            )

        assert result.exit_code == 0, result.output
        assert captured_kwargs["max_voters"] == 10000

    def test_max_voters_default_is_none(self, tmp_path: Path, httpx_mock: HTTPXMock) -> None:
        """Verify --max-voters defaults to None (unlimited) when not specified."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        voter_content = b"voter csv data"
        voter_sha = hashlib.sha512(voter_content).hexdigest()

        manifest = json.dumps(
            {
                "version": "1",
                "updated_at": "2026-02-20T09:00:00Z",
                "files": [
                    {
                        "filename": "Bibb.csv",
                        "sha512": voter_sha,
                        "category": "voter",
                        "size_bytes": len(voter_content),
                    },
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/Bibb.csv", content=voter_content)

        captured_kwargs: dict = {}

        async def mock_voters_batch(
            file_paths: list[Path],
            batch_size: int,
            seed_result: object,
            fail_fast: bool,
            max_voters: int | None = None,
        ) -> None:
            captured_kwargs["max_voters"] = max_voters

        with (
            patch(
                "voter_api.cli.seed_cmd._import_county_districts",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.cli.seed_cmd._import_all_boundaries",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.cli.seed_cmd._seed_elections_from_api",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.cli.seed_cmd._import_voters_batch",
                side_effect=mock_voters_batch,
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "seed",
                    "--data-root",
                    "https://test.example.com/",
                    "--data-dir",
                    str(data_dir),
                ],
            )

        assert result.exit_code == 0, result.output
        assert captured_kwargs["max_voters"] is None
