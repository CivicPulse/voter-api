# Coding Conventions

**Analysis Date:** 2026-03-13

## Naming Patterns

**Files:**
- `snake_case` for all module names: `auth_service.py`, `voter_history_service.py`, `boundary_loader.py`
- Test files mirror source with `test_` prefix and directory structure: `tests/unit/lib/test_geocoder/test_cache.py` mirrors `src/voter_api/lib/geocoder/cache.py`
- CLI command modules use `_cmd.py` suffix: `db_cmd.py`, `import_cmd.py`, `officials_cmd.py`

**Functions:**
- `snake_case` for all functions and async functions
- Private helpers prefixed with single underscore: `_build_county_filter()`, `_mock_user()`, `_distinct_sorted()`
- Async functions are not specially named; `async def` is the marker
- FastAPI endpoint functions use `snake_case` with verb prefix: `search_voters_endpoint`, `get_voter`, `set_voter_official_location`

**Variables:**
- `snake_case` for all identifiers
- Module-level constants in `UPPER_SNAKE_CASE`: `VOTER_NOT_FOUND = "Voter not found"`, `BOUNDARY_ID`, `QUALITY_RANK`
- Module-level private constants prefixed with underscore: `_HTTPS_SCHEME`, `_LOG_FORMAT`, `_PROVIDERS`, `_STALE_TASK_NOTE`
- Unused FastAPI dependency parameters prefixed with underscore: `_current_user` (required by DI chain but not used in handler body)

**Types:**
- `PascalCase` for all classes: `Voter`, `GeocodingResult`, `BaseGeocoder`, `PasskeyManager`
- Custom exception classes `PascalCase` with descriptive suffix matching base: `GeocodingProviderError(Exception)`, `OutOfBoundsError(ValueError)`, `DuplicateElectionError(ValueError)`
- Pydantic models use `PascalCase` with semantic suffix: `VoterSummaryResponse`, `PaginationMeta`, `AddressGeocodeResponse`
- SQLAlchemy ORM models use `PascalCase` with no suffix: `Voter`, `Boundary`, `Election`
- Enums use `StrEnum` with `PascalCase` class name, `UPPER_SNAKE_CASE` members: `GeocodeQuality.EXACT`, `GeocodeServiceType.BATCH`

## Code Style

**Formatting:**
- Ruff with line length 120 characters (`pyproject.toml` `[tool.ruff]`)
- Run before every commit: `uv run ruff check .` then `uv run ruff format .`
- Auto-fix: `uv run ruff check . --fix && uv run ruff format .`

**Linting rules selected (from `pyproject.toml`):**
- `E`, `W` — pycodestyle errors/warnings
- `F` — pyflakes (undefined names, unused imports)
- `I` — isort (import ordering)
- `N` — pep8-naming
- `UP` — pyupgrade (modern Python idioms)
- `B` — flake8-bugbear
- `S` — flake8-bandit (security)
- `A` — flake8-builtins
- `C4` — flake8-comprehensions
- `DTZ` — timezone-aware datetimes
- `T20` — no print statements
- `RET` — return value patterns
- `SIM` — simplify
- `TCH` — type-checking imports
- `PTH` — use pathlib

**Per-file ignores:**
- `tests/**/*.py` — `S101` (assert), `S105`, `S106` (test credentials)
- `src/voter_api/api/**/*.py` — `B008` (FastAPI `Depends()` in defaults is idiomatic)
- `src/voter_api/cli/**/*.py` — `B008` (Typer `Argument`/`Option` in defaults is idiomatic)

**Type Checking:**
- mypy 1.14+ with `disallow_untyped_defs = true` and `warn_return_any = true`
- pydantic mypy plugin enabled: `plugins = ["pydantic.mypy"]`
- External packages without stubs declared in `[[tool.mypy.overrides]]`: `geoalchemy2`, `geopandas`, `boto3`, `pandas`, `shapely`

## Import Organization

**Order (enforced by Ruff `I` rule):**
1. `from __future__ import annotations` — only in files with forward references
2. Standard library imports
3. Third-party imports
4. Local `voter_api` imports (absolute, never relative)
5. `if TYPE_CHECKING:` block for forward-reference-only imports

**Path convention:**
- Always absolute imports: `from voter_api.models.user import User`
- Never relative imports (`from . import` is not used anywhere)
- Explicit per-symbol imports, not wildcard: `from voter_api.services.voter_service import search_voters, get_voter_detail`

**`TYPE_CHECKING` pattern (used in 23 source files):**
```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voter_api.core.config import Settings
    from voter_api.schemas.voter import BatchBoundaryCheckResponse
```

Used to break circular imports and avoid runtime cost of importing schema types only needed for annotations.

**Late imports inside functions** are used sparingly to break circular imports at call time:
```python
async def check_batch_boundaries_for_voter(session, voter_id):
    # Import here to avoid circular import at module level
    from voter_api.lib.analyzer.batch_check import VoterNotFoundError, check_batch_boundaries
    from voter_api.schemas.voter import BatchBoundaryCheckResponse, ...
```

## Error Handling

**Strategy:**
- Service layer raises domain-specific exceptions; API layer catches and converts to `HTTPException`
- Service functions return `None` for "not found" cases; API layer converts `None` to `HTTP 404`
- Never raise `HTTPException` from service or library code

**Custom exception pattern:**
```python
class GeocodingProviderError(Exception):
    """Raised when a geocoding provider experiences a transport or service error."""

    def __init__(self, provider_name: str, message: str, status_code: int | None = None) -> None:
        self.provider_name = provider_name
        self.message = message
        self.status_code = status_code
        super().__init__(f"{provider_name}: {message}")
```

**Custom exceptions in the codebase:**
- `src/voter_api/lib/geocoder/base.py` — `GeocodingProviderError(Exception)`
- `src/voter_api/lib/geocoder/point_lookup.py` — `OutOfBoundsError(ValueError)`
- `src/voter_api/lib/analyzer/batch_check.py` — `VoterNotFoundError(Exception)`
- `src/voter_api/lib/mailer/mailer.py` — `MailDeliveryError(RuntimeError)`
- `src/voter_api/lib/election_tracker/fetcher.py` — `FetchError(Exception)`
- `src/voter_api/lib/officials/base.py` — `OfficialsProviderError(Exception)`
- `src/voter_api/services/geocoding_service.py` — `GeocodingJobNotFoundError`, `GeocodingJobTerminalStateError`
- `src/voter_api/services/election_service.py` — `DuplicateElectionError(ValueError)`

**API error conversion pattern:**
```python
try:
    voter = await set_official_location_override(session, voter_id, request.latitude, request.longitude)
except OutOfBoundsError as err:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err)) from err
except ValueError as err:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=VOTER_NOT_FOUND) from err
```

**Error message strings:**
- Defined as module-level constants: `VOTER_NOT_FOUND = "Voter not found"`, not inline strings
- Error messages constructed with variable: `msg = f"Unknown geocoder provider: {provider!r}. Available: {list(_PROVIDERS.keys())}"`; then `raise ValueError(msg)` — never `raise ValueError(f"...")`

## Logging

**Framework:** Loguru (`from loguru import logger` — module-level import)

**Message format:**
```
{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}
```

**Patterns:**
- Use Loguru-style placeholder format: `logger.info("Fetched {} records from {}", len(records), provider_name)`
- Security events use structured key=value format: `logger.warning("security.totp.recovery_code_failed username={username}", username=username)`
- Log levels: `debug` for diagnostics, `info` for milestones, `warning` for recoverable issues, `error` for failures

**Configuration:** `src/voter_api/core/logging.py` — `setup_logging()` called from `lifespan()` in `main.py`. Optional file sink enabled when `LOG_DIR` env var set.

## Comments and Docstrings

**Module-level docstrings:** Required on every `.py` file. First line is a one-sentence summary.

**Class docstrings:** Required on every class.

**Public function docstrings:** Required on all public functions, using Google-style format:
```python
async def search_voters(
    session: AsyncSession,
    *,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Voter], int]:
    """Search voters with multi-parameter filters using AND logic.

    Args:
        session: Database session.
        q: Combined name search query (searches across first_name, last_name, middle_name).
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (voters, total count).
    """
```

**Private function docstrings:** Optional, but used for non-obvious helpers.

**Inline comments:** Used sparingly to explain *why*, not *what*:
```python
# Escape SQL wildcard chars so user input is treated as literal text.
# Without this, "100%" becomes ILIKE '%100%%' and "_mith" matches any
# single character in that position rather than a literal underscore.
word_escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```

## Function Design

**Keyword-only arguments:** Used for optional filter parameters to avoid positional argument ambiguity:
```python
async def search_voters(
    session: AsyncSession,
    *,                          # Everything after * is keyword-only
    q: str | None = None,
    first_name: str | None = None,
    ...
) -> tuple[list[Voter], int]:
```

**FastAPI dependency injection pattern:**
```python
async def search_voters_endpoint(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
    q: str | None = Query(None, description="...", max_length=500),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedVoterResponse:
```

**Return types:**
- Always annotated, including `-> None`
- Service functions return `None` for not-found (not raising)
- Service functions return domain objects or dataclasses, not raw dicts
- Pagination returns `tuple[list[Model], int]` (items, total count)

**Abstract base classes:** Used in `lib/` to define provider interfaces:
```python
class BaseGeocoder(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    async def geocode(self, address: str) -> GeocodingResult | None: ...
```

## Module Design

**Library `__init__.py` exports:** Each `lib/` subpackage has an explicit `__init__.py` with:
1. A module docstring listing the public API
2. All imports from submodules
3. An `__all__` list

Example: `src/voter_api/lib/geocoder/__init__.py` — 287 lines, documents 30+ public symbols.

**Barrel imports:** Consumers import from the package, not internal modules:
```python
# Correct
from voter_api.lib.geocoder import GeocodingResult, BaseGeocoder, get_geocoder

# Acceptable for symbols not re-exported in __init__.py
from voter_api.lib.geocoder.base import GeocodingResult
```

**Service layer:** Functions only, no classes. Each service file is a module of async functions taking `session: AsyncSession` as first parameter:
```python
# src/voter_api/services/voter_service.py
async def search_voters(session: AsyncSession, *, q: str | None = None, ...) -> tuple[list[Voter], int]: ...
async def get_voter_detail(session: AsyncSession, voter_id: uuid.UUID) -> Voter | None: ...
```

**Pydantic schemas:** All schemas use `model_config = {"from_attributes": True}` for ORM model hydration. `BaseModel` subclasses never inherit from ORM models.

**Settings:** Singleton via `get_settings()` factory in `src/voter_api/core/config.py`. All env vars validated on startup via `pydantic-settings`. No inline env reads outside of `Settings`.

---

*Convention analysis: 2026-03-13*
