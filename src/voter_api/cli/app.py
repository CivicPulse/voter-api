"""Typer CLI root application with serve command."""

import typer

app = typer.Typer(name="voter-api", help="Georgia voter data management CLI")


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
    from voter_api.cli.election_cmd import election_app
    from voter_api.cli.export_cmd import export_app
    from voter_api.cli.geocode_cmd import geocode_app
    from voter_api.cli.import_cmd import import_app
    from voter_api.cli.officials_cmd import officials_app
    from voter_api.cli.publish_cmd import publish_app
    from voter_api.cli.user_cmd import user_app

    app.add_typer(db_app, name="db", help="Database migration commands")
    app.add_typer(user_app, name="user", help="User management commands")
    app.add_typer(import_app, name="import", help="Data import commands")
    app.add_typer(geocode_app, name="geocode", help="Geocoding commands")
    app.add_typer(analyze_app, name="analyze", help="Location analysis commands")
    app.add_typer(export_app, name="export", help="Data export commands")
    app.add_typer(publish_app, name="publish", help="Publish static datasets to object storage")
    app.add_typer(election_app, name="election", help="Election tracking commands")
    app.add_typer(officials_app, name="officials", help="Elected officials data commands")


_register_subcommands()
