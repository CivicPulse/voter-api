# Feature Research

**Domain:** Election search, filtering, and discovery API for civic data
**Researched:** 2026-03-16
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features the voter-web frontend team and API consumers assume exist. Missing these means the elections list page cannot ship.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Free-text search (`q` param) | Every list endpoint needs a search box. Users type candidate names, district names, election titles. Frontend cannot ship without this. | LOW | ILIKE on `name` + `district` columns. Both are indexed. PostgreSQL `%term%` ILIKE is fine at current scale (~34 elections). Add `pg_trgm` GIN index only if dataset grows past 1,000 rows. |
| Race category filter (`race_category`) | Users think in "federal / state / local" buckets, not internal `district_type` values. The frontend dropdown needs a human-friendly grouping. | LOW | Pure mapping layer over existing `district_type`. No new column needed. Map: `federal` = congressional + us_senate, `state_senate` = state_senate, `state_house` = state_house, `local` = county_commission + county_office + city_council + municipal + board_of_education + judicial, `statewide` = statewide + psc. |
| County filter (`county`) | Georgia voters care about their county. "Show me elections in Bibb County" is the most natural geographic filter for local races. | LOW | Exact match on existing `eligible_county` column, already indexed (`idx_elections_eligible_county`). Case-insensitive comparison recommended (ILIKE or `lower()`). |
| Filter options endpoint (`GET /elections/filter-options`) | Frontend dropdowns need to know what values exist. Hardcoding filter values in the frontend is fragile and falls out of sync with data. Every civic data API that serves a UI provides this. | MEDIUM | `SELECT DISTINCT` queries across filter columns. Return JSON object with arrays for each filter dimension: `election_types`, `statuses`, `race_categories`, `counties`, `district_types`. Unscoped (global) first -- scoped (cascading) is a separate feature. |
| Pagination on all list endpoints | Already exists. Noting for completeness -- the existing `page`/`page_size` pattern is table stakes. | ALREADY BUILT | Existing implementation is correct. |
| Date range filtering (`date_from`, `date_to`) | Already exists. Users expect to narrow by date window. | ALREADY BUILT | Existing implementation covers this. |

### Differentiators (Competitive Advantage)

Features that make the CivPulse API more useful than alternatives like Google Civic Information or BallotReady, which are address-centric rather than browsable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Capabilities endpoint (`GET /elections/capabilities`) | Progressive feature discovery -- the frontend can adapt its UI based on what filters the API actually supports. Prevents frontend/backend version skew. Neither Google Civic nor Democracy Works expose this. Borrowed from OGC API Features pattern. | LOW | Static JSON response listing supported filter names, types, and operators. No database queries. Can be hardcoded initially and made dynamic later. The key insight: this is a contract, not a feature. It tells the frontend "you can use these filters." |
| Exact date filter (`election_date`) | Complements existing `date_from`/`date_to` range. "Show me everything on May 19, 2026" is a common query for election-day coverage. Google Civic uses `electionId` instead, which requires knowing IDs upfront. | LOW | `Election.election_date == date_param`. Trivially small. Mutually exclusive with date range -- if `election_date` is provided, ignore `date_from`/`date_to` or return 422. |
| Temporal status filters (`registration_open`, `early_voting_active`) | Already built. These are genuinely differentiating -- most civic APIs require the consumer to compute these from raw dates. CivPulse does the math server-side. | ALREADY BUILT | Keep promoting these in the capabilities endpoint. |
| Combined multi-filter queries | All filters composable via AND. BallotReady's GraphQL forces structured queries; Google Civic is address-only. CivPulse lets you do `?race_category=federal&county=Bibb&date_from=2026-01-01` in a single GET. | LOW | Already works -- the existing filter chain in `list_elections` applies AND to all provided filters. New filters just add more `if param: filters.append(...)` clauses. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full-text search with ranking/relevance | "Search should rank results by relevance like Google" | PostgreSQL `ts_vector` / `ts_rank` adds significant complexity (migration, index maintenance, query rewriting) for a dataset of ~34 elections. ILIKE is simpler and sufficient. Relevance ranking on election names is meaningless -- users want exact matches, not fuzzy. | Simple ILIKE search on `name` + `district`. If the dataset grows past 1,000 elections, revisit with `pg_trgm` trigram index for substring matching. |
| Scoped/cascading filter options | "When I select county=Bibb, the race_category dropdown should only show categories that exist in Bibb County" | Combinatorial query explosion. Every filter combination needs its own DISTINCT query. For N filters, that is O(2^N) possible scoping contexts. Slow, complex to implement, and the dataset is small enough that empty result sets are self-correcting. | Unscoped filter options first. Frontend shows all values, empty results teach the user. Add scoped options as a fast-follow only if user research demands it. Already noted as backlog in PROJECT.md. |
| Geospatial "elections near me" search | "Enter an address, get elections you can vote in" | Requires point-in-polygon against all boundary geometries for every election, which means joining elections to boundaries and running ST_Contains. This is the BallotReady/Google Civic model -- it is a different product feature, not a search filter enhancement. Also requires knowing voter registration address, not just location. | Keep this as a separate feature (voter-centric lookup), not part of the election list/search endpoint. The existing `district_type` + `district_identifier` filters serve the "which elections apply to this district" use case. |
| OR-based multi-value filters | "Filter by race_category=federal OR race_category=state_senate" | Adds query complexity (IN clause instead of ==). Rarely needed at current scale. Multi-select dropdowns in the UI add UX complexity. | Single-value filters first. If the frontend needs multi-select, accept comma-separated values and split to an IN clause. Do this as a v1.x enhancement, not launch. |
| Sorting by arbitrary fields | "Sort by name, date, county, relevance" | Each sortable field needs an index for performance. Sorting by `name` is rarely useful for elections. Default sort (date descending) is the right answer for 95% of use cases. | Fixed sort: `election_date DESC`. If needed later, add `sort_by` param limited to `election_date` and `name` only. |
| Saved searches / search bookmarks | "Save my filter combination for later" | Requires user accounts for anonymous visitors, adds state management, and the entire search state is already in the URL query string. | Frontend bookmarks the URL with query params. This is a frontend concern, not an API feature. |

## Feature Dependencies

```
Capabilities endpoint (contract)
    └──informs──> Frontend filter UI (what to render)

Filter options endpoint
    └──requires──> All filter params implemented (needs to know which columns to DISTINCT)

Race category filter
    └──requires──> district_type populated on elections (already done via import pipeline)
    └──requires──> Category-to-district_type mapping (code-level, no migration)

County filter
    └──requires──> eligible_county populated on elections (already done via import pipeline)

Text search (q param)
    └──independent──> No dependencies, works on name + district columns

Exact date filter
    └──independent──> No dependencies, works on election_date column
    └──conflicts──> date_from/date_to (mutually exclusive or precedence rule needed)
```

### Dependency Notes

- **Filter options requires all filters implemented:** The filter-options endpoint returns valid values for each filter dimension. It should be built last so it reflects the actual filter set.
- **Capabilities requires filter set finalized:** The capabilities endpoint is a contract -- it advertises what exists. Build it after all filters are implemented, or build it as a static stub and update it as filters land.
- **Race category requires mapping definition:** The mapping from `race_category` values to `district_type` values must be defined once and shared between the filter logic and the filter-options endpoint. Define it as a constant dict in a shared location (e.g., `schemas/election.py` or a new `lib/election_filters.py`).
- **Exact date conflicts with date range:** Define precedence: if `election_date` is provided, it takes priority over `date_from`/`date_to`. Document this in the capabilities endpoint. Do not return 422 -- just ignore the range params silently, which is what most REST APIs do.

## MVP Definition

### Launch With (v1.1)

Everything the frontend team requested, in implementation order:

- [ ] Text search (`q` param) -- highest user-facing value, simplest to implement
- [ ] Race category filter (`race_category`) -- mapping layer over existing data
- [ ] County filter (`county`) -- exact match on existing indexed column
- [ ] Exact date filter (`election_date`) -- trivial WHERE clause
- [ ] Filter options endpoint (`GET /elections/filter-options`) -- build after filters exist
- [ ] Capabilities endpoint (`GET /elections/capabilities`) -- build last, advertises everything above

### Add After Validation (v1.x)

Features to add once the frontend is using v1.1 filters and providing feedback:

- [ ] Scoped filter options -- add when the frontend team reports users are confused by empty results from unscoped dropdowns
- [ ] Multi-value filters (comma-separated) -- add when the frontend team requests multi-select dropdowns
- [ ] `pg_trgm` trigram index -- add when election count exceeds ~500 and ILIKE performance degrades
- [ ] Statewide election inclusion in county filter -- add when users report "I filtered by Bibb County but don't see the Governor's race"

### Future Consideration (v2+)

- [ ] Address-based "my elections" lookup -- different product feature, not a list filter
- [ ] Full-text search with ranking -- only if dataset grows dramatically
- [ ] Saved search / notification -- frontend concern, not API

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Text search (`q`) | HIGH | LOW | P1 |
| Race category filter | HIGH | LOW | P1 |
| County filter | HIGH | LOW | P1 |
| Exact date filter | MEDIUM | LOW | P1 |
| Filter options endpoint | HIGH | MEDIUM | P1 |
| Capabilities endpoint | MEDIUM | LOW | P1 |
| Scoped filter options | MEDIUM | HIGH | P2 |
| Multi-value filters | LOW | MEDIUM | P2 |
| Statewide in county filter | MEDIUM | HIGH | P3 |
| Address-based lookup | HIGH | HIGH | P3 |

**Priority key:**
- P1: Must have for v1.1 launch (frontend team is blocked without these)
- P2: Should have, add based on frontend feedback
- P3: Future feature, different scope

## Competitor Feature Analysis

| Feature | Google Civic Info | BallotReady | Democracy Works | CivPulse (our approach) |
|---------|-------------------|-------------|-----------------|------------------------|
| Search model | Address-centric (required param) | Address/lat-lon + GraphQL | OCD-ID based | Browsable list + filters (no address required) |
| Election listing | By electionId only | By address | By OCD division IDs | Paginated list with composable filters |
| Race categorization | Contest level (federal/state/local) | Government level filter | Not exposed | `race_category` mapping over `district_type` |
| County filtering | Not supported (address determines) | Not directly (radius search) | Not directly (OCD-ID) | Direct `county` param on `eligible_county` |
| Date filtering | Current/upcoming only | Not documented | Upcoming only | Full range (`date_from`, `date_to`, exact `election_date`) |
| Temporal filters | None | None | None | `registration_open`, `early_voting_active` (differentiator) |
| Filter discovery | None (read the docs) | GraphQL introspection | None | Explicit `/capabilities` + `/filter-options` endpoints |
| Free-text search | None | None documented | None | ILIKE on name + district |

**Key insight:** Most civic data APIs are address-lookup tools ("what elections apply to me at this address?"). CivPulse's election list with composable filters serves a different use case: browsable discovery ("what elections exist in this county/category/timeframe?"). This is the right model for the voter-web frontend, which needs to display election directories, not just personalized ballots.

## Sources

- [Google Civic Information API](https://developers.google.com/civic-information) -- address-centric model, no list/filter endpoints
- [BallotReady API](https://organizations.ballotready.org/ballotready-api) -- GraphQL, address/lat-lon, government level filter
- [Democracy Works Elections API](https://www.democracy.works/elections-api) -- OCD-ID based filtering
- [Speakeasy REST API Filtering Best Practices](https://www.speakeasy.com/api-design/filtering-responses) -- query parameter patterns
- [Moesif REST API Design: Filtering, Sorting, Pagination](https://www.moesif.com/blog/technical/api-design/REST-API-Design-Filtering-Sorting-and-Pagination/) -- filter design patterns
- Existing codebase: `src/voter_api/api/v1/elections.py`, `src/voter_api/services/election_service.py`, `src/voter_api/lib/district_parser/parser.py`

---
*Feature landscape research: Election search and filter API capabilities*
*Researched: 2026-03-16*
