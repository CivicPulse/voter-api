# Research: Voter Data Management

**Branch**: `001-voter-data-management` | **Date**: 2026-02-11
**Purpose**: Resolve all technology decisions and document best practices
for the implementation plan.

## 1. FastAPI + SQLAlchemy 2.x Async Session Management

**Decision**: Use `create_async_engine` with `asyncpg` driver,
`async_sessionmaker` for session factories, and a FastAPI dependency
with `yield` (`async def get_session()`) that provides one `AsyncSession`
per request via `Annotated[AsyncSession, Depends(get_session)]`.

**Rationale**: SQLAlchemy 2.0's `ext.asyncio` module provides
`AsyncSession` and `create_async_engine` as first-class async primitives.
Create a module-level `async_engine` (once at startup, disposed at
shutdown via FastAPI lifespan), then create an `async_sessionmaker` bound
to that engine. Each request gets its own session via a FastAPI dependency
that uses `async with async_sessionmaker() as session: yield session`.
Use `Annotated` type aliases to reduce boilerplate.

**Alternatives Considered**:
- **SQLModel (sync)**: Blocks the event loop, unsuitable for production
  with PostGIS queries.
- **encode/databases**: Lacks full ORM support, less actively maintained.
- **Middleware-based session**: Less explicit than dependency injection,
  harder to test.

---

## 2. GeoAlchemy2 + PostGIS Spatial Queries

**Decision**: Use GeoAlchemy2's `Geometry` column type
(`Geometry('POINT', srid=4326)` for voter locations,
`Geometry('MULTIPOLYGON', srid=4326)` for boundaries) with GIST spatial
indexes. Point-in-polygon via `func.ST_Contains(boundary.geom, voter.point)`
or `func.ST_Within(voter.point, boundary.geom)`.

**Rationale**: GeoAlchemy2 extends SQLAlchemy with PostGIS types and
functions. Spatial functions are invoked via `func.ST_Contains`,
`func.ST_Intersects`, etc. GIST indexes provide sub-second spatial
lookups even at scale. Works identically through `AsyncSession` since
spatial functions operate at the SQL level. Use `to_shape()` /
`from_shape()` for Shapely interop.

**Alternatives Considered**:
- **Raw SQL spatial queries**: Loses ORM benefits and type safety.
- **Shapely-only (in-memory)**: Much slower than PostGIS index-backed
  queries for large datasets.
- **Django + GeoDjango**: Not async-compatible; FastAPI already chosen.

---

## 3. Shapefile and GeoJSON Ingestion in Python

**Decision**: Use **GeoPandas** (with `pyogrio` engine) for reading
shapefiles and GeoJSON into GeoDataFrames, then convert geometries
to WKB via GeoAlchemy2's `from_shape()` for PostGIS insertion.

**Rationale**: GeoPandas provides a high-level DataFrame-like API for
geospatial file I/O supporting `.shp`, `.geojson`, `.gpkg`. The `pyogrio`
engine (GDAL/OGR-based) is significantly faster than legacy Fiona for
large files. GeoPandas handles CRS transformations via `.to_crs()` for
reprojecting to EPSG:4326. For insertion, iterate GeoDataFrame rows and
use `from_shape(shapely_geom, srid=4326)` for WKBElement objects.

**Alternatives Considered**:
- **Fiona (direct)**: Lower-level, good for streaming, but more manual
  geometry handling.
- **pyshp**: Pure Python, no GDAL dependency, but much slower and no CRS.
- **ogr2ogr (CLI)**: Fast for bulk loading but harder to integrate with
  validation logic.

---

## 4. Pluggable Geocoder Architecture

**Decision**: Define an abstract `BaseGeocoder` class (using `abc.ABC`)
with `async def geocode(address: str) -> GeocodingResult` and
`async def reverse(lat, lon) -> GeocodingResult`. Implement concrete
providers (e.g., `CensusGeocoder`, `NominatimGeocoder`). Use a
registry/factory for provider selection with a separate caching layer
and asyncio-based rate limiting.

**Rationale**: Follow `geopy`'s pattern: base class with `geocode()` /
`reverse()`, subclasses per provider. Make it async-native. Rate limiting
via `asyncio.Semaphore` or `aiolimiter.AsyncLimiter` per provider.
Caching is a separate concern: use a decorator/middleware that hashes
normalized addresses as keys and stores results in the database. A
`GeocoderManager` can implement fallback chains (Census → Nominatim).

**Alternatives Considered**:
- **Using geopy directly**: Limited async support, adds heavyweight
  dependency for just an interface pattern.
- **Single-provider**: Not resilient; Census geocoder has downtime.
- **HTTP-level caching**: Caches at wrong level, prevents normalized
  address matching.

---

## 5. JWT Authentication with FastAPI

**Decision**: Use **PyJWT** (`pyjwt`) for JWT token creation/validation,
**passlib** with **bcrypt** for password hashing, FastAPI's
`OAuth2PasswordBearer` for the token scheme. Encode role claims directly
in the JWT payload (`{"sub": username, "role": "admin", "exp": ...}`).

**Rationale**: FastAPI docs recommend PyJWT over python-jose (unmaintained).
Pattern: (1) define `OAuth2PasswordBearer(tokenUrl="auth/login")`; (2)
`create_access_token(data, expires_delta)` via `jwt.encode()`; (3)
`get_current_user` dependency decodes/validates token via `jwt.decode()`
and looks up user; (4) chain dependencies for role checking. Refresh
tokens: issue separate long-lived token, provide `/auth/refresh`
endpoint. Use bcrypt for password hashing.

**Alternatives Considered**:
- **python-jose**: Unmaintained; PyJWT is actively maintained.
- **passlib[argon2]**: Argon2 is stronger than bcrypt but adds a C
  dependency; bcrypt is well-supported and sufficient.
- **Third-party auth (Auth0)**: Adds external dependency and cost;
  not warranted for an internal API.

---

## 6. Alembic with Async SQLAlchemy 2.x

**Decision**: Use Alembic's `async` template (`alembic init -t async`)
which generates an `env.py` preconfigured with `async_engine_from_config`,
`run_sync`, and the async migration pattern. Import `geoalchemy2` in
`env.py` so spatial types are registered.

**Rationale**: Alembic provides an explicit async recipe: define
`do_run_migrations(connection)` as sync, call it via
`await connection.run_sync(do_run_migrations)` in an async context.
The `async` template generates this boilerplate. For GeoAlchemy2,
`import geoalchemy2` in `env.py` registers `Geometry`/`Geography`
types for autogenerated migrations. GeoAlchemy2 includes Alembic helpers
(`geoalchemy2.alembic_helpers`) for spatial index management. Set
`compare_type=True` for spatial column type change detection.

**Alternatives Considered**:
- **Manual sync Alembic**: Requires separate sync connection string.
- **Programmatic migration runner**: Useful for testing, not a CLI
  replacement.

---

## 7. Batch Processing Large CSVs

**Decision**: Use `pandas.read_csv()` with `chunksize` (5,000–10,000 rows
per chunk), validate/transform each chunk, then bulk-insert via
SQLAlchemy's `session.execute(insert(Model), list_of_dicts)` with the
asyncpg driver's batch mode.

**Rationale**: Pandas' `read_csv(filepath, chunksize=N)` returns an
iterator for processing arbitrarily large files without loading
everything into memory. Each chunk is validated as a DataFrame using
vectorized operations. SQLAlchemy 2.x's `insert().values()` with a
list of dicts performs efficient bulk inserts. Asyncpg batches multiple
inserts into a single `INSERT ... VALUES` statement. Use `tqdm` for
progress tracking. Commit every N chunks to avoid transaction bloat.

**Alternatives Considered**:
- **Python csv module**: Lower memory but requires manual type conversion.
- **Polars**: Faster but adds another dependency alongside Pandas.
- **COPY command**: Fastest but bypasses ORM validation.
- **Dask**: Overkill for single-file sub-million-row processing.

---

## 8. uv Project Setup for Library-First Python Packages

**Decision**: Use `pyproject.toml` with `hatchling` build backend,
`[project.scripts]` for CLI entry points via Typer, and
`[dependency-groups]` for dev dependencies. Use `uv add` / `uv add --dev`
for dependency management.

**Rationale**: uv supports full PEP 621 metadata in `pyproject.toml`.
Setup: (1) `[build-system] requires = ["hatchling"]`; (2) runtime
dependencies in `[project] dependencies`; (3) dev dependencies via
`uv add --dev`; (4) CLI entry point as
`[project.scripts] voter-api = "voter_api.cli:app"`; (5) test config
in `[tool.pytest.ini_options]`; (6) ruff config in `[tool.ruff]`.
Use `uv build` for distributions and `uv publish` for PyPI. The
lockfile (`uv.lock`) is checked into version control.

**Alternatives Considered**:
- **setuptools**: More boilerplate, requires `setup.cfg`/`setup.py`.
- **Poetry**: Non-standard `[tool.poetry]` section; uv is faster.
- **Flit**: Simpler but less flexible for complex builds.

---

## 9. Docker Multi-Stage Build for Python/uv

**Decision**: Two-stage Dockerfile: (1) builder stage based on
`ghcr.io/astral-sh/uv:python3.11-bookworm-slim` that installs deps
with `uv sync --locked --no-install-project` (layer caching), then
copies source and runs `uv sync --locked --no-editable`; (2) final
stage based on `python:3.11-slim-bookworm` that copies only `.venv`
from builder. docker-compose with `postgis/postgis:15-3.4`.

**Rationale**: Official uv Docker docs recommend: (a) copy uv via
`COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/` pinning
version; (b) intermediate layers for dependency caching; (c)
`--no-editable` for self-contained `.venv`; (d) `UV_COMPILE_BYTECODE=1`
for production. PostGIS available as `postgis/postgis:15-3.4` with
`pg_isready` health check. Use `depends_on: db: condition: service_healthy`.

**Alternatives Considered**:
- **Single-stage build**: Larger images with build tools included.
- **pip-based Docker**: Slower resolution, no lockfile determinism.
- **Alpine final image**: Compatibility issues with C extensions (GDAL,
  Shapely).

---

## 10. Address Normalization for Geocoding

**Decision**: Build a custom `AddressNormalizer` class that reconstructs
full addresses from decomposed components using USPS Publication 28
rules: uppercase, abbreviate directionals (NORTH→N) and street types
(STREET→ST, AVENUE→AVE), remove punctuation, collapse whitespace. Use
normalized form as both geocoder input and cache key.

**Rationale**: Voter data stores decomposed address fields. Geocoders
expect a single string. The normalization pipeline: (1) map directional
words to USPS abbreviations; (2) map street types to canonical
abbreviations from USPS Pub 28 Appendix C; (3) handle unit designators;
(4) strip leading zeros from house numbers; (5) produce deterministic
string like `"123 N MAIN ST APT 4B, SPRINGFIELD, GA 30301"`. This
normalized form serves as both geocoder input and cache key, ensuring
variant spellings map to the same cache entry.

**Alternatives Considered**:
- **usaddress library**: For parsing freeform addresses; unnecessary
  when data is already decomposed.
- **libpostal**: Powerful but ~2GB model, complex installation; overkill
  for pre-decomposed addresses.
- **Geocoder-side normalization**: Works for accuracy but defeats cache
  deduplication.
- **USPS Address Validation API**: Gold standard but adds external
  dependency and cost.
