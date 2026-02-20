"""Typer CLI root application with serve command."""

import typer

from voter_api.core.config import get_settings
from voter_api.core.logging import setup_logging

app = typer.Typer(name="voter-api", help="Georgia voter data management CLI")


@app.callback()
def _main_callback() -> None:
    """Initialize logging for all CLI commands."""
    settings = get_settings()
    setup_logging(settings.log_level, log_dir=settings.log_dir)


@app.command()
def serve(
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),  # noqa: S104
    port: int = typer.Option(8000, "--port", help="Bind port"),
) -> None:
    """Start the API server."""
    import uvicorn

    uvicorn.run(
        "voter_api.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


def _register_subcommands() -> None:
    """Register all CLI subcommand groups."""
    from voter_api.cli.analyze_cmd import analyze_app
    from voter_api.cli.db_cmd import db_app
    from voter_api.cli.deploy_check_cmd import deploy_check
    from voter_api.cli.election_cmd import election_app
    from voter_api.cli.export_cmd import export_app
    from voter_api.cli.geocode_cmd import geocode_app
    from voter_api.cli.import_cmd import import_app
    from voter_api.cli.meetings_cmd import meetings_app
    from voter_api.cli.officials_cmd import officials_app
    from voter_api.cli.publish_cmd import publish_app
    from voter_api.cli.seed_cmd import seed
    from voter_api.cli.user_cmd import user_app

    app.add_typer(db_app, name="db", help="Database migration commands")
    app.add_typer(user_app, name="user", help="User management commands")
    app.add_typer(import_app, name="import", help="Data import commands")
    app.add_typer(geocode_app, name="geocode", help="Geocoding commands")
    app.add_typer(analyze_app, name="analyze", help="Location analysis commands")
    app.add_typer(export_app, name="export", help="Data export commands")
    app.add_typer(publish_app, name="publish", help="Publish static datasets to object storage")
    app.add_typer(election_app, name="election", help="Election tracking commands")
    app.add_typer(meetings_app, name="meetings", help="Meeting record management commands")
    app.add_typer(officials_app, name="officials", help="Elected officials data commands")
    app.command("deploy-check")(deploy_check)
    app.command("seed")(seed)


_register_subcommands()
