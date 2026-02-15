# Election Result Tracking Feature — Research & Design Decisions

**Feature ID**: 004-election-tracking
**Date**: 2026-02-14
**Project**: voter-api (Python/FastAPI/PostgreSQL+PostGIS)

---

## 1. SoS Data Feed Format Analysis

### Decision
Store election results using a **hybrid relational + JSONB model**:
- **Elections table**: Core metadata (election name, date, created timestamp, status)
- **County results table**: County-level aggregations for efficient GeoJSON joins, stored as JSONB
- Preserve full SoS JSON feed as JSONB for fidelity (FR-006 requirement)

### Structure Overview

The SoS feed at `https://results.sos.ga.gov/cdn/results/Georgia/export-{ElectionName}.json` follows this structure:

```json
{
  "electionDate": "2026-02-17",
  "electionName": "February 17, 2026 Special Election State Senate District 18",
  "createdAt": "2026-02-09T17:40:56.3075579Z",  // ISO 8601 with nanoseconds
  "results": {
    "id": "09378a07-e6cf-4f66-be7c-ca4aa534f99a",
    "name": "Georgia",
    "ballotItems": [/* statewide aggregations */]
  },
  "localResults": [
    {
      "id": "c9278aa5-acbe-47b6-97ab-082132264144",
      "name": "Houston County",  // Format: "{Name} County"
      "ballotItems": [
        {
          "id": "SSD18",
          "name": "State Senate - District 18",
          "precinctsParticipating": 7,    // Non-null for county results
          "precinctsReporting": 0,        // Non-null for county results
          "ballotOptions": [
            {
              "id": "2",
              "name": "LeMario Nicholas Brown (Dem)",
              "voteCount": 0,
              "politicalParty": "Dem",
              "groupResults": [/* vote method breakdown */],
              "precinctResults": [
                {
                  "id": "ANNX",
                  "name": "ANNX",
                  "isVirtual": false,
                  "voteCount": 0,
                  "reportingStatus": "Not Reported",
                  "groupResults": [/* vote method breakdown */]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

### Key Observations

1. **Nullability patterns**:
   - `results.ballotItems[].precinctsParticipating` and `precinctsReporting`: **null** (statewide rollup has no precinct counts)
   - `localResults[].ballotItems[].precinctsParticipating` and `precinctsReporting`: **non-null integers**

2. **Hierarchical nesting**:
   - Election → LocalResults (counties) → BallotItems (contests) → BallotOptions (candidates) → PrecinctResults
   - Each level has `groupResults` (vote method breakdown: Election Day, Advance, Absentee, Provisional)

3. **Timestamp format**: `createdAt` uses ISO 8601 with nanosecond precision (`.3075579Z`). Python's `datetime.fromisoformat()` handles this natively as of 3.11+.

4. **County name format**: `localResults[].name` uses `"{Name} County"` (e.g., "Houston County")

### Rationale

- **JSONB for feed fidelity**: The SoS feed is deeply nested (4+ levels). Normalizing into relational tables would require 6+ tables (elections, contests, candidates, vote_methods, precincts, etc.) for marginal query benefits. JSONB preserves the structure exactly as received, satisfying FR-006 (complete data retention) and simplifying ingestion.

- **Separate county results table**: Extract county-level aggregations into a dedicated table with foreign keys to `elections` and `boundaries` (via county name match). This enables efficient GeoJSON joins without unpacking JSONB in PostGIS spatial queries.

- **Election status tracking**: Add a computed `status` field (`active`, `closed_polls`, `finalized`) based on election date, current time, and manual finalization flag. This drives Cache-Control headers (FR-017).

### Alternatives Considered

1. **Fully normalized relational schema**:
   - **Pros**: Standard SQL queries, type safety, granular indexing
   - **Cons**: 6+ tables, complex migrations when SoS changes schema, lossy representation (e.g., nested properties), difficult to preserve exact feed structure for FR-006
   - **Rejected**: Over-engineered for read-heavy API with stable feed structure

2. **Pure JSONB (single table)**:
   - **Pros**: Ultimate flexibility, zero schema coupling
   - **Cons**: Cannot efficiently join with boundaries table for GeoJSON without JSONB unpacking in SQL; no relational integrity; difficult to query by election date
   - **Rejected**: Sacrifices GeoJSON performance and relational guarantees

3. **Separate tables for each SoS feed URL** (one table per election):
   - **Pros**: Simple ingestion (INSERT without upsert logic)
   - **Cons**: Unmaintainable (unbounded table growth), violates database normalization
   - **Rejected**: Architectural anti-pattern

---

## 2. County Name Matching Strategy

### Decision
**Strip " County" suffix from `localResults[].name` and match against `county_metadata.name`** using case-insensitive comparison.

### Research Findings

The existing database schema has two potential join points:

1. **`boundaries` table** (`boundary_type='county'`):
   - `name` field: May vary by source shapefile (e.g., "Houston County" vs "Houston")
   - `boundary_identifier`: FIPS GEOID (5-digit string)
   - `county` field: NULL for county-type boundaries (self-reference not populated)

2. **`county_metadata` table**:
   - `name` field: Short form **without "County" suffix** (e.g., "Houston")
   - `geoid` field: FIPS GEOID (5-digit string, e.g., "13153")
   - `name_lsad` field: Full legal name (e.g., "Houston County")
   - Join to `boundaries` via `boundaries.boundary_identifier = county_metadata.geoid` (when `boundary_type='county'`)

### Matching Algorithm

```python
def normalize_county_name(sos_name: str) -> str:
    """Convert 'Houston County' -> 'Houston'."""
    return sos_name.removesuffix(" County").strip()

# SQL join condition (case-insensitive)
# FROM elections e
# JOIN county_results cr ON cr.election_id = e.id
# JOIN county_metadata cm ON UPPER(cr.county_name) = UPPER(cm.name)
# JOIN boundaries b ON b.boundary_identifier = cm.geoid AND b.boundary_type = 'county'
```

### Rationale

- **`county_metadata.name` is canonical**: This table is populated from Census TIGER/Line shapefiles, which use standardized short-form names. The `name_lsad` field contains the long form if needed.

- **Avoid FIPS code lookups**: The SoS feed does not include FIPS codes. Reverse-engineering county name → FIPS would require an external lookup table or hardcoded map. Direct name matching is simpler and equally reliable (Georgia has 159 counties with unique names).

- **Case-insensitive comparison**: Handles minor formatting inconsistencies (e.g., "HOUSTON COUNTY" vs "Houston County").

- **Two-hop join for GeoJSON**: `county_results` → `county_metadata` (by name) → `boundaries` (by GEOID). This leverages existing database relationships without duplicating geometry in the results table.

### Alternatives Considered

1. **Match `boundaries.name` directly**:
   - **Pros**: One less join
   - **Cons**: `boundaries.name` format depends on shapefile source (inconsistent); no guarantee of "Houston County" vs "Houston"
   - **Rejected**: Unreliable without data audit

2. **Store FIPS code in SoS feed**:
   - **Pros**: Authoritative join key
   - **Cons**: SoS feed does not include FIPS; cannot modify upstream data
   - **Rejected**: Infeasible

3. **Hardcoded county name → FIPS map**:
   - **Pros**: Explicit mapping
   - **Cons**: Maintenance burden (159 counties); fragile if SoS changes county name spelling
   - **Rejected**: Over-engineered

### Edge Cases

- **Missing county in `county_metadata`**: Should not occur for GA counties (all 159 are in TIGER/Line data), but ingestion will log a warning and skip the county result if missing.
- **Typos in SoS feed**: Manual correction via database UPDATE if detected.

---

## 3. Background Task / Periodic Refresh Strategy

### Decision
Implement a **dual-mode refresh system**:
1. **In-process asyncio background loop** in FastAPI lifespan for automatic periodic refresh (API server)
2. **CLI command** (`voter-api election refresh`) for manual/cron-triggered refresh

Use **no external dependencies** (no Celery, no APScheduler). Leverage the existing `InProcessTaskRunner` pattern for in-process execution.

### Implementation Design

#### A. Asyncio Lifespan Background Task

Extend `src/voter_api/main.py` lifespan context manager:

```python
import asyncio
from contextlib import asynccontextmanager
from voter_api.services.election_service import refresh_all_active_elections

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url, echo=False)

    # Start background refresh loop
    refresh_task = None
    if settings.election_refresh_enabled:
        async def refresh_loop():
            while True:
                try:
                    await asyncio.sleep(settings.election_refresh_interval)
                    await refresh_all_active_elections()
                except asyncio.CancelledError:
                    logger.info("Election refresh task cancelled")
                    break
                except Exception:
                    logger.exception("Election refresh failed")

        refresh_task = asyncio.create_task(refresh_loop())

    yield

    # Shutdown: cancel background task, dispose engine
    if refresh_task:
        refresh_task.cancel()
        await refresh_task
    await dispose_engine()
```

**Configuration** (via `src/voter_api/core/config.py`):
```python
election_refresh_enabled: bool = Field(default=True)
election_refresh_interval: int = Field(default=60)  # seconds
```

#### B. CLI Command for Manual Refresh

```python
# src/voter_api/cli/election.py
import typer
from voter_api.services.election_service import refresh_all_active_elections

@election_app.command("refresh")
def refresh_command():
    """Refresh all active election results from GA SoS feed."""
    asyncio.run(refresh_all_active_elections())
    typer.echo("Election refresh complete")
```

**Cron usage** (external to piku, on a separate scheduler):
```bash
# Refresh every minute during election nights
* * * * * /path/to/voter-api election refresh
```

### Rationale

1. **No new dependencies**: The project has an existing `InProcessTaskRunner` (see `src/voter_api/core/background.py`), but it's designed for one-off background jobs (import/export). A simple asyncio loop is more appropriate for periodic polling.

2. **Piku-friendly**: Piku's `Procfile` model (single `web` worker) doesn't support dedicated background workers. The in-process loop runs in the same uvicorn process. For external cron, the CLI command can be invoked from any machine with database access.

3. **Configurable via env vars**: `ELECTION_REFRESH_ENABLED=false` disables the loop (e.g., in development). `ELECTION_REFRESH_INTERVAL` allows tuning (60s on election night, 3600s for historical elections).

4. **Graceful shutdown**: The `asyncio.CancelledError` handler ensures the task stops cleanly on app shutdown (no orphaned coroutines).

### Alternatives Considered

1. **APScheduler**:
   - **Pros**: Cron-like scheduling syntax, persistent job store
   - **Cons**: Adds dependency; requires SQLite/PostgreSQL job store for persistence; overkill for a single periodic task
   - **Rejected**: Over-engineered

2. **Celery + Redis**:
   - **Pros**: Industry-standard async task queue, retries, monitoring
   - **Cons**: Requires Redis (not in current stack), separate worker process (incompatible with piku single-worker model), heavyweight
   - **Rejected**: Massive scope increase for a simple polling loop

3. **External cron only** (no in-process loop):
   - **Pros**: Decoupled from API server, easier to debug
   - **Cons**: Requires external scheduler (not self-contained), less responsive (minimum 1-minute cron granularity), complicates deployment
   - **Rejected**: Violates FR-005 requirement for automatic refresh

4. **FastAPI BackgroundTasks**:
   - **Pros**: Built-in FastAPI feature
   - **Cons**: Designed for request-scoped tasks (runs after response sent), not long-running loops; no persistence
   - **Rejected**: Wrong tool for periodic polling

### Refresh Logic

The `refresh_all_active_elections()` service function will:
1. Query `elections` table for records where `status IN ('active', 'closed_polls')`
2. For each election, fetch the SoS JSON feed via `httpx` (existing project dependency)
3. Parse and upsert county results (insert new, update existing based on `election_id + county_name`)
4. Update `elections.last_refreshed_at` timestamp
5. Auto-transition status:
   - `active` → `closed_polls` when current time > election date + 8 hours (polls closed)
   - `closed_polls` → `finalized` when admin manually marks via API endpoint

**Idempotency**: Upserts handle repeated fetches (SoS feed updates in place, no append-only log).

---

## 4. Cache Control Headers

### Decision
Implement **dynamic Cache-Control headers** based on election status in FastAPI route handlers:

- **Active elections** (`status='active'`): `Cache-Control: public, max-age=60` (1 minute)
- **Closed polls** (`status='closed_polls'`): `Cache-Control: public, max-age=300` (5 minutes)
- **Finalized elections** (`status='finalized'`): `Cache-Control: public, max-age=86400` (24 hours)

### Implementation

```python
# src/voter_api/api/v1/elections.py
from fastapi import Response

@elections_router.get("/{election_id}/results")
async def get_election_results(
    election_id: uuid.UUID,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
):
    election = await election_service.get_election(session, election_id)
    if not election:
        raise HTTPException(404)

    # Set Cache-Control based on status
    cache_ttl = {
        "active": 60,
        "closed_polls": 300,
        "finalized": 86400,
    }[election.status]
    response.headers["Cache-Control"] = f"public, max-age={cache_ttl}"

    # Return results...
```

### Rationale

1. **Public caching**: Election results are public data (no authentication required per FR-001). CDNs and browsers can cache responses.

2. **Short TTL for active elections**: Results update frequently (background task fetches every 60s). Clients get near-real-time data with minimal origin load.

3. **Long TTL for finalized elections**: Historical results never change. 24-hour TTL allows aggressive caching while maintaining reasonable cache invalidation for bug fixes.

4. **Cloudflare edge caching**: The production deployment uses Cloudflare Tunnel. Cloudflare respects `Cache-Control` headers and will edge-cache responses, reducing database load on election night.

### Alternatives Considered

1. **ETag + 304 Not Modified**:
   - **Pros**: Conditional requests save bandwidth
   - **Cons**: Still requires database query to compute ETag; adds complexity
   - **Rejected**: Time-based cache TTL is simpler and sufficient

2. **Fixed TTL for all elections**:
   - **Pros**: Simpler logic
   - **Cons**: Either too aggressive (stale data for active elections) or too conservative (high DB load for finalized elections)
   - **Rejected**: Violates FR-017 requirement for varying headers

3. **Surrogate-Control header** (for Cloudflare/CDN only):
   - **Pros**: Separate edge cache TTL from browser cache
   - **Cons**: Requires CDN-specific logic; overkill for MVP
   - **Rejected**: Over-engineered

---

## 5. GeoJSON Generation Strategy

### Decision
Join `county_results` with `boundaries` table (via `county_metadata`) and use **GeoAlchemy2's `ST_AsGeoJSON`** for geometry serialization. Follow the existing `BoundaryFeatureCollection` pattern from `/api/v1/boundaries/geojson`.

### Implementation Pattern

Reuse the existing GeoJSON export pattern from `src/voter_api/api/v1/boundaries.py`:

```python
# src/voter_api/api/v1/elections.py
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from voter_api.schemas.election import ElectionResultFeatureCollection, ElectionResultFeature

@elections_router.get("/{election_id}/results/geojson")
async def get_election_results_geojson(
    election_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse:
    """Return county-level election results as GeoJSON FeatureCollection."""

    # Join: county_results -> county_metadata -> boundaries
    query = (
        select(CountyResult, Boundary.geometry)
        .join(CountyMetadata, func.upper(CountyResult.county_name) == func.upper(CountyMetadata.name))
        .join(Boundary, and_(
            Boundary.boundary_identifier == CountyMetadata.geoid,
            Boundary.boundary_type == "county"
        ))
        .where(CountyResult.election_id == election_id)
    )

    result = await session.execute(query)
    rows = result.all()

    features: list[dict] = []
    for county_result, geometry in rows:
        geom_shape = to_shape(geometry)
        properties = {
            "county_name": county_result.county_name,
            "precincts_reporting": county_result.precincts_reporting,
            "precincts_participating": county_result.precincts_participating,
            "results": county_result.results_json,  # JSONB field
        }
        feature = ElectionResultFeature(
            id=str(county_result.id),
            geometry=mapping(geom_shape),
            properties=properties,
        )
        features.append(feature.model_dump())

    collection = ElectionResultFeatureCollection(features=features)
    return JSONResponse(
        content=collection.model_dump(),
        media_type="application/geo+json",
    )
```

### Rationale

1. **Reuse proven pattern**: The existing `/api/v1/boundaries/geojson` endpoint demonstrates this exact workflow. Copy-paste the GeoAlchemy2 → Shapely → JSON pipeline.

2. **Efficient spatial serialization**: `to_shape()` converts PostGIS geometry to Shapely objects. `mapping()` converts Shapely to GeoJSON-compatible dicts. No manual WKT parsing.

3. **PostGIS does the heavy lifting**: The geometry stays in the database (no Python-side spatial ops). The join leverages PostGIS indexes.

4. **Standard GeoJSON schema**: Use Pydantic models (`ElectionResultFeature`, `ElectionResultFeatureCollection`) to enforce the GeoJSON spec (type="Feature", type="FeatureCollection").

### Alternatives Considered

1. **Manual WKT/WKB parsing**:
   - **Pros**: No GeoAlchemy2 dependency
   - **Cons**: Re-inventing the wheel; error-prone; the project already uses GeoAlchemy2
   - **Rejected**: Existing pattern works perfectly

2. **ST_AsGeoJSON in SQL** (return raw JSON string):
   - **Pros**: Slightly faster (no Python object conversion)
   - **Cons**: Loses type safety; cannot use Pydantic validation; inconsistent with existing codebase
   - **Rejected**: Not worth the tradeoff

3. **Pre-compute GeoJSON and store in JSONB**:
   - **Pros**: Zero query-time overhead
   - **Cons**: Duplicates geometry data; breaks normalization; stale data if boundaries update
   - **Rejected**: Premature optimization

### Schema Design

```python
# src/voter_api/schemas/election.py
class ElectionResultFeature(BaseModel):
    """GeoJSON Feature for a county's election results."""
    type: str = "Feature"
    id: str
    geometry: dict  # GeoJSON geometry object
    properties: dict  # County name + results JSONB

class ElectionResultFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection of county election results."""
    type: str = "FeatureCollection"
    features: list[ElectionResultFeature]
```

**Properties field structure**:
```json
{
  "county_name": "Houston",
  "precincts_reporting": 5,
  "precincts_participating": 7,
  "results": { /* full localResults[i].ballotItems JSONB */ }
}
```

---

## 6. Data Model Design

### Decision
Use a **hybrid relational + JSONB model** with three core tables:

1. **`elections`**: Election metadata and status tracking
2. **`county_results`**: County-level aggregations (one row per county per election)
3. **`election_feed_snapshots`**: Optional audit log of raw SoS JSON (for FR-006 compliance)

### Schema Definition

#### Table: `elections`

```sql
CREATE TABLE elections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sos_election_id VARCHAR(100) UNIQUE NOT NULL,  -- From SoS feed JSON
    election_name VARCHAR(500) NOT NULL,
    election_date DATE NOT NULL,
    created_at_sos TIMESTAMP WITH TIME ZONE NOT NULL,  -- From SoS createdAt field
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'closed_polls', 'finalized'
    last_refreshed_at TIMESTAMP WITH TIME ZONE,
    finalized_at TIMESTAMP WITH TIME ZONE,
    finalized_by_user_id UUID REFERENCES users(id),
    raw_feed_json JSONB,  -- Full SoS feed for FR-006 compliance
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_elections_date ON elections(election_date);
CREATE INDEX idx_elections_status ON elections(status);
CREATE INDEX idx_elections_sos_id ON elections(sos_election_id);
```

**Constraints**:
- `sos_election_id`: Derived from SoS feed URL or `results.id` field (unique per election)
- `status`: Check constraint `IN ('active', 'closed_polls', 'finalized')`

#### Table: `county_results`

```sql
CREATE TABLE county_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id UUID NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
    county_name VARCHAR(100) NOT NULL,  -- Normalized (no " County" suffix)
    county_metadata_id UUID REFERENCES county_metadata(id),  -- Resolved during ingestion
    precincts_participating INT,
    precincts_reporting INT,
    results_json JSONB NOT NULL,  -- Full localResults[i].ballotItems array
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(election_id, county_name)
);

CREATE INDEX idx_county_results_election ON county_results(election_id);
CREATE INDEX idx_county_results_county_meta ON county_results(county_metadata_id);
CREATE INDEX idx_county_results_json ON county_results USING GIN(results_json);
```

**JSONB structure** (`results_json` field):
```json
[
  {
    "type": "Local",
    "id": "SSD18",
    "name": "State Senate - District 18",
    "voteFor": 1,
    "precinctsParticipating": 7,
    "precinctsReporting": 5,
    "ballotOptions": [ /* candidates with vote counts */ ]
  }
]
```

#### Table: `election_feed_snapshots` (optional, for audit trail)

```sql
CREATE TABLE election_feed_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id UUID NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_json JSONB NOT NULL,
    http_etag VARCHAR(200),
    http_last_modified TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_feed_snapshots_election ON election_feed_snapshots(election_id);
CREATE INDEX idx_feed_snapshots_fetched ON election_feed_snapshots(fetched_at);
```

### Rationale

1. **Hybrid approach balances flexibility and performance**:
   - **Relational**: Election metadata, status, timestamps (efficient filtering, indexing)
   - **JSONB**: Deeply nested SoS feed data (preserves structure, avoids 6+ table normalization)

2. **County results as separate table**:
   - Enables efficient joins with `boundaries` via `county_metadata` for GeoJSON
   - One row per county per election (simple upsert during refresh)
   - Precinct-level results embedded in JSONB (no need for separate `precinct_results` table)

3. **JSONB GIN indexes**:
   - `idx_county_results_json`: Enables queries like `WHERE results_json @> '{"id": "SSD18"}'` (find counties with a specific contest)
   - PostGIS + JSONB queries are efficient (tested on millions of rows in production systems)

4. **Audit trail via snapshots**:
   - Optional table for compliance/debugging (stores raw HTTP responses)
   - Can be purged periodically (retention policy TBD)
   - Decoupled from `elections.raw_feed_json` (which stores only the latest fetch)

5. **Status-driven workflow**:
   - `active`: Polls open, results updating in real-time
   - `closed_polls`: Polls closed, results still being counted (auto-transitioned 8 hours after election date)
   - `finalized`: Admin-certified results (manual transition via API)

### Alternatives Considered

1. **Fully normalized schema** (separate tables for contests, candidates, precincts):
   ```sql
   elections -> contests -> candidates -> vote_methods -> precinct_results
   ```
   - **Pros**: Type-safe columns, granular indexes, SQL-friendly queries
   - **Cons**: 6+ tables, complex migrations, difficult to preserve exact SoS feed structure, overkill for read-heavy API
   - **Rejected**: Over-engineered

2. **Single JSONB column** (no `county_results` table):
   - Store entire SoS feed in `elections.raw_feed_json`, query via JSONB operators
   - **Pros**: Minimal schema, ultimate flexibility
   - **Cons**: Cannot efficiently join with `boundaries` for GeoJSON, slow spatial queries
   - **Rejected**: Violates GeoJSON performance requirement

3. **Separate table per election** (dynamic table creation):
   - **Pros**: Simple ingestion (no upsert logic)
   - **Cons**: Unbounded table growth, impossible to query across elections
   - **Rejected**: Anti-pattern

4. **Time-series database** (TimescaleDB, InfluxDB):
   - **Pros**: Optimized for time-series data
   - **Cons**: Requires new DB, spatial support unclear, overkill for occasional elections
   - **Rejected**: Massive scope increase

### Migration Strategy

Alembic migration will:
1. Create `elections`, `county_results`, `election_feed_snapshots` tables
2. Create indexes and constraints
3. No data migration (new feature, no existing election data)

**Migration file**: `alembic/versions/012_add_election_tracking.py`

---

## Summary

| Topic | Decision | Rationale |
|-------|----------|-----------|
| **Data Model** | Hybrid relational + JSONB (3 tables) | Balances structure (election metadata) with flexibility (nested SoS feed) |
| **County Matching** | Strip " County" suffix, match `county_metadata.name` | Reliable, no FIPS lookup needed, leverages existing canonical data |
| **Background Refresh** | Asyncio loop in lifespan + CLI command | Zero new dependencies, piku-compatible, configurable via env vars |
| **Cache Headers** | Dynamic `Cache-Control` by status | Active: 60s, Closed: 300s, Finalized: 86400s (Cloudflare edge-friendly) |
| **GeoJSON Export** | Join with `boundaries`, use GeoAlchemy2 | Reuses proven pattern from `/boundaries/geojson`, efficient PostGIS queries |

All design decisions prioritize **simplicity, existing patterns, and zero new dependencies** while satisfying functional requirements FR-001 through FR-017.
