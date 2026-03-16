# Architecture Patterns

**Domain:** Election search/filter API integration
**Researched:** 2026-03-16

## Recommended Architecture

Extend the existing elections vertical (router, service, schemas) rather than creating new components. The current codebase already has the exact patterns needed -- the `list_elections` filter builder, Pydantic schemas for request/response, and the router-service-model layering. The new features slot cleanly into these patterns with zero new files, zero migrations, and zero new dependencies.

### Integration Strategy: Modify Existing + Two New Endpoints

**Modify existing:**
- `election_service.list_elections()` -- add `q`, `race_category`, `county`, `election_date` filter params
- `elections_router.list_elections()` -- add corresponding Query params
- `schemas/election.py` -- add race category mapping constant, new response schemas

**Add new (same router):**
- `GET /elections/capabilities` -- static JSON, no DB call
- `GET /elections/filter-options` -- three aggregation queries

### Component Boundaries

| Component | Responsibility | What Changes |
|-----------|---------------|--------------|
| `api/v1/elections.py` (router) | HTTP param binding, response shaping | Add 3 Query params to `list_elections`, add 2 new endpoint functions |
| `services/election_service.py` | Filter building, DB queries | Add filter logic in `list_elections`, add `get_filter_options()` function |
| `schemas/election.py` | Pydantic models | Add `CapabilitiesResponse`, `FilterOptionsResponse`, race category map |
| `models/election.py` | ORM model | No changes -- all needed columns exist (`district_type`, `eligible_county`, `election_date`, `name`, `district`) |
| No new files | -- | Everything fits in existing files |

### Data Flow

**Search/filter request (modified `GET /elections`):**
```
Client request with ?q=sheriff&county=Bibb&race_category=county
    |
    v
elections_router.list_elections()
    - FastAPI binds q, race_category, county, election_date as Query params
    - Passes through to service
    |
    v
election_service.list_elections()
    - Existing filter builder pattern: list[ColumnElement[bool]]
    - q: OR(Election.name.ilike(%q%), Election.district.ilike(%q%))
    - race_category: map to district_type values, use .in_() clause
    - county: Election.eligible_county == county
    - election_date: Election.election_date == election_date
    - Applies via and_(*filters) (same as today)
    |
    v
Same pagination, same response schema (ElectionSummary unchanged)
```

**Capabilities endpoint (new `GET /elections/capabilities`):**
```
Client request
    |
    v
elections_router.get_capabilities()
    - Returns hardcoded CapabilitiesResponse (no service call, no DB)
    - Lists available filters, search fields, sort options
    |
    v
Static JSON response
```

**Filter options endpoint (new `GET /elections/filter-options`):**
```
Client request
    |
    v
elections_router.get_filter_options()
    - Calls election_service.get_filter_options(session)
    |
    v
election_service.get_filter_options()
    - 3 sequential queries (DISTINCT on indexed columns):
      1. SELECT DISTINCT district_type FROM elections WHERE deleted_at IS NULL AND district_type IS NOT NULL
      2. SELECT DISTINCT eligible_county FROM elections WHERE deleted_at IS NULL AND eligible_county IS NOT NULL
      3. SELECT DISTINCT election_date FROM elections WHERE deleted_at IS NULL ORDER BY election_date DESC
    - Maps district_type values back to race_category labels
    |
    v
FilterOptionsResponse with race_categories[], counties[], election_dates[]
```

## Patterns to Follow

### Pattern 1: Filter Builder (Existing -- Extend It)

The `list_elections` function (line 581 of `election_service.py`) already uses a filter builder pattern. Each filter is conditionally appended to a `list[ColumnElement[bool]]`, then combined with `and_(*filters)`. New filters are just more entries in the same list.

**What:** Build a list of SQLAlchemy filter expressions, apply them all at once.
**When:** Any list endpoint with optional filters.
**Why this works here:** New filters (q, race_category, county, election_date) are just more entries in the same list. No structural change needed.

**Example (adding text search):**
```python
from sqlalchemy import or_

# In election_service.list_elections(), after existing filters:
if q:
    search_term = f"%{q}%"
    filters.append(
        or_(
            Election.name.ilike(search_term),
            Election.district.ilike(search_term),
        )
    )
```

**Example (adding race category with mapping):**
```python
# Race category maps to one or more district_type values
RACE_CATEGORY_MAP: dict[str, list[str]] = {
    "federal": ["us_house", "us_senate"],
    "statewide": ["statewide"],
    "state_legislative": ["state_senate", "state_house"],
    "county": ["county_commission", "county"],
    "municipal": ["municipal", "city_council"],
    "judicial": ["superior_court", "state_court", "magistrate_court", "probate_court"],
    "school_board": ["school_board"],
    "special_district": ["special_district"],
}

if race_category:
    district_types = RACE_CATEGORY_MAP.get(race_category, [])
    if district_types:
        filters.append(Election.district_type.in_(district_types))
    else:
        # Unknown category -- return empty results rather than silently ignoring
        filters.append(sqlalchemy.false())
```

### Pattern 2: Route Ordering (FastAPI Requirement -- Critical)

FastAPI matches routes in declaration order. The new static endpoints MUST be declared before the `/{election_id}` path parameter routes, or FastAPI will try to parse "capabilities" and "filter-options" as UUIDs and return 422.

**What:** Declare path-parameter-free routes before parameterized routes.
**When:** Adding new endpoints to an existing router with `/{id}` patterns.

**Current route order in elections.py:**
```python
# Line 50:  GET ""                  (list_elections)
# Line 98:  POST ""                 (create_election)
# Line 125: POST "/import-feed/preview"
# Line 146: POST "/import-feed"
# Line 171: GET "/{election_id}"    <-- everything after here uses path params
# Line 186: PATCH "/{election_id}"
# ...
```

**Required insertion point:** Between `POST /import-feed` and `GET /{election_id}`:
```python
# After import-feed endpoints, before /{election_id} routes:
@elections_router.get("/capabilities")
async def get_capabilities(): ...

@elections_router.get("/filter-options")
async def get_filter_options(): ...
```

### Pattern 3: Capabilities as Progressive Discovery

**What:** A static endpoint that tells the frontend what search/filter features are available.
**When:** API evolves incrementally; frontend needs to know what to render.
**Why:** Decouples frontend feature flags from API version numbers. Frontend reads capabilities, enables UI accordingly. When v1.2 adds more filters, the capabilities response grows -- no frontend deploy needed.

**Example schema:**
```python
class SearchCapability(BaseModel):
    enabled: bool = True
    fields: list[str]       # ["name", "district"]
    min_length: int = 2

class FilterCapability(BaseModel):
    name: str               # "race_category"
    type: str               # "select", "date", "text"
    options_endpoint: str | None  # "/api/v1/elections/filter-options"

class CapabilitiesResponse(BaseModel):
    version: str            # "1.1"
    search: SearchCapability
    filters: list[FilterCapability]
```

### Pattern 4: Sequential Aggregation Queries (NOT asyncio.gather)

The filter-options endpoint needs 3 aggregation queries. These MUST run sequentially on the same session.

**What:** Run independent DB queries sequentially on the same AsyncSession.
**When:** Multiple queries needed within a single request.
**Why:** SQLAlchemy `AsyncSession` is NOT safe for concurrent queries. `asyncio.gather` with the same session raises `MissingGreenlet` or produces undefined behavior. The codebase already uses sequential queries in other services.

**Example:**
```python
async def get_filter_options(session: AsyncSession) -> FilterOptionsResponse:
    # Sequential -- same session, each completes before next starts
    race_result = await session.execute(
        select(func.distinct(Election.district_type)).where(
            Election.deleted_at.is_(None), Election.district_type.is_not(None)
        )
    )
    county_result = await session.execute(
        select(func.distinct(Election.eligible_county)).where(
            Election.deleted_at.is_(None), Election.eligible_county.is_not(None)
        ).order_by(Election.eligible_county)
    )
    date_result = await session.execute(
        select(func.distinct(Election.election_date)).where(
            Election.deleted_at.is_(None)
        ).order_by(Election.election_date.desc())
    )
    # Map district_types back to race categories...
```

**Performance note:** These are trivial queries (DISTINCT on indexed columns, ~34 rows total). Sequential execution adds microseconds of overhead. Not worth the complexity of separate sessions.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Creating a New Service File
**What:** Making a separate `election_search_service.py`.
**Why bad:** Splits election query logic across two files. The existing `election_service.py` already owns list/filter queries. A second file creates confusion about which service to call and where to add the next filter.
**Instead:** Add new functions and filter params directly to `election_service.py`.

### Anti-Pattern 2: Full-Text Search (pg_trgm / tsvector)
**What:** Adding PostgreSQL full-text search indexes for the `q` parameter.
**Why bad:** Overkill for searching across ~34 elections (current dataset). ILIKE with OR on two columns is perfectly adequate. Full-text search adds migration complexity, index maintenance, and configuration for zero measurable benefit at this scale.
**Instead:** Use `ILIKE` with `OR` on `name` and `district`. Revisit if election count exceeds 10,000.

### Anti-Pattern 3: Putting Race Category Mapping in the Database
**What:** Creating a lookup table or enum for race categories.
**Why bad:** The mapping is a presentation concern (frontend categories to backend `district_type` values). It changes when the frontend changes, not when the data changes. A DB table adds migration complexity for what is a static dictionary.
**Instead:** Define `RACE_CATEGORY_MAP` as a Python dict constant in `schemas/election.py`. The capabilities endpoint exposes available categories; the service uses the map for filtering.

### Anti-Pattern 4: Scoped Filter Options on First Pass
**What:** Making filter-options respond differently based on other active filters (e.g., counties available for a given race_category).
**Why bad:** Combinatorial query complexity. Each filter option would need to consider all other active filters. The PROJECT.md explicitly defers this: "Scoped options add combinatorial query complexity; fast-follow if needed."
**Instead:** Return all distinct values unscoped. Frontend can do client-side filtering of dropdown options if needed.

### Anti-Pattern 5: New Alembic Migration
**What:** Adding database indexes or columns for search features.
**Why bad:** Every column needed already exists with indexes:
- `district_type` -- `idx_elections_district_type`
- `eligible_county` -- `idx_elections_eligible_county`
- `election_date` -- `idx_elections_election_date`
- `name` -- part of `uq_election_name_date` unique index
- `district` -- no index, but ILIKE on ~34 rows does not need one
**Instead:** Use existing indexed columns directly. Zero migration overhead.

## Detailed Change Map

### File: `src/voter_api/schemas/election.py`

**New additions:**
1. `RACE_CATEGORY_MAP` -- dict[str, list[str]] mapping frontend categories to `district_type` values
2. `SearchCapability`, `FilterCapability` -- nested models for capabilities response
3. `CapabilitiesResponse` -- response model for `GET /capabilities`
4. `RaceCategoryOption` -- model with `name` and `label` for filter options
5. `FilterOptionsResponse` -- response model for `GET /filter-options` with `race_categories`, `counties`, `election_dates`

**No modifications** to existing schemas. `ElectionSummary` and `PaginatedElectionListResponse` are unchanged.

### File: `src/voter_api/api/v1/elections.py`

**New endpoints (insert between import-feed and /{election_id} routes):**
1. `get_capabilities()` -- returns static `CapabilitiesResponse`, no auth required, no DB call
2. `get_filter_options(session)` -- calls service, returns `FilterOptionsResponse`, no auth required

**Modified endpoint:**
1. `list_elections()` -- add 4 new Query params: `q`, `race_category`, `county`, `election_date`

### File: `src/voter_api/services/election_service.py`

**New function:**
1. `get_filter_options(session) -> FilterOptionsResponse` -- 3 aggregation queries, reverse-maps district_types to categories

**Modified function:**
1. `list_elections()` -- add 4 new keyword params (`q`, `race_category`, `county`, `election_date`), add filter logic for each in the existing filter builder

### File: `tests/e2e/test_smoke.py`

**New tests in `TestElections` class:**
1. `test_capabilities_endpoint` -- GET /elections/capabilities returns 200, check structure
2. `test_filter_options_endpoint` -- GET /elections/filter-options returns 200 with expected keys
3. `test_search_by_q` -- GET /elections?q=... returns filtered results
4. `test_filter_by_race_category` -- GET /elections?race_category=... works
5. `test_filter_by_county` -- GET /elections?county=... works
6. `test_filter_by_election_date` -- GET /elections?election_date=... works

May need to extend `seed_database` in `conftest.py` to add an election with `eligible_county` and `district_type` populated for meaningful filter tests.

### Files NOT Changed
- `models/election.py` -- all columns and indexes already exist
- No Alembic migration needed
- No new service/library/CLI files
- `core/`, `cli/`, `lib/` -- untouched

## Build Order

The build order is driven by dependencies between the new features and testing practicality.

### Phase 1: Capabilities Endpoint (no dependencies)
**Why first:** Zero risk, zero DB interaction, establishes the progressive discovery pattern. Can be built and tested in isolation. Unblocks frontend development immediately (frontend reads capabilities to know what filters to render).

**Components:**
1. Schema: `CapabilitiesResponse` and nested models in `schemas/election.py`
2. Router: `get_capabilities()` endpoint in `api/v1/elections.py`
3. Test: E2E smoke test

**Estimated effort:** Small -- static response, no business logic.

### Phase 2: Text Search + Filter Extensions (depends on nothing new)
**Why second:** Modifies existing code paths. The `list_elections` filter builder is the foundation -- extend it with all new filter params at once. Text search (`q`) is the most impactful user-facing feature.

**Components:**
1. Schema: `RACE_CATEGORY_MAP` constant in `schemas/election.py`
2. Service: Add `q`, `race_category`, `county`, `election_date` params to `list_elections()` in `election_service.py`
3. Router: Add 4 new Query params to `list_elections()` handler in `elections.py`
4. Tests: E2E tests for each new filter; possibly extend seed data

**Build sub-order within Phase 2:**
1. `q` text search (ILIKE OR on name + district) -- most valuable, simplest
2. `election_date` exact match -- trivial addition to filter list
3. `county` filter on `eligible_county` -- trivial exact match
4. `race_category` filter -- needs the mapping dict, `IN()` clause

**Estimated effort:** Medium -- 4 filter additions to existing pattern, plus mapping dict.

### Phase 3: Filter Options Endpoint (depends on Phase 2 mapping)
**Why last:** Uses `RACE_CATEGORY_MAP` from Phase 2 to reverse-map `district_type` values back to frontend categories. Logically the "discovery" endpoint that tells the frontend what filter values currently exist in the data.

**Components:**
1. Schema: `FilterOptionsResponse` and nested models in `schemas/election.py`
2. Service: `get_filter_options()` function in `election_service.py`
3. Router: `get_filter_options()` endpoint in `elections.py`
4. Test: E2E smoke test

**Estimated effort:** Medium -- 3 aggregation queries plus reverse mapping logic.

## Scalability Considerations

| Concern | Current (34 elections) | At 1K elections | At 10K elections |
|---------|----------------------|-----------------|------------------|
| ILIKE search | Instant | Fine (small table) | Consider pg_trgm GIN index |
| Filter options (DISTINCT) | Instant | Fine (indexed cols) | Consider caching or materialized view |
| Race category IN() | Instant | Fine | Fine (small IN list, indexed col) |
| County filter | Instant | Fine (indexed) | Fine (indexed) |
| Combined filters | Instant | Fine (AND of indexed filters) | Monitor query plans |

**Bottom line:** No performance work needed until election count grows by 2-3 orders of magnitude. Current indexes cover all filter columns. The architecture supports easy evolution -- add pg_trgm index later with a migration, no code changes needed.

## Sources

- Direct code inspection: `election_service.py` lines 581-660 (filter builder pattern), `elections.py` (route ordering), `election.py` model (existing columns and indexes), `election.py` schemas (response models)
- SQLAlchemy 2.x async documentation: AsyncSession is not concurrency-safe (no asyncio.gather on same session)
- FastAPI documentation: route declaration order determines matching priority
- Existing project conventions: `CLAUDE.md` architecture section, library-first pattern
- `PROJECT.md`: explicit decisions on race_category mapping, unscoped filter options, county filter without statewide inclusion

---

*Architecture research for v1.1 Election Search: 2026-03-16*
