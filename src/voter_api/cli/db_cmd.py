"""Database migration CLI commands using Alembic programmatically."""

import typer
from loguru import logger

db_app = typer.Typer()


@db_app.command()
def upgrade(
    revision: str = typer.Argument("head", help="Target revision"),
) -> None:
    """Run database migrations up to the target revision."""
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    logger.info(f"Upgrading database to {revision}")
    command.upgrade(config, revision)
    logger.info("Database upgrade complete")


@db_app.command()
def downgrade(
    revision: str = typer.Argument("-1", help="Target revision"),
) -> None:
    """Rollback database migration to the target revision."""
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    logger.info(f"Downgrading database to {revision}")
    command.downgrade(config, revision)
    logger.info("Database downgrade complete")


@db_app.command()
def current() -> None:
    """Show the current database migration revision."""
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    command.current(config, verbose=True)
