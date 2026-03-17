# Election Search API — Frontend Integration Report

**From:** voter-api backend team
**To:** voter-web frontend team
**Date:** 2026-03-16
**Re:** Response to [API-SPEC.md](https://github.com/CivicPulse/voter-web/blob/main/.planning/API-SPEC.md) (v1.0 Draft, 2026-03-14)
**Status:** Implementation complete

---

## Summary

We reviewed your Election Filter API specification and implemented all requested functionality. This report documents what shipped, how it maps to your spec, and where our implementation differs from what you proposed.

**Delivered:**
- `GET /api/v1/elections/capabilities` — filter capability discovery
- `GET /api/v1/elections/filter-options` — dynamic dropdown values
- 5 new filter parameters on `GET /api/v1/elections`
- All backward-compatible — existing clients unaffected

---

## 1. Capabilities Endpoint

### `GET /api/v1/elections/capabilities`

**Implemented as specified.** Static response, no DB queries, public access.

```json
{
  "supported_filters": ["q", "race_category", "county", "district", "election_date"],
  "endpoints": {
    "filter_options": true
  }
}
```

No deviations from your spec.

---

## 2. Filter Parameters on `GET /api/v1/elections`

### 2.1 `q` (Text Search)

**Implemented as specified.** Case-insensitive partial match on `name` and `district` fields using `OR` logic.

| Property | Value |
|----------|-------|
| Min length | 2 characters (422 if shorter) |
| Max length | 200 characters |
| Match type | Case-insensitive substring (`ILIKE`) |
| Fields searched | `name`, `district` |

No deviations.

---

### 2.2 `race_category` (Race Category Filter)

**Implemented with a different mechanism than suggested.** Your spec proposed adding a new `race_category` column or deriving it server-side. We already had a `district_type` column on the Election model that is populated during election import. Rather than duplicating this data, we implemented `race_category` as a **mapping layer** over `district_type`.

**Accepted values and their internal mapping:**

| `race_category` value | Matches `district_type` values |
|----------------------|-------------------------------|
| `federal` | `congressional` |
| `state_senate` | `state_senate` |
| `state_house` | `state_house` |
| `local` | everything else (`county`, `city`, `municipal`, `judicial`, `school_board`, etc.) |

**What this means for you:**
- Use `race_category` exactly as your spec describes — the mapping is transparent
- The `filter-options` endpoint returns the four category values you expect
- If you ever need finer granularity (e.g., distinguishing county from municipal), we also expose `district_type` as a separate filter parameter (pre-existing, not part of your spec)

**Pre-existing filter you may not have known about:** `district_type` was already a query parameter on `GET /elections` before this milestone. It accepts the raw values: `congressional`, `state_senate`, `state_house`, `county`, `city`, `municipal`, `judicial`, `school_board`, etc. You can use either `race_category` (your abstraction) or `district_type` (our raw values).

---

### 2.3 `county` (County Filter)

**Implemented with a scope limitation.** Matches against the `eligible_county` field on Election records.

| Property | Value |
|----------|-------|
| Match type | Case-insensitive exact match |
| Format | County name without "County" suffix (e.g., `Bibb`) |
| Unknown county | Empty result set (not 422) |

**Deviation from spec — statewide elections:**

Your spec requested that statewide elections (US Senate, Governor) be included when filtering by any county. We did **not** implement this in the initial release. Here's why:

- Statewide elections don't have `eligible_county` set (they apply to all counties)
- Including them requires either: (a) a hardcoded list of statewide `district_type` values, or (b) geospatial boundary containment queries
- Both approaches have edge cases (e.g., State House districts span multiple counties — should they appear for every county they touch?)

**Current behavior:** `?county=Bibb` returns only elections with `eligible_county = 'Bibb'`. Statewide races are excluded.

**Workaround:** To show statewide races alongside county-filtered results, make two API calls:
1. `GET /elections?county=Bibb` — county-specific races
2. `GET /elections?district_type=congressional` (or `race_category=federal`) — statewide races

We can add statewide inclusion as a follow-up if this workaround is too cumbersome. Let us know.

**Data coverage note:** `eligible_county` is populated for elections imported through the JSONL pipeline (our v1.0 import path). Elections from the SOS feed auto-refresh may not have this field set. Coverage will improve as we migrate more elections to the JSONL pipeline.

---

### 2.4 `district` (District Filter)

**Deviation from spec — we kept partial matching.**

Your spec proposed changing `district` to exact match (case-insensitive). However, `district` was **already a shipped filter parameter** with partial-match (`ILIKE`) behavior. Changing it to exact match would be a breaking change for any existing API consumers.

**Current behavior (unchanged):**

| Property | Value |
|----------|-------|
| Match type | Case-insensitive **partial** match (contains) |
| Example | `?district=Senate` matches "State Senate District 18", "State Senate District 1", etc. |

**If you need exact matching**, use the `q` parameter for search or pass the full district name — partial match on the full string is effectively exact. Alternatively, we can add a separate `district_exact` parameter if there's a real use case where partial matching causes problems (e.g., "District 1" matching "District 10"). Let us know.

---

### 2.5 `election_date` (Exact Date Filter)

**Implemented as specified.** Exact date match on the `election_date` column.

| Property | Value |
|----------|-------|
| Format | `YYYY-MM-DD` (ISO 8601) |
| Invalid format | 422 |
| Interaction with `date_from`/`date_to` | `election_date` takes precedence (overrides range) |

No deviations.

---

## 3. Filter Options Endpoint

### `GET /api/v1/elections/filter-options`

**Implemented — unscoped only.** Returns all valid values regardless of other active filters.

```json
{
  "race_categories": ["federal", "state_senate", "state_house", "local"],
  "counties": ["Bibb", "Houston", "Peach"],
  "election_dates": ["2026-11-03", "2026-06-09", "2026-05-19"]
}
```

| Field | Behavior |
|-------|----------|
| `race_categories` | Categories with at least one non-deleted election, sorted alphabetically |
| `counties` | Distinct `eligible_county` values (non-null), sorted alphabetically |
| `election_dates` | Distinct dates with at least one election, sorted descending |

**Deviation from spec — no scoped filtering yet.**

Your spec described optional scoping (e.g., `?status=active` to narrow options). This is not implemented in the initial release. All values are returned regardless of context. If a user selects "Bibb" county and there are no federal races there, "federal" will still appear in `race_categories`.

**Impact:** Users may occasionally select a filter combination that returns zero results. Your UI already handles this gracefully (empty state). We can add scoped filtering as a fast-follow if dead-end selections become a UX problem.

---

## 4. Combined Filter Behavior

All parameters combine with **AND** logic, consistent with your spec:

```
GET /api/v1/elections?status=active&q=senate&county=Bibb&election_date=2026-11-03&page=1&page_size=25
```

**Interaction with pre-existing filters:**

| Pre-existing param | Still works | Notes |
|--------------------|-------------|-------|
| `status` | Yes | Unchanged |
| `election_type` | Yes | Unchanged |
| `date_from` / `date_to` | Yes | Overridden if `election_date` is also provided |
| `registration_open` | Yes | Unchanged |
| `early_voting_active` | Yes | Unchanged |
| `district` | Yes | Still partial match (see section 2.4) |
| `district_type` | Yes | Works alongside `race_category` — if both provided, both must match |
| `source` | Yes | Unchanged |

---

## 5. Feature Flag Mapping (Updated)

Your appendix mapping is correct with one adjustment:

| `supported_filters` value | Frontend flag | UI control | Notes |
|---------------------------|---------------|------------|-------|
| `q` | `search` | Text search input | As specified |
| `race_category` | `raceCategory` | Race category dropdown | Maps to `district_type` internally |
| `county` | `geographic` | County filter dropdown | No statewide inclusion (see 2.3) |
| `district` | `geographic` | District filter input | **Partial match**, not exact (see 2.4) |
| `election_date` | `electionDate` | Date picker | As specified |

---

## 6. Deviation Summary

| # | Your Spec | What We Shipped | Why | Impact |
|---|-----------|-----------------|-----|--------|
| 1 | `race_category` as new column | Mapping over existing `district_type` | Column already existed, avoids data duplication | None — API contract identical |
| 2 | `county` includes statewide races | County-only, no statewide | Geospatial complexity, data gaps | Workaround: two API calls |
| 3 | `district` as exact match | Kept as partial match | Pre-existing behavior, breaking change | Use full name for effective exact match |
| 4 | `filter-options` supports scoping | Unscoped only | Complexity, can fast-follow | Possible dead-end filter combos |

---

## 7. What's Next

These items were deferred from this milestone. Let us know which are priorities:

- **Statewide election inclusion in county filter** — requires boundary-based geospatial logic
- **Scoped filter options** — context-sensitive dropdown values based on active filters
- **`district_exact` parameter** — if partial match on `district` causes real problems
- **Full-text search upgrade** — PostgreSQL `tsvector` for ranked results if `ILIKE` performance degrades at scale

---

## Questions?

Open an issue on [CivicPulse/voter-api](https://github.com/CivicPulse/voter-api) or ping us in the team channel.
