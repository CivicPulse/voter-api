# Stack Research

**Domain:** Election search/filter API capabilities for existing FastAPI + SQLAlchemy + PostgreSQL/PostGIS REST API
**Researched:** 2026-03-16
**Confidence:** HIGH

## Verdict: No New Dependencies Required

Every capability needed for v1.1 Election Search is achievable with the existing stack. The codebase already has all the patterns and technologies required. This is a feature-layer change, not a stack change.

## Existing Stack (Relevant Subset)

| Technology | Version | Role in This Milestone |
|------------|---------|----------------------|
| PostgreSQL 15 / PostGIS 3.4 | 15-3.4 (Docker image) | ILIKE, DISTINCT, COUNT aggregation -- all built-in |
| SQLAlchemy 2.x async | >=2.0.0 | Query building with `.ilike()`, `func.count()`, `func.distinct()` |
| FastAPI | >=0.115.0 | New endpoints, Query parameter validation |
| Pydantic v2 | >=2.0.0 | New request/response schemas, Literal types for enums |

## Capability-by-Capability Analysis

### 1. Free-Text Search (`q` parameter)

**Recommendation: ILIKE across `name` + `district` columns. Do NOT use PostgreSQL full-text search.**

**Why ILIKE, not tsvector:**

| Factor | ILIKE | Full-Text Search (tsvector) |
|--------|-------|---------------------------|
| Data scale | ~34 elections, growing to maybe hundreds | Designed for thousands-to-millions of documents |
| Setup cost | Zero -- one WHERE clause | Migration for generated column + GIN index |
| Query complexity | `OR(name.ilike(...), district.ilike(...))` | `to_tsvector`, `plainto_tsquery`, `@@` operator, ranking |
| Partial word match | Works naturally ("Spe" matches "Special") | Does NOT match partial words without `prefix:*` syntax |
| User expectation | Typing "bibb" finds "Bibb County" | Stemming would match "running" for "run" -- overkill for election names |
| Performance | Seq scan on <1000 rows: <1ms | GIN index overhead not justified at this scale |

The codebase already has a full-text search implementation on `agenda_items` (see `src/voter_api/models/agenda_item.py` lines 69-77 and `src/voter_api/services/meeting_search_service.py`). That pattern exists if scale ever demands it, but election names are proper nouns and district identifiers -- not prose text that benefits from stemming and ranking.

**Implementation pattern (already in codebase):**
```python
# From election_service.py line 625 -- existing ILIKE on district
filters.append(Election.district.ilike(f"%{district}%"))

# New: search across name AND district
if q:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    filters.append(
        or_(Election.name.ilike(pattern), Election.district.ilike(pattern))
    )
```

The wildcard-escaping pattern is already used in `voter_service.py` (lines 82-89) and `meeting_search_service.py` (lines 81-82). Follow that same pattern.

**Confidence: HIGH** -- ILIKE on small tables is a well-understood PostgreSQL pattern. The existing `idx_elections_*` B-tree indexes won't help ILIKE with leading wildcards, but at <1000 rows sequential scan is faster than any index lookup anyway.

### 2. Race Category Mapping (`race_category` filter)

**Recommendation: Pure Python dict mapping in the service layer. No new column, no migration.**

The `district_type` column already contains values like `us_house`, `state_senate`, `state_house`, `county_commission`, etc. The `race_category` parameter is a frontend-friendly grouping:

```python
RACE_CATEGORY_MAP: dict[str, list[str]] = {
    "federal": ["us_senate", "us_house", "president"],
    "state": ["governor", "state_senate", "state_house", "secretary_of_state", ...],
    "county": ["county_commission", "sheriff", "tax_commissioner", ...],
    "municipal": ["mayor", "city_council", ...],
    "judicial": ["superior_court", "magistrate", ...],
    "school_board": ["school_board"],
    "special": ["special_purpose"],
}
```

**Why a dict, not a DB column or enum:**
- The mapping is a presentation concern, not a data concern
- `district_type` is the authoritative field -- race_category is derived
- Adding a column means a migration + backfill for zero data benefit
- The mapping can evolve without migrations as new district types appear
- At query time: `Election.district_type.in_(RACE_CATEGORY_MAP[race_category])`

**Confidence: HIGH** -- This is the PROJECT.md's stated approach ("race_category maps to district_type").

### 3. County Filter (`county` parameter)

**Recommendation: Exact case-insensitive match on `eligible_county` column.**

```python
if county:
    filters.append(func.lower(Election.eligible_county) == county.lower())
```

The `eligible_county` column already exists (model line 77) with an index (`idx_elections_eligible_county`, model line 117). This is a straightforward exact-match filter.

**Statewide election inclusion is explicitly deferred** per PROJECT.md backlog: "Statewide election inclusion in county filter (geospatial boundary logic)." First version does simple matching only.

**Confidence: HIGH** -- Column and index already exist.

### 4. Exact Date Filter (`election_date` parameter)

**Recommendation: Direct equality on `election_date` column.**

```python
if election_date:
    filters.append(Election.election_date == election_date)
```

Complementary to existing `date_from`/`date_to` range filters. The `idx_elections_election_date` B-tree index already covers this.

**Confidence: HIGH** -- Trivial addition.

### 5. Capabilities Endpoint (`GET /elections/capabilities`)

**Recommendation: Static Pydantic response model, no database query.**

This endpoint tells the frontend which filters are available, what values they accept, and which are currently active. It is a contract/discovery mechanism, not a data query.

```python
class ElectionCapabilities(BaseModel):
    filters: list[FilterCapability]
    search: SearchCapability
    sort_options: list[str]
    version: str  # e.g., "1.0"
```

No new dependencies. Pure schema definition + a static handler that returns the hardcoded capabilities object.

**Confidence: HIGH** -- Standard progressive disclosure pattern.

### 6. Filter Options Endpoint (`GET /elections/filter-options`)

**Recommendation: SQLAlchemy `func.distinct()` + `func.count()` aggregation queries against the elections table.**

```python
# Example: distinct district_type values with counts
stmt = (
    select(
        Election.district_type,
        func.count(Election.id).label("count"),
    )
    .where(Election.deleted_at.is_(None))
    .group_by(Election.district_type)
    .order_by(func.count(Election.id).desc())
)
```

Run one query per filter dimension (district_type, eligible_county, election_type, status, source, election_date). At <1000 rows, all queries complete in <5ms total. Combine results into a single response.

For race_category options, aggregate in Python after fetching district_type counts (reverse the RACE_CATEGORY_MAP to group counts).

**No caching needed** at this data scale. If scale grows to >10K elections, consider `Cache-Control: max-age=300` headers or in-memory TTL cache.

**Confidence: HIGH** -- Standard SQL aggregation, already used throughout the codebase.

## What NOT to Add

| Avoid | Why | What to Do Instead |
|-------|-----|-------------------|
| PostgreSQL full-text search (tsvector) for elections | Overkill for <1000 rows of proper-noun data; adds migration complexity; partial-word matching (which users expect) requires extra `tsquery` syntax | ILIKE with wildcard escaping |
| Elasticsearch / Meilisearch / Typesense | External service dependency for a table with 34 rows | ILIKE |
| pg_trgm extension | Trigram indexes help ILIKE performance at scale; not needed at <1000 rows | Sequential scan is faster |
| New Python packages | No library gaps exist | Use existing SQLAlchemy, Pydantic, FastAPI |
| Redis/memcached for filter options | Caching adds operational complexity; queries are <5ms | Direct DB queries; add Cache-Control headers if needed |
| New database columns | `race_category` is derived from `district_type`; no new data to store | Python dict mapping in service layer |
| New Alembic migrations | No schema changes needed for search/filter features | All columns and indexes already exist |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| ILIKE for search | PostgreSQL tsvector + GIN | When elections table exceeds ~5,000 rows AND users need linguistic matching (stemming, ranking). The codebase already has this pattern in `agenda_items` -- can be ported if needed. |
| Python dict for race_category mapping | Database enum or lookup table | If race categories need to be user-configurable at runtime (admin CRUD). Currently they are a fixed taxonomy. |
| Direct DB queries for filter options | Materialized view | When filter option queries take >100ms (would require >100K elections). Not foreseeable. |
| No caching | In-memory TTL cache (e.g., `cachetools`) | If filter-options endpoint gets >100 req/sec. Add `cachetools` (already in Python stdlib-adjacent, 3KB package) with 60s TTL. |

## Installation

```bash
# No new dependencies needed for v1.1 Election Search
# All functionality uses existing packages
```

## Stack Patterns for This Milestone

**Pattern: Filter builder with OR-search**
The existing `list_elections()` in `election_service.py` uses a `filters: list[ColumnElement[bool]]` accumulator pattern (lines 619-648). All new filters follow this same pattern. The `q` search parameter adds an `or_()` clause to the same list.

**Pattern: Aggregation service function**
The filter-options endpoint introduces a new pattern: queries that return aggregated metadata rather than entity lists. Implement as a separate service function (`get_filter_options()`) that returns a typed dict or Pydantic model, not as part of `list_elections()`.

**Pattern: Static capability declaration**
The capabilities endpoint is a new pattern for this codebase: a schema-only endpoint with no database interaction. Implement as a module-level constant (frozen Pydantic model instance) that gets returned directly.

## Version Compatibility

No version concerns. All features use core PostgreSQL 15 capabilities (ILIKE, DISTINCT, COUNT, GROUP BY) and existing SQLAlchemy 2.x APIs. No new packages to version-check.

## Sources

- `src/voter_api/services/election_service.py` lines 616-695 -- existing filter/query pattern (direct code inspection)
- `src/voter_api/models/election.py` lines 37-126 -- Election model with existing columns and indexes (direct code inspection)
- `src/voter_api/models/agenda_item.py` lines 69-77 -- existing tsvector pattern for reference (direct code inspection)
- `src/voter_api/services/meeting_search_service.py` -- existing full-text search + ILIKE hybrid (direct code inspection)
- `src/voter_api/services/voter_service.py` lines 82-109 -- existing ILIKE wildcard-escape pattern (direct code inspection)
- `.planning/PROJECT.md` -- milestone scope and key decisions (direct inspection)

---
*Stack research for: v1.1 Election Search*
*Researched: 2026-03-16*
