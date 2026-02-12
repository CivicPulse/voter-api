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
    from voter_api.cli.db_cmd import db_app
    from voter_api.cli.user_cmd import user_app

    app.add_typer(db_app, name="db", help="Database migration commands")
    app.add_typer(user_app, name="user", help="User management commands")


_register_subcommands()
