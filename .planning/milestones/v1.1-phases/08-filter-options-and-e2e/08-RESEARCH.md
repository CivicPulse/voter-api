# Phase 8: Filter Options and E2E - Research

**Researched:** 2026-03-16
**Domain:** FastAPI endpoint + E2E test infrastructure (SQLAlchemy DISTINCT queries, pytest-asyncio session fixtures)
**Confidence:** HIGH

## Summary

Phase 8 adds a single new endpoint (`GET /api/v1/elections/filter-options`) that queries DISTINCT values from the `elections` table for race categories, counties, and election dates, excluding soft-deleted rows. It also adds comprehensive E2E test coverage for all Phase 6-8 endpoints.

The implementation is straightforward because the project already has an established filter-options pattern (`voter_service.get_voter_filter_options()`), established E2E infrastructure (`tests/e2e/conftest.py` with `seed_database`, fixed UUIDs, and `_make_client()`), and all necessary database columns are already indexed. No new migrations, no new dependencies.

**Primary recommendation:** Follow the voter filter-options pattern exactly (sequential DISTINCT queries, sorted arrays, dict response) but adapt for the election domain. Keep the endpoint public (no auth) with 5-minute Cache-Control. Seed 4-5 elections with diverse `district_type` and `eligible_county` values plus one soft-deleted election for exclusion testing.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Response shape: Simple string arrays: `{"race_categories": [...], "counties": [...], "election_dates": [], "total_elections": 0}`
- Only return values with at least one non-deleted election (no empty dropdown options)
- Election dates sorted descending (newest first)
- Include `total_elections` integer field alongside filter arrays
- Counties title-case normalized regardless of DB storage casing
- Public endpoint (no auth required) -- consistent with /capabilities and elections list
- Cache-Control: public, max-age=300 (5-minute cache)
- Add 4-5 elections covering all race categories: federal (congressional), state_senate, state_house, local (null/other district_type), plus one soft-deleted election
- Soft-deleted election seeded in seed_database (deleted_at set) for exclusion tests
- Also test inline create-then-delete to verify dynamic soft-delete exclusion
- Shared seed data -- new elections visible to all tests; update existing count assertions (>= instead of ==)
- Each seeded election should have district_type and eligible_county populated to exercise Phase 7 filters
- Empty database returns empty arrays with total_elections: 0, HTTP 200
- No 404 for empty results

### Claude's Discretion
- Exact seeded election names, dates, and district values
- Internal query implementation (single query vs multiple)
- Title-case normalization approach (Python str.title() or SQL)
- E2E test organization within TestElections or new test class
- Route registration order (must be before /{election_id} catch-all -- already established pattern from Phase 6)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DISC-02 | API consumer can fetch valid values for race category, county, and election date dropdown filters via a filter-options endpoint | Voter filter-options pattern provides exact blueprint; RACE_CATEGORY_MAP keys provide category list; DISTINCT queries on existing indexed columns |
| INTG-03 | E2E tests cover all new endpoints and filter parameters with seed data that exercises eligible_county and district_type | E2E conftest seed_database fixture pattern documented; TestElections class shows existing test structure; need 4-5 new election seed rows + soft-deleted row |

</phase_requirements>

## Standard Stack

No new libraries required. Everything uses the existing stack.

### Core (Existing)
| Library | Version | Purpose | Already Installed |
|---------|---------|---------|-------------------|
| FastAPI | existing | Route handler + Query params | Yes |
| SQLAlchemy 2.x (async) | existing | DISTINCT queries on Election model | Yes |
| Pydantic v2 | existing | FilterOptionsResponse schema | Yes |
| pytest + pytest-asyncio | existing | E2E test framework | Yes |
| httpx | existing | ASGI test client | Yes |

**Installation:** None required. Zero new dependencies per CONTEXT.md constraints.

## Architecture Patterns

### New Files / Modifications

```
src/voter_api/
├── schemas/election.py        # ADD: FilterOptionsResponse model
├── services/election_service.py  # ADD: get_filter_options() function
└── api/v1/elections.py         # ADD: /filter-options route handler

tests/e2e/
├── conftest.py                 # MODIFY: Add 4-5 election seed rows + 1 soft-deleted + new UUID constants + cleanup
└── test_smoke.py               # MODIFY: Add filter-options tests, capabilities tests, search/filter tests
```

### Pattern 1: Filter Options Service Function

**What:** A service function that runs DISTINCT queries against the Election table, filters out soft-deleted rows, and returns a dict of sorted arrays.

**When to use:** Exactly this endpoint.

**Reference implementation** (from `voter_service.py` lines 192-260):
```python
# The voter filter-options uses sequential DISTINCT queries with _distinct_sorted() helper.
# Election version is simpler (no cascading filters, no county scoping).
# Key differences:
# 1. race_categories derived from RACE_CATEGORY_MAP keys, not raw column values
# 2. counties need title-case normalization
# 3. election_dates sorted descending (newest first)
# 4. Must include total_elections count
# 5. All queries filter WHERE deleted_at IS NULL
```

**Implementation approach:**
```python
async def get_filter_options(session: AsyncSession) -> dict:
    base_filter = Election.deleted_at.is_(None)

    # Race categories: query DISTINCT district_type, map back to category keys
    # Use RACE_CATEGORY_MAP to determine which categories have matching elections
    # Also check for NULL/unrecognized district_type -> "local" category

    # Counties: DISTINCT eligible_county WHERE NOT NULL, title-case normalize
    # Python str.title() is simplest (e.g., "BIBB" -> "Bibb", "DE KALB" -> "De Kalb")

    # Election dates: DISTINCT election_date, sorted DESC

    # Total: COUNT(*) WHERE deleted_at IS NULL
```

### Pattern 2: Route Registration (Before Catch-All)

**What:** The `/filter-options` route MUST be registered before the `/{election_id}` catch-all UUID route.

**When to use:** Any new static path on the elections router.

**Existing pattern** (from `elections.py`):
```python
# Current order in elections.py:
# 1. GET ""              (list)
# 2. GET "/capabilities"  (static path - registered BEFORE /{id})
# 3. POST ""             (create)
# 4. POST "/import-feed/preview"
# 5. POST "/import-feed"
# 6. GET "/{election_id}"  (catch-all)
# ...
```

The `/filter-options` route should be registered after `/capabilities` but before `/{election_id}`.

### Pattern 3: E2E Seed Data (Idempotent Upsert with Fixed UUIDs)

**What:** Session-scoped seed data using `pg_insert().on_conflict_do_update()` with deterministic UUIDs.

**Key details from existing conftest.py:**
- UUID constants defined at module level (e.g., `ELECTION_ID = uuid.UUID("00000000-...")`)
- Insert uses `on_conflict_do_update(index_elements=["id"], set_={...})` for idempotency
- Cleanup block at end of `seed_database` deletes seeded rows in reverse FK order
- Existing election seed: `ELECTION_ID` with `name="E2E Test General Election"`, `election_date=date(2024, 11, 5)`, no `district_type` or `eligible_county` set

**New seed elections need:**
- 4-5 new UUID constants (e.g., `ELECTION_FEDERAL_ID`, `ELECTION_STATE_SENATE_ID`, etc.)
- Each with `district_type` and `eligible_county` populated
- One with `deleted_at` set (soft-deleted) to verify exclusion
- Cleanup deletes for all new election IDs

### Pattern 4: E2E Test Assertions

**What:** Tests use `client` (unauthenticated) for public endpoints, assert on status code + response shape.

**Existing election test pattern** (from `test_smoke.py` TestElections):
```python
async def test_list_elections(self, client: httpx.AsyncClient) -> None:
    resp = await client.get(_url("/elections"))
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert len(body["items"]) >= 1  # Uses >= for shared seed data
```

### Anti-Patterns to Avoid
- **Exact count assertions on shared data:** Use `>=` instead of `==` for counts, since other seeded data or feed imports may add elections
- **Hardcoding category order:** Sort categories alphabetically in the response for deterministic assertions
- **Forgetting cleanup:** Every seeded election UUID must have a matching `DELETE` in the cleanup block
- **Testing auth on public endpoint:** filter-options is public; don't test 401/403 (there should be none)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Race category mapping | Custom mapping logic | `RACE_CATEGORY_MAP.keys()` + reverse lookup | Already defined and tested in Phase 7 |
| Soft-delete filtering | Manual `WHERE deleted_at IS NULL` in route | `Election.deleted_at.is_(None)` pattern used everywhere in election_service | Consistency |
| Title-case normalization | Custom case-conversion | Python `str.title()` | Handles multi-word counties correctly ("DE KALB" -> "De Kalb") |
| E2E client setup | Custom httpx wiring | `_make_client()` helper + existing fixtures | Already handles ASGI transport, auth headers |

## Common Pitfalls

### Pitfall 1: Route Order Collision
**What goes wrong:** `/filter-options` is interpreted as `/{election_id}` with value "filter-options", returning 422 (invalid UUID).
**Why it happens:** FastAPI evaluates routes in registration order; `/{election_id}` is a catch-all UUID path.
**How to avoid:** Register `/filter-options` BEFORE `/{election_id}` in the router. Place it right after `/capabilities`.
**Warning signs:** 422 "invalid UUID" error when hitting `/filter-options`.

### Pitfall 2: Race Category Reverse Mapping
**What goes wrong:** Returning raw `district_type` values instead of user-facing race category names.
**Why it happens:** The DB stores `district_type` (e.g., "congressional", "state_senate"), but the API returns `race_category` (e.g., "federal", "state_senate").
**How to avoid:** Query DISTINCT `district_type`, then map back to category keys using `RACE_CATEGORY_MAP`. For NULL or unrecognized types, map to "local".
**Warning signs:** Response contains "congressional" instead of "federal".

### Pitfall 3: Missing Soft-Delete Filter
**What goes wrong:** Filter options include values from soft-deleted elections, showing stale dropdown options.
**Why it happens:** Forgetting `WHERE deleted_at IS NULL` on filter-options queries.
**How to avoid:** Always include `Election.deleted_at.is_(None)` in every query. The E2E test with a soft-deleted seeded election will catch this.
**Warning signs:** Soft-deleted election's county or date appears in filter options.

### Pitfall 4: E2E Seed Data FK Conflicts
**What goes wrong:** Seed insert fails with unique constraint violation on `uq_election_name_date`.
**Why it happens:** The unique constraint is partial (`WHERE deleted_at IS NULL`), so two active elections with the same name+date collide.
**How to avoid:** Use unique names for each seeded election (include category in name). The soft-deleted election needs a different name anyway.
**Warning signs:** `IntegrityError` during test setup.

### Pitfall 5: Existing Test Count Assertions
**What goes wrong:** Existing tests that assert `len(body["items"]) == 1` fail because new seed elections increase the count.
**Why it happens:** Adding 4-5 new elections to shared `seed_database` increases total count.
**How to avoid:** Update existing assertions to use `>=` instead of `==` where appropriate. Check `TestElections.test_list_elections` and `TestPagination`.
**Warning signs:** Pre-existing election tests fail with count mismatch.

### Pitfall 6: County NULL Values in DISTINCT
**What goes wrong:** `None` appears in the counties list or title-case crashes on None.
**Why it happens:** `eligible_county` is nullable; DISTINCT includes NULL.
**How to avoid:** Filter NULLs in the query: `WHERE eligible_county IS NOT NULL`. The voter filter-options helper uses `filter_nulls=True` for nullable columns.
**Warning signs:** `None` or `AttributeError` on `.title()`.

## Code Examples

### FilterOptionsResponse Schema
```python
# Source: Follows CapabilitiesResponse pattern in schemas/election.py
class FilterOptionsResponse(BaseModel):
    """Valid filter values for election search dropdowns."""
    race_categories: list[str] = Field(default_factory=list)
    counties: list[str] = Field(default_factory=list)
    election_dates: list[date] = Field(default_factory=list)
    total_elections: int = 0
```

### Service Function Pattern
```python
# Source: Adapted from voter_service.get_voter_filter_options() lines 192-260
async def get_filter_options(session: AsyncSession) -> dict:
    base = Election.deleted_at.is_(None)

    # District types -> race categories
    dt_result = await session.execute(
        select(distinct(Election.district_type)).where(base)
    )
    district_types = {row for (row,) in dt_result.all()}

    categories = []
    for cat, types in RACE_CATEGORY_MAP.items():
        if any(t in district_types for t in types):
            categories.append(cat)
    # "local" if NULL or unrecognized types exist
    if None in district_types or (district_types - set(_NON_LOCAL_TYPES)):
        categories.append("local")
    categories.sort()

    # Counties (non-null, title-cased, sorted)
    county_result = await session.execute(
        select(distinct(Election.eligible_county))
        .where(base, Election.eligible_county.isnot(None))
        .order_by(Election.eligible_county)
    )
    counties = [row.title() for (row,) in county_result.all()]

    # Election dates (descending)
    date_result = await session.execute(
        select(distinct(Election.election_date))
        .where(base)
        .order_by(Election.election_date.desc())
    )
    dates = [row for (row,) in date_result.all()]

    # Total count
    count_result = await session.execute(
        select(func.count(Election.id)).where(base)
    )
    total = count_result.scalar_one()

    return {
        "race_categories": categories,
        "counties": counties,
        "election_dates": dates,
        "total_elections": total,
    }
```

### Route Handler Pattern
```python
# Source: Follows /capabilities pattern in api/v1/elections.py line 122
@elections_router.get("/filter-options", response_model=FilterOptionsResponse)
async def get_filter_options(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    response: Response,
) -> FilterOptionsResponse:
    """Return valid filter values for election search dropdowns. Public endpoint."""
    response.headers["Cache-Control"] = "public, max-age=300"
    options = await election_service.get_filter_options(session)
    return FilterOptionsResponse(**options)
```

### E2E Seed Data Pattern
```python
# Source: Follows election seed pattern in conftest.py line 337
# New UUIDs for diverse election seed data
ELECTION_FEDERAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")
ELECTION_STATE_SENATE_ID = uuid.UUID("00000000-0000-0000-0000-000000000012")
ELECTION_STATE_HOUSE_ID = uuid.UUID("00000000-0000-0000-0000-000000000013")
ELECTION_LOCAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000014")
ELECTION_DELETED_ID = uuid.UUID("00000000-0000-0000-0000-000000000015")

# Example seed row with district_type + eligible_county:
{
    "id": ELECTION_FEDERAL_ID,
    "name": "E2E US House District 5",
    "election_date": date(2024, 11, 5),
    "election_type": "general",
    "district": "US House District 5",
    "district_type": "congressional",
    "eligible_county": "FULTON",
    "status": "active",
    "source": "manual",
    "refresh_interval_seconds": 120,
}

# Soft-deleted election (deleted_at set):
{
    "id": ELECTION_DELETED_ID,
    "name": "E2E Deleted Election",
    "election_date": date(2023, 5, 1),
    "election_type": "primary",
    "district": "Statewide",
    "district_type": "congressional",
    "eligible_county": "CHATHAM",
    "status": "active",
    "source": "manual",
    "refresh_interval_seconds": 120,
    "deleted_at": datetime.now(UTC),  # Marks as soft-deleted
}
```

### E2E Test Pattern
```python
# Source: Follows TestElections pattern in test_smoke.py line 603
class TestFilterOptions:
    """GET /api/v1/elections/filter-options -- public, no auth."""

    async def test_filter_options_returns_200(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/elections/filter-options"))
        assert resp.status_code == 200
        body = resp.json()
        assert "race_categories" in body
        assert "counties" in body
        assert "election_dates" in body
        assert "total_elections" in body
        assert isinstance(body["race_categories"], list)
        assert body["total_elections"] >= 1

    async def test_filter_options_excludes_soft_deleted(
        self, admin_client: httpx.AsyncClient, db_session: AsyncSession, client: httpx.AsyncClient
    ) -> None:
        # Create, soft-delete, verify exclusion from filter-options
        ...

    async def test_filter_options_cache_header(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/elections/filter-options"))
        assert resp.headers.get("cache-control") == "public, max-age=300"
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/e2e/ -x -k "filter_options or capabilities or search"` |
| Full suite command | `uv run pytest tests/e2e/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DISC-02 | filter-options returns valid dropdown values | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "filter_options"` | No - Wave 0 |
| DISC-02 | filter-options excludes soft-deleted elections | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "soft_deleted"` | No - Wave 0 |
| DISC-02 | filter-options has 5-min cache header | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "cache"` | No - Wave 0 |
| INTG-03 | capabilities endpoint returns expected shape | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "capabilities"` | No - Wave 0 |
| INTG-03 | election search with q param | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "search"` | No - Wave 0 |
| INTG-03 | election filter by race_category | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "race_category"` | No - Wave 0 |
| INTG-03 | election filter by county | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "county"` | No - Wave 0 |
| INTG-03 | election filter by election_date | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "election_date"` | No - Wave 0 |
| INTG-03 | existing E2E tests still pass | e2e | `uv run pytest tests/e2e/ -v` | Yes |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/e2e/ --collect-only` (verify new tests are discovered)
- **Per wave merge:** `uv run pytest tests/e2e/ -v` (full E2E suite against PostGIS)
- **Phase gate:** Full E2E suite green + `uv run ruff check . && uv run ruff format --check .`

### Wave 0 Gaps
- [ ] New election seed rows in `tests/e2e/conftest.py` (4-5 elections + 1 soft-deleted)
- [ ] New UUID constants exported from conftest
- [ ] Cleanup deletes for new election IDs
- [ ] Update existing count assertions to use `>=` if needed

## Sources

### Primary (HIGH confidence)
- `src/voter_api/services/voter_service.py:192-260` -- existing filter-options pattern (DISTINCT queries, sorted arrays)
- `src/voter_api/services/election_service.py:56-61` -- RACE_CATEGORY_MAP and _NON_LOCAL_TYPES constants
- `src/voter_api/api/v1/elections.py:122-129` -- capabilities endpoint (route ordering, caching pattern)
- `src/voter_api/models/election.py` -- Election model with district_type, eligible_county, deleted_at columns
- `tests/e2e/conftest.py` -- E2E seed data fixtures, UUID constants, cleanup pattern
- `tests/e2e/test_smoke.py` -- TestElections class, assertion patterns

### Secondary (MEDIUM confidence)
- `CLAUDE.md` E2E Tests section -- rules for updating E2E tests when API changes

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing patterns
- Architecture: HIGH -- directly follows established voter filter-options pattern
- Pitfalls: HIGH -- documented from actual codebase patterns and constraints

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable domain, no external dependencies)
