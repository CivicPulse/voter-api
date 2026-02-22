# voter-api
An API for voter data

## Description

A fastAPI based python web service that provides access to voter data. The API allows users to query voter information based on various parameters such as name, address, and voter ID. It also provides geospatial querying capablities (including a geocoder) to find voters based on location data.

## Packages

- fastAPI
- SQLAlchemy
- PostGIS
- GeoAlchemy2
- loguru
- pydantic
- pandas
- typer
- Jinja2

## Tech notes

Use: 
- 12 factor principles for configuration management.
- use alembic for database migrations.
- Use loguru for logging.
- Use pydantic models for data validation and serialization.
- Database updates should be transctions to ensure data integrity.
- Use async programming for handling requests to improve performance.
- use Conventional Commits standards. see [docs/convential_commits.md](docs/convential_commits.md) for more details.
- Use OpenAPI standards for API documentation.
- use pytest for testing.
- Use Docker for containerization.
- Use GitHub Actions for CI/CD.
- use `uv` for all python commands (e.g. `uv add package`, `uv run python` etc.)
- use `uv` for all python environment management and package management.


## Plain text thoughts about what is needed




