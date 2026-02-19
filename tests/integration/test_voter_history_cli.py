"""Integration tests for voter history CLI command.

Covers T019: test `import voter-history` command with sample file.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from voter_api.cli.app import app

runner = CliRunner()


def _make_completed_job() -> MagicMock:
    """Build a mock completed ImportJob."""
    job = MagicMock()
    job.id = "test-job-id"
    job.status = "completed"
    job.total_records = 10
    job.records_succeeded = 8
    job.records_failed = 1
    job.records_skipped = 1
    job.records_unmatched = 2
    return job


def _patch_cli_deps(mock_job: MagicMock):
    """Context manager stack for patching CLI lazy imports."""
    mock_session = AsyncMock()

    mock_factory = MagicMock()
    mock_factory.return_value = MagicMock(
        __aenter__=AsyncMock(return_value=mock_session),
        __aexit__=AsyncMock(return_value=False),
    )

    return (
        patch("voter_api.core.config.get_settings"),
        patch("voter_api.core.database.init_engine"),
        patch("voter_api.core.database.dispose_engine", new_callable=AsyncMock),
        patch("voter_api.core.database.get_session_factory", return_value=mock_factory),
        patch(
            "voter_api.services.import_service.create_import_job",
            new_callable=AsyncMock,
            return_value=mock_job,
        ),
        patch(
            "voter_api.services.voter_history_service.process_voter_history_import",
            new_callable=AsyncMock,
            return_value=mock_job,
        ),
    )


class TestImportVoterHistoryCLI:
    """Tests for the `import voter-history` CLI command."""

    def test_successful_import(self, tmp_path: Path) -> None:
        """CLI runs import and displays summary."""
        csv_file = tmp_path / "voter_history.csv"
        csv_file.write_text(
            "County Name,Voter Registration Number,Election Date,"
            "Election Type,Party,Ballot Style,Absentee,Provisional,Supplemental\n"
            "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,Y,N,N\n"
        )

        mock_job = _make_completed_job()
        patches = _patch_cli_deps(mock_job)

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = runner.invoke(app, ["import", "voter-history", str(csv_file)])

        assert result.exit_code == 0
        assert "completed" in result.output.lower()
        assert "10" in result.output  # total records

    def test_file_not_found(self) -> None:
        """CLI shows error for non-existent file."""
        result = runner.invoke(app, ["import", "voter-history", "/nonexistent/file.csv"])
        assert result.exit_code != 0

    def test_custom_batch_size(self, tmp_path: Path) -> None:
        """CLI passes --batch-size option to import function."""
        csv_file = tmp_path / "voter_history.csv"
        csv_file.write_text(
            "County Name,Voter Registration Number,Election Date,"
            "Election Type,Party,Ballot Style,Absentee,Provisional,Supplemental\n"
            "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,Y,N,N\n"
        )

        mock_job = _make_completed_job()
        patches = _patch_cli_deps(mock_job)

        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5] as mock_process,
        ):
            result = runner.invoke(app, ["import", "voter-history", str(csv_file), "--batch-size", "500"])

        assert result.exit_code == 0
        mock_process.assert_awaited_once()
        call_args = mock_process.call_args
        assert call_args[0][3] == 500  # batch_size positional arg
