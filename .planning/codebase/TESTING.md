# Testing Patterns

**Analysis Date:** 2026-03-13

## Test Framework

**Runner:**
- pytest 8.0.0+ with pytest-asyncio 0.25.0+
- Config: `pyproject.toml` `[tool.pytest.ini_options]`
- `asyncio_mode = "auto"` — all `async def` test functions run automatically without `@pytest.mark.asyncio` on the function itself (the decorator is still used in many existing files, both work)
- `asyncio_default_fixture_loop_scope = "session"` — session-scoped async fixtures share one event loop
- Default options: `-ra -q` (show extra test summary, quiet output)
- `filterwarnings = ["ignore::DeprecationWarning"]`

**Assertion Library:**
- Standard pytest assertions
- `pytest.approx()` for floats: `assert result.latitude == pytest.approx(33.749)`
- `pytest.raises()` for exceptions: `with pytest.raises(GeocodingProviderError, match="census"):`
- `pytest.MonkeyPatch` for env var manipulation in config tests

**Run Commands:**
```bash
uv run pytest                                            # Run all tests
uv run pytest tests/unit/                               # Unit tests only
uv run pytest tests/integration/                        # Integration tests only
uv run pytest tests/contract/                           # Contract tests only
uv run pytest tests/e2e/ -v                             # E2E tests (requires PostGIS)
uv run pytest --cov=voter_api --cov-report=term-missing # Coverage report (90% threshold)
uv run pytest tests/unit/lib/test_geocoder/test_cache.py  # Single file
uv run pytest -k "test_import"                          # Keyword match
uv run pytest -x                                        # Stop on first failure
```

## Test File Organization

**Location:** `tests/` directory, separate from `src/`. Test structure mirrors source structure.

**Naming:**
- Test modules: `test_` prefix — `test_cache.py`, `test_census.py`, `test_auth.py`
- Test classes: `Test<Feature>` — `class TestCacheFunctions`, `class TestCensusResponseParsing`, `class TestGetElection`
- Test methods: `test_<description>` — `def test_cache_lookup_is_async`, `def test_successful_match`, `def test_get_election_404`

**Directory layout:**
```
tests/
├── conftest.py                        # Shared: async_engine, async_session, Settings, JWT tokens
├── unit/                              # Pure logic — no DB, no HTTP, in-memory SQLite only
│   ├── lib/
│   │   ├── test_geocoder/             # One directory per lib subpackage
│   │   │   ├── test_cache.py
│   │   │   ├── test_census.py
│   │   │   ├── test_fallback.py
│   │   │   └── ...
│   │   ├── test_analyzer/
│   │   ├── test_exporter/
│   │   ├── test_meetings/
│   │   └── ...
│   ├── test_api/                      # API endpoint unit tests (mocked service layer)
│   ├── test_core/                     # Core module tests (config, security, logging)
│   ├── test_models/                   # ORM model tests
│   ├── test_schemas/                  # Pydantic schema validation tests
│   └── test_services/                 # Service function tests (mocked sessions)
├── integration/                       # API + DB integration (mocked external deps)
│   ├── test_api/
│   │   ├── conftest.py               # make_test_app(), role-specific client fixtures
│   │   ├── test_election_api.py
│   │   ├── test_auth.py
│   │   └── ...
│   ├── test_cli/
│   └── test_*.py
├── contract/                          # OpenAPI contract compliance
│   ├── test_geocoding_contract.py
│   ├── test_election_contract.py
│   └── ...
└── e2e/                               # Full stack — real PostGIS, real Alembic migrations
    ├── conftest.py                    # session-scoped app, seeded DB, role clients
    └── test_smoke.py                  # 61 smoke tests organized by router class
```

## Test Structure

**Class-per-feature pattern:**
```python
class TestCensusResponseParsing:
    """Tests for Census API response parsing."""

    def setup_method(self) -> None:
        """Create a fresh geocoder instance for each test."""
        self.geocoder = CensusGeocoder()

    def test_successful_match(self) -> None:
        """Successful address match returns GeocodingResult with quality."""
        data = {"result": {"addressMatches": [{"matchedAddress": "...", "coordinates": {"x": -84.388, "y": 33.749}, "tigerLine": {}}]}}
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.latitude == pytest.approx(33.749)
        assert result.quality == GeocodeQuality.EXACT

    def test_no_matches(self) -> None:
        """No matches returns None."""
        data = {"result": {"addressMatches": []}}
        assert self.geocoder._parse_response(data) is None
```

**Rules:**
- One test class per logical unit (one class per schema, service function group, or endpoint)
- Descriptive docstring on every test method explaining the expected behavior (not "test that X", but what X does)
- Return type `-> None` on all test methods
- `setup_method` for class-level state that needs fresh initialization per test (rare — prefer fixtures)

## Mocking

**Framework:** `unittest.mock` (stdlib) — `AsyncMock`, `MagicMock`, `patch`

**Async session mock pattern:**
```python
from unittest.mock import AsyncMock, MagicMock

def _mock_session_with_result(scalar_result: object) -> AsyncMock:
    """Create mock session returning a specific scalar result."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_result
    session.execute.return_value = result
    return session

# For queries returning lists:
session = AsyncMock()
mock_result = MagicMock()
mock_result.scalars.return_value.all.return_value = [item1, item2]
mock_result.scalar_one.return_value = 2  # total count
session.execute.return_value = mock_result
```

**Service layer mock with `patch`:**
```python
with patch("voter_api.services.election_service.get_election_by_id", return_value=election):
    resp = await client.get(f"/api/v1/elections/{election.id}")

# Async service mocks need new_callable=AsyncMock:
with patch(
    "voter_api.services.election_service.preview_feed_import",
    new_callable=AsyncMock,
    return_value=mock_preview,
):
    resp = await admin_client.post("/api/v1/elections/import-feed/preview", json=body)
```

**FastAPI dependency override pattern (integration tests):**
```python
@pytest.fixture
def app(mock_session) -> FastAPI:
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    return app

@pytest.fixture
def admin_app(mock_session, mock_admin_user) -> FastAPI:
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    return app
```

The shared `make_test_app()` helper in `tests/integration/test_api/conftest.py` encapsulates this pattern for reuse.

**What to mock:**
- Database sessions (`AsyncMock`) in all non-E2E tests
- External HTTP calls (geocoders, Mailgun, election feeds)
- Authentication dependencies (`get_current_user`) via `dependency_overrides`
- S3/R2 storage via `moto[s3]`
- Time-sensitive operations via `time-machine`

**What NOT to mock:**
- Pydantic schemas — test real validation behavior
- Custom exception classes — test real exception construction
- Core utility functions (`hash_password`, `create_access_token`)
- Library pure logic (address parsing, analyzers)

## Fixtures and Factories

**Root conftest (`tests/conftest.py`) provides:**
```python
@pytest.fixture
def settings() -> Settings:
    """Minimal settings for in-memory SQLite testing."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-for-production",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
    )

@pytest.fixture
async def async_engine(settings: Settings) -> AsyncGenerator[AsyncEngine]:
    """In-memory SQLite engine — creates tables on entry, drops on exit."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession]:
    """Per-test session (no transaction rollback — tests must clean up or use fresh engine)."""
    ...

@pytest.fixture
def admin_token(settings) -> str:
    return create_access_token(subject="testadmin", role="admin", ...)
```

**Model factory pattern** (underscore-prefixed module-level helpers):
```python
def _make_election(**overrides) -> Election:
    """Build a mock Election with sensible defaults, accepting overrides."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Election",
        "election_date": date(2026, 2, 17),
        "status": "active",
        ...
    }
    defaults.update(overrides)
    election = MagicMock(spec=Election)
    for k, v in defaults.items():
        setattr(election, k, v)
    return election

# Usage: election = _make_election(status="finalized")
```

**Mock user factory:**
```python
def _mock_user(**overrides: object) -> MagicMock:
    """Create a mock User object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "testuser"
    user.role = "admin"
    user.is_active = True
    for key, value in overrides.items():
        setattr(user, key, value)
    return user
```

**Integration test API conftest** (`tests/integration/test_api/conftest.py`) provides:
- `mock_session` fixture (function-scoped `AsyncMock`)
- `mock_admin_user`, `mock_viewer_user` fixtures (function-scoped `MagicMock` with role set)
- `client`, `admin_client`, `viewer_client` — `httpx.AsyncClient` instances via `ASGITransport`
- `make_test_app(router, mock_session, *, user=None)` — helper to create minimal FastAPI apps

## E2E Test Data Seeding

**Pattern:** Session-scoped `seed_database` autouse fixture using PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` for idempotency:
```python
stmt = pg_insert(User).values([{
    "id": ADMIN_ID,
    "username": ADMIN_USERNAME,
    "hashed_password": hash_password(ADMIN_PASSWORD),
    "role": "admin",
    "is_active": True,
}]).on_conflict_do_update(
    index_elements=["id"],
    set_={"username": ADMIN_USERNAME, "role": "admin"},
)
await session.execute(stmt)
```

**Fixed UUIDs:** All seeded rows use deterministic constants (`BOUNDARY_ID`, `ELECTION_ID`, `OFFICIAL_ID`) exported from `tests/e2e/conftest.py` so tests can reference them without querying.

**Cleanup:** `seed_database` fixture deletes seeded rows in reverse-dependency order after the session ends.

## Coverage

**Threshold:** 90% (enforced in CI)

**Commands:**
```bash
uv run pytest --cov=voter_api --cov-report=term-missing   # Terminal report
uv run pytest --cov=voter_api --cov-report=html           # HTML report (htmlcov/)
```

## Test Types

**Unit Tests** (`tests/unit/`):
- No external I/O, no real database connections
- Fast: < 1 second each
- Use in-memory SQLite (`sqlite+aiosqlite:///:memory:`) when ORM is needed
- Mock all external services
- Cover: schemas, lib utilities, service logic (mocked session), core modules

**Integration Tests** (`tests/integration/`):
- FastAPI app wired with `dependency_overrides` for session and auth
- HTTP requests via `httpx.AsyncClient` + `ASGITransport`
- Service layer mocked via `patch`
- Cover: full route behavior, auth/RBAC enforcement, HTTP error codes, response shapes

**Contract Tests** (`tests/contract/`):
- OpenAPI schema compliance
- No real DB — service layer mocked
- Assert response models match documented schemas
- Assert endpoint-level constraints (auth required, correct status codes)

**E2E Tests** (`tests/e2e/`):
- Real PostgreSQL + PostGIS (from `docker compose up -d db`)
- All Alembic migrations applied before tests run
- Session-scoped fixtures: one app, one seeded DB, multiple clients
- 61 smoke tests in `test_smoke.py` organized as `Test<Router>` classes
- CI: `.github/workflows/e2e.yml` — `postgis/postgis:15-3.4` service container

## Common Patterns

**Async test (with `@pytest.mark.asyncio` — still used in many files despite auto mode):**
```python
@pytest.mark.asyncio
async def test_timeout_raises_provider_error(self) -> None:
    """httpx.TimeoutException raises GeocodingProviderError."""
    geocoder = CensusGeocoder(timeout=0.1)
    with (
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        pytest.raises(GeocodingProviderError, match="census") as exc_info,
    ):
        mock_get.side_effect = httpx.TimeoutException("timed out")
        await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    assert exc_info.value.provider_name == "census"
```

**Multiple context managers (Python 3.10+ parenthesized form):**
```python
with (
    patch("voter_api.services.geocoding_service.cache_lookup", new_callable=AsyncMock, return_value=None),
    patch("voter_api.services.geocoding_service.cache_store", new_callable=AsyncMock),
):
    result = await geocode_with_fallback(session, "test addr", [p1, p2])
```

**Error path testing:**
```python
async def test_refresh_502_on_fetch_error(self, admin_client):
    from voter_api.lib.election_tracker import FetchError

    with patch(
        "voter_api.services.election_service.refresh_single_election",
        side_effect=FetchError("Connection failed"),
    ):
        resp = await admin_client.post(f"/api/v1/elections/{uuid.uuid4()}/refresh")
    assert resp.status_code == 502
    assert "retry" in resp.json()["detail"].lower()
```

**Schema validation error testing:**
```python
def test_jwt_secret_key_minimum_length(self, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings()
```

**Parametrized tests:**
```python
@pytest.mark.parametrize("page,page_size,valid", [
    (1, 20, True),
    (0, 20, False),
    (1, 101, False),
])
def test_pagination_params(self, page, page_size, valid) -> None:
    if valid:
        params = PaginationParams(page=page, page_size=page_size)
        assert params.page == page
    else:
        with pytest.raises(ValidationError):
            PaginationParams(page=page, page_size=page_size)
```

**Verifying mock call arguments:**
```python
async def test_list_with_filters(self, client):
    with patch("voter_api.services.election_service.list_elections", return_value=([], 0)) as mock_list:
        resp = await client.get("/api/v1/elections?status=active&page=2")

    assert resp.status_code == 200
    mock_list.assert_awaited_once()
    call_kwargs = mock_list.call_args[1]
    assert call_kwargs["status"] == "active"
    assert call_kwargs["page"] == 2
```

**Concrete subclass mock for abstract base:**
```python
class MockGeocoder(BaseGeocoder):
    """Minimal concrete implementation for testing fallback logic."""

    def __init__(self, name: str, result: GeocodingResult | None = None, error: bool = False) -> None:
        self._name = name
        self._result = result
        self._error = error

    @property
    def provider_name(self) -> str:
        return self._name

    async def geocode(self, address: str) -> GeocodingResult | None:
        if self._error:
            raise GeocodingProviderError(self._name, "Test error")
        return self._result
```

---

*Testing analysis: 2026-03-13*
