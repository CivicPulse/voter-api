# Phase 7: Search and Filters - Research

**Researched:** 2026-03-16
**Domain:** FastAPI query parameter filtering, SQLAlchemy ILIKE search, Pydantic Literal validation
**Confidence:** HIGH

## Summary

Phase 7 adds four new query parameters (`q`, `race_category`, `county`, `election_date`) to the existing `GET /api/v1/elections` endpoint. All implementation uses existing stack (FastAPI, SQLAlchemy, Pydantic) with no new dependencies or database changes. The existing `list_elections` service function already uses a dynamic filter chain (`filters: list[ColumnElement[bool]]`) that makes adding new conditions straightforward -- each new filter appends to the same list.

The primary risk is ILIKE wildcard injection (SRCH-02), which requires escaping `%` and `_` characters before building the search pattern. The race category mapping is a pure code concern -- a module-level constant dict in the service layer. All four filters AND together with existing filters per established patterns.

**Primary recommendation:** Implement as four additional filter conditions in `election_service.list_elections()` with corresponding `Query()` params in the route handler, plus a small `escape_ilike_wildcards()` utility function for SRCH-02 compliance.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- `RACE_CATEGORY_MAP` defined as module-level constant in `election_service.py`
- Maps `federal` -> `['congressional']`, `state_senate` -> `['state_senate']`, `state_house` -> `['state_house']`
- `local` implemented as NOT IN (`congressional`, `state_senate`, `state_house`) -- future-proof
- `race_category` query param uses `Literal['federal', 'state_senate', 'state_house', 'local']` type constraint
- FastAPI auto-returns 422 for invalid `race_category` values
- Search (`q`): case-insensitive partial match via ILIKE on `name` OR `district`
- Min 2 chars, max 200 chars for `q` parameter
- SQL wildcards `%` and `_` escaped to literal text via utility function
- `election_date` silently overrides `date_from`/`date_to` when both provided (no 422)
- `q` and `district` AND together when both present
- `county` strips whitespace, case-insensitive exact match via `func.lower()`
- Unknown county values return empty result set (not 422)
- Integration-heavy test strategy with minimal unit tests
- E2E tests deferred to Phase 8

### Claude's Discretion
- Exact placement of new query params in the route handler signature
- Whether to use a helper function for building the q-search OR condition or inline it
- Integration test file organization (new file vs. existing election test file)
- Exact test fixture data (election names, dates, districts)

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SRCH-01 | Free text search across name and district (case-insensitive, partial, min 2 / max 200 chars) | ILIKE with OR condition on `Election.name` and `Election.district`; FastAPI `Query(min_length=2, max_length=200)` handles validation |
| SRCH-02 | Special characters treated as literal text (`%` and `_` escaped) | `escape_ilike_wildcards()` utility replaces `%` -> `\%`, `_` -> `\_`; SQLAlchemy ILIKE with backslash escape |
| FILT-01 | Race category filter mapped to `district_type` values | `RACE_CATEGORY_MAP` constant + `notin_()` for local category |
| FILT-02 | County filter via `eligible_county` (case-insensitive exact match) | `func.lower(Election.eligible_county) == county.strip().lower()` |
| FILT-03 | Exact date filter complementing date range filters | `Election.election_date == election_date`; overrides `date_from`/`date_to` when both present |
| FILT-04 | All new filters combine with existing using AND logic | Append to existing `filters` list; no changes to existing filter logic |
| INTG-02 | Backward compatible -- existing behavior unchanged | All new params default to `None`; existing `district` partial match preserved |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | Query parameter declaration with `Query()` | Already in stack; `Literal` type + `min_length`/`max_length` provide automatic validation |
| SQLAlchemy 2.x | existing | ILIKE, `func.lower()`, `notin_()` filter expressions | Already in stack; all needed filter operations are built-in |
| Pydantic v2 | existing | `Literal` type for race_category validation | Already in stack; provides 422 auto-response for invalid enum values |

### Supporting
No new libraries needed. Zero new dependencies.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ILIKE search | PostgreSQL `tsvector` / `pg_trgm` | Overkill for ~34 elections; ILIKE sufficient, deferred per SRCH-03 |
| `func.lower()` for county | `collation` on column | Would require migration; `func.lower()` achieves same result |

## Architecture Patterns

### Modified Files
```
src/voter_api/
├── api/v1/elections.py          # Add 4 Query() params to list_elections handler
├── services/election_service.py # Add RACE_CATEGORY_MAP + 4 filter conditions + escape utility
└── schemas/election.py          # Optional: RaceCategory type alias
tests/
├── integration/test_api/
│   └── test_election_filters_api.py  # New file: filter integration tests
└── unit/
    └── test_services/
        └── test_election_filters.py  # New file: escape utility + RACE_CATEGORY_MAP unit tests
```

### Pattern 1: Dynamic Filter Chain (existing)
**What:** The `list_elections()` service builds a list of SQLAlchemy filter conditions and applies them with `and_(*filters)`.
**When to use:** Every new filter follows the same pattern -- check if param is not None, append condition to `filters` list.
**Example:**
```python
# Existing pattern at election_service.py line 619-644
filters: list[ColumnElement[bool]] = [Election.deleted_at.is_(None)]
if status:
    filters.append(Election.status == status)
# ... new filters follow the same pattern
if q:
    escaped = escape_ilike_wildcards(q)
    pattern = f"%{escaped}%"
    filters.append(or_(Election.name.ilike(pattern), Election.district.ilike(pattern)))
```

### Pattern 2: Race Category NOT IN for "local"
**What:** The `local` category is defined as "everything NOT in the known state/federal types" -- future-proof against new district types.
**Example:**
```python
RACE_CATEGORY_MAP: dict[str, list[str]] = {
    "federal": ["congressional"],
    "state_senate": ["state_senate"],
    "state_house": ["state_house"],
}
_NON_LOCAL_TYPES = [t for types in RACE_CATEGORY_MAP.values() for t in types]

# In list_elections:
if race_category == "local":
    filters.append(Election.district_type.notin_(_NON_LOCAL_TYPES))
else:
    filters.append(Election.district_type.in_(RACE_CATEGORY_MAP[race_category]))
```

### Pattern 3: election_date Overrides date_from/date_to
**What:** When `election_date` is provided, it takes precedence over range filters.
**Example:**
```python
if election_date:
    filters.append(Election.election_date == election_date)
else:
    if date_from:
        filters.append(Election.election_date >= date_from)
    if date_to:
        filters.append(Election.election_date <= date_to)
```

### Anti-Patterns to Avoid
- **Using raw string interpolation in ILIKE:** Never do `f"%{user_input}%"` without escaping `%` and `_` first -- this is the SRCH-02 requirement
- **Raising 422 for unknown county:** Decision is to return empty result set, not error
- **Modifying existing `district` filter behavior:** Must remain partial match (ILIKE), not exact

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Enum validation for race_category | Custom validator | `Literal['federal', 'state_senate', 'state_house', 'local']` in Query param | FastAPI generates 422 automatically with proper error detail |
| Date format validation | Custom date parser | `date` type annotation on Query param | FastAPI/Pydantic handle ISO 8601 parsing and 422 for invalid formats |
| String length validation for q | Custom length check | `Query(min_length=2, max_length=200)` | FastAPI generates 422 with proper validation error |

## Common Pitfalls

### Pitfall 1: ILIKE Wildcard Injection
**What goes wrong:** User searches for `100%` or `District_1` and `%`/`_` are treated as SQL wildcards, matching unintended results.
**Why it happens:** ILIKE treats `%` as "any characters" and `_` as "any single character".
**How to avoid:** Escape before building pattern: replace `\` -> `\\`, `%` -> `\%`, `_` -> `\_` (backslash first to avoid double-escaping).
**Warning signs:** Search for literal `%` or `_` returns more results than expected.

### Pitfall 2: Backslash Escape Order
**What goes wrong:** If you escape `%` and `_` before escaping `\`, the backslashes you just added get double-escaped.
**Why it happens:** Order of replacement matters.
**How to avoid:** Always escape `\` first, then `%`, then `_`.

### Pitfall 3: Race Category with NULL district_type
**What goes wrong:** Elections with `district_type = NULL` don't match any category including `local`.
**Why it happens:** `NULL NOT IN (...)` evaluates to `NULL` (falsy) in SQL, not `TRUE`.
**How to avoid:** For `local` category, use `or_(Election.district_type.notin_(_NON_LOCAL_TYPES), Election.district_type.is_(None))` to include NULL district_type elections in the local bucket.

### Pitfall 4: election_date and date_from/date_to Interaction
**What goes wrong:** If implemented naively, `election_date` and `date_from`/`date_to` could create contradictory WHERE clauses (e.g., `election_date = 2026-01-01 AND election_date >= 2026-06-01`).
**How to avoid:** Use if/else structure so `election_date` prevents `date_from`/`date_to` from being applied.

### Pitfall 5: County Whitespace
**What goes wrong:** Frontend sends `"Bibb "` (trailing space) which doesn't match `"Bibb"`.
**How to avoid:** Strip whitespace before comparison: `county.strip()`.

## Code Examples

### ILIKE Wildcard Escape Utility
```python
def escape_ilike_wildcards(value: str) -> str:
    """Escape SQL ILIKE wildcard characters for literal matching.

    Escapes %, _, and \\ so they are treated as literal characters
    in ILIKE patterns.

    Args:
        value: Raw search input string.

    Returns:
        Escaped string safe for ILIKE pattern use.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```

### Route Handler Signature Addition
```python
@elections_router.get("", response_model=PaginatedElectionListResponse)
async def list_elections(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    # ... existing params ...
    q: str | None = Query(
        default=None,
        min_length=2,
        max_length=200,
        description="Search elections by name or district (case-insensitive partial match)",
    ),
    race_category: Literal["federal", "state_senate", "state_house", "local"] | None = Query(
        default=None,
        description="Filter by race category",
    ),
    county: str | None = Query(
        default=None,
        description="Filter by eligible county (case-insensitive exact match)",
    ),
    election_date: date | None = Query(
        default=None,
        description="Filter by exact election date (YYYY-MM-DD)",
    ),
    # ... existing pagination params ...
) -> PaginatedElectionListResponse:
```

### Service Layer Filter Additions
```python
from sqlalchemy import or_

# In list_elections(), after existing filters:
if q:
    escaped = escape_ilike_wildcards(q)
    pattern = f"%{escaped}%"
    filters.append(
        or_(Election.name.ilike(pattern), Election.district.ilike(pattern))
    )

if race_category:
    if race_category == "local":
        filters.append(
            or_(
                Election.district_type.notin_(_NON_LOCAL_TYPES),
                Election.district_type.is_(None),
            )
        )
    else:
        filters.append(Election.district_type.in_(RACE_CATEGORY_MAP[race_category]))

if county:
    filters.append(func.lower(Election.eligible_county) == county.strip().lower())

# election_date overrides date_from/date_to
if election_date:
    filters.append(Election.election_date == election_date)
else:
    if date_from:
        filters.append(Election.election_date >= date_from)
    if date_to:
        filters.append(Election.election_date <= date_to)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw `%` interpolation in ILIKE | Escape wildcards before pattern building | Always was best practice | Prevents wildcard injection |
| Separate search endpoint | Query params on existing list endpoint | This phase decision | Simpler API surface |

## Open Questions

1. **NULL district_type handling in local category**
   - What we know: Some elections may have `district_type = NULL` (e.g., older data without district parsing)
   - What's unclear: Whether NULL elections should appear under `local` or be excluded entirely
   - Recommendation: Include NULLs in `local` (use `or_(...notin_(...), ...is_(None))`) per the "future-proof" intent of the local category

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (auto mode) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest --cov=voter_api --cov-report=term-missing` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SRCH-01 | q search returns matching elections (name OR district, case-insensitive) | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "test_q"` | No - Wave 0 |
| SRCH-02 | Wildcard chars `%` `_` treated as literals | unit + integration | `uv run pytest tests/unit/test_services/test_election_filters.py -x -k "escape"` | No - Wave 0 |
| FILT-01 | race_category maps to district_type; invalid values return 422 | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "race_category"` | No - Wave 0 |
| FILT-02 | county filter case-insensitive exact match on eligible_county | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "county"` | No - Wave 0 |
| FILT-03 | election_date exact match, overrides date_from/date_to | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "election_date"` | No - Wave 0 |
| FILT-04 | All filters combine with AND logic | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "combined"` | No - Wave 0 |
| INTG-02 | Existing behavior unchanged (backward compat) | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "backward"` | No - Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ tests/integration/test_api/test_election_filters_api.py -x -q`
- **Per wave merge:** `uv run pytest --cov=voter_api --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_services/test_election_filters.py` -- covers SRCH-02 (escape utility), FILT-01 (RACE_CATEGORY_MAP validation)
- [ ] `tests/integration/test_api/test_election_filters_api.py` -- covers SRCH-01, SRCH-02, FILT-01, FILT-02, FILT-03, FILT-04, INTG-02

## Sources

### Primary (HIGH confidence)
- `src/voter_api/services/election_service.py` lines 581-654 -- existing `list_elections()` filter chain pattern
- `src/voter_api/api/v1/elections.py` lines 51-93 -- existing route handler signature
- `src/voter_api/models/election.py` -- Election model with column definitions and indexes
- `docs/election-search-api-report.md` -- canonical contract document for filter behavior

### Secondary (MEDIUM confidence)
- `tests/integration/test_api/test_capabilities_api.py` -- established integration test pattern for elections router
- `tests/integration/test_api/conftest.py` -- shared test fixtures and `make_test_app()` helper

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all existing stack
- Architecture: HIGH -- follows established filter chain pattern exactly
- Pitfalls: HIGH -- ILIKE escaping is well-documented; NULL handling is the one edge case to verify

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable -- no external dependencies or moving targets)
