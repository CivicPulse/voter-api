"""User management CLI commands."""

import asyncio

import typer

user_app = typer.Typer()


@user_app.command("create")
def create_user(
    username: str = typer.Option(..., prompt=True, help="Username"),
    email: str = typer.Option(..., prompt=True, help="Email address"),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True, help="Password"),
    role: str = typer.Option("viewer", prompt=True, help="User role (admin/analyst/viewer)"),
    if_not_exists: bool = typer.Option(
        False,
        "--if-not-exists",
        help="Exit successfully if user already exists (idempotent mode)",
    ),
) -> None:
    """Create a new user interactively."""
    asyncio.run(_create_user(username, email, password, role, if_not_exists=if_not_exists))


async def _create_user(
    username: str,
    email: str,
    password: str,
    role: str,
    *,
    if_not_exists: bool = False,
) -> None:
    """Async implementation of user creation."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.schemas.auth import UserCreateRequest
    from voter_api.services.auth_service import create_user

    settings = get_settings()
    init_engine(settings.database_url, schema=settings.database_schema)

    try:
        factory = get_session_factory()
        async with factory() as session:
            request = UserCreateRequest(
                username=username,
                email=email,
                password=password,
                role=role,
            )
            user = await create_user(session, request)
            typer.echo(f"User '{user.username}' created with role '{user.role}'")
    except ValueError as e:
        # NOTE: This relies on auth_service.create_user raising a ValueError
        # whose message contains "already exists" when the user already exists.
        if if_not_exists and "already exists" in str(e):
            typer.echo(f"User '{username}' already exists, skipping (--if-not-exists)")
            return
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
    finally:
        await dispose_engine()


@user_app.command("list")
def list_users() -> None:
    """List all users."""
    asyncio.run(_list_users())


async def _list_users() -> None:
    """Async implementation of user listing."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.auth_service import list_users

    settings = get_settings()
    init_engine(settings.database_url, schema=settings.database_schema)

    try:
        factory = get_session_factory()
        async with factory() as session:
            users, total = await list_users(session)
            typer.echo(f"{'Username':<20} {'Email':<30} {'Role':<10} {'Active':<8}")
            typer.echo("-" * 68)
            for user in users:
                typer.echo(f"{user.username:<20} {user.email:<30} {user.role:<10} {user.is_active!s:<8}")
            typer.echo(f"\nTotal: {total}")
    finally:
        await dispose_engine()
