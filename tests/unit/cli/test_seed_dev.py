"""Unit tests for the seed-dev CLI command."""

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from voter_api.cli.db_cmd import db_app

runner = CliRunner()


class TestSeedDevRegistration:
    """Verify the seed-dev command is registered on the db Typer group."""

    def test_seed_dev_command_registered(self) -> None:
        """The 'seed-dev' command should be discoverable on db_app."""
        command_names = [cmd.name for cmd in db_app.registered_commands]
        assert "seed-dev" in command_names

    def test_seed_dev_help(self) -> None:
        """The 'seed-dev' command should display help text."""
        result = runner.invoke(db_app, ["seed-dev", "--help"])
        assert result.exit_code == 0
        assert "Seed lightweight dev data" in result.output


class TestSeedDevExecution:
    """Verify seed-dev calls the async seeder."""

    @patch("voter_api.cli.seed_dev_cmd.asyncio")
    @patch("voter_api.cli.seed_dev_cmd._seed", new_callable=AsyncMock)
    def test_seed_dev_calls_async_seed(self, mock_seed: AsyncMock, mock_asyncio: MagicMock) -> None:
        """seed_dev() should delegate to asyncio.run(_seed())."""
        from voter_api.cli.seed_dev_cmd import seed_dev

        seed_dev()
        mock_asyncio.run.assert_called_once()

    @patch("voter_api.cli.seed_dev_cmd._seed", new_callable=AsyncMock)
    @patch("voter_api.cli.seed_dev_cmd.asyncio")
    def test_seed_dev_via_typer_runner(self, mock_asyncio: MagicMock, mock_seed: AsyncMock) -> None:
        """Invoking via Typer runner should succeed."""
        result = runner.invoke(db_app, ["seed-dev"])
        assert result.exit_code == 0
        mock_asyncio.run.assert_called_once()
