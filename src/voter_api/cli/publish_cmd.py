"""Publish CLI commands for static dataset publishing to object storage."""

import typer

publish_app = typer.Typer(name="publish", help="Publish static datasets to object storage.")
