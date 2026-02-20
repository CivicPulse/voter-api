"""Integration tests for the `voter-api seed` CLI command.

Tests cover US1 (full seed), US2 (category filter), and US3 (download-only).
All HTTP requests and database imports are mocked — these tests verify the
CLI orchestration logic, not the underlying download or import implementations.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from pathlib import Path

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

    def test_seed_with_download_only_no_db(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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

    def test_seed_unreachable_url(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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

    def test_seed_skip_if_cached(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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
        httpx_mock,  # type: ignore[no-untyped-def]
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

    def test_seed_import_order_enforcement(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Verify imports run in order: county-districts → boundaries → voters."""
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
                ],
            }
        )

        httpx_mock.add_response(url="https://test.example.com/manifest.json", text=manifest)
        httpx_mock.add_response(url="https://test.example.com/Bibb.csv", content=voter_content)
        httpx_mock.add_response(url="https://test.example.com/congress.zip", content=boundary_content)
        httpx_mock.add_response(url="https://test.example.com/counties.csv", content=county_content)

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
        # Verify order: county_district first, then boundary, then voter
        assert order_log == ["county_district", "boundary", "voter"]


# ---------------------------------------------------------------------------
# US2: Selective Import by Data Type
# ---------------------------------------------------------------------------


class TestSeedCategoryFilter:
    """US2: --category option filters downloads and imports."""

    def test_category_boundaries_only(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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

    def test_category_voters_only(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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


# ---------------------------------------------------------------------------
# US3: Download Only
# ---------------------------------------------------------------------------


class TestSeedDownloadOnly:
    """US3: --download-only flag skips database imports."""

    def test_download_only_no_import(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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

    def test_download_only_with_category(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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

    def test_max_voters_passed_to_voter_batch(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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

    def test_max_voters_default_is_none(self, tmp_path: Path, httpx_mock) -> None:  # type: ignore[no-untyped-def]
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
