# Phase 9: Context-Aware Mismatch Filter - Research

**Researched:** 2026-03-16
**Domain:** PostgreSQL JSONB querying via SQLAlchemy 2.x async; service-layer filter modification
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Filter Semantics**
- Exact type match only: When `has_district_mismatch=true` is passed on a `state_senate` election, only match voters whose `mismatch_details` JSONB contains `boundary_type == "state_senate"`. No type family grouping.
- Hybrid approach for unanalyzed voters: Check existing `analysis_results` JSONB. Voters without analysis data are excluded from mismatch filtering (both `=true` and `=false`) and flagged as unanalyzed in the response.
- Null district_type returns 422: If `election.district_type` is NULL and `has_district_mismatch` is specified, return a 422 validation error explaining context-aware filtering is unavailable for this election.
- Validate district_type against known set: Check that `election.district_type` is in `BOUNDARY_TYPE_TO_VOTER_FIELD` keys before querying. Return 422 if unknown type.

**Backward Compatibility**
- Silent switch on participation endpoint: Replace blanket `Voter.has_district_mismatch` filter logic with context-aware JSONB lookup on the participation endpoint. Same parameter name, smarter behavior.
- Voters list unchanged: `GET /voters` keeps using the blanket `Voter.has_district_mismatch` flag — it has no election context.
- Default path unchanged: When `has_district_mismatch` is omitted (not specified), the participation endpoint continues using `Voter.has_district_mismatch` for the response field. The expensive JSONB JOIN only happens when the filter is actively used.

**Response Enrichment**
- Nullable boolean for unanalyzed indicator: `has_district_mismatch` stays `bool | null` on `ElectionParticipationRecord`. When null, it means "no analysis data available." True/false mean context-aware result.
- Add `mismatch_district_type` to response metadata: Include the district_type used for the mismatch check in the response metadata (alongside pagination). Helpful for debugging.
- No mismatch details in response: Per REQUIREMENTS.md out-of-scope decision — mismatch details are not exposed in the participation response.

**Stats Enrichment**
- Add context-aware `mismatch_count` to stats: Include in the `ParticipationStatsResponse`. Reuses the same JSONB query logic. Included in Phase 9 scope since the JOIN logic is already being built.

### Claude's Discretion
- Exact JSONB query approach (PostgreSQL `jsonb_array_elements` vs `@>` containment operator vs lateral join)
- Whether to extract the mismatch JSONB check into a reusable utility function in the service layer
- Index strategy for the JSONB query if needed for performance
- Error message wording for 422 responses

### Deferred Ideas (OUT OF SCOPE)
- Context-aware mismatch on the voters list endpoint (`GET /voters`) — would need an election_id parameter to provide context
- Mismatch details exposed in participation response — explicitly out of scope per REQUIREMENTS.md
- New mismatch aggregation/stats beyond simple count — out of scope per REQUIREMENTS.md
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MISMATCH-01 | Participation endpoint `has_district_mismatch=true` only returns voters whose mismatch is on the election's `district_type` (via `analysis_results.mismatch_details` JSONB lookup) | JSONB containment query pattern, service layer JOIN modification, 422 validation paths all documented below |
</phase_requirements>

---

## Summary

Phase 9 is a focused service-layer and schema change with no new tables and no Alembic migrations. The core work is replacing a single blanket boolean filter (`Voter.has_district_mismatch == filters.has_district_mismatch` at `voter_history_service.py:655-657`) with a context-aware JSONB lookup that checks `analysis_results.mismatch_details` for the election's specific `district_type`. Three supporting changes follow from this: the `list_election_participants` service gains an `analysis_results` JOIN when the filter is active; `PaginatedElectionParticipationResponse` gains a `mismatch_district_type` metadata field; and `ParticipationStatsResponse` gains a `mismatch_count: int | None` field.

The JSONB column `analysis_results.mismatch_details` stores a list of dicts of the form `{"boundary_type": "state_senate", "registered": "...", "determined": "..."}`. The query goal is: "does any element in this list have `boundary_type == <election.district_type>`?" PostgreSQL supports this natively via the `@>` containment operator (`mismatch_details @> '[{"boundary_type": "state_senate"}]'`) or via `jsonb_array_elements` with a lateral join. The `@>` approach is cleaner and expressible directly in SQLAlchemy 2.x using `AnalysisResult.mismatch_details.contains(...)` with a cast or using `text()`-based predicates.

The unanalyzed voter exclusion (voters with no `analysis_results` row) is handled by using an INNER JOIN to `analysis_results` (rather than LEFT JOIN) when the filter is active. Voters with `mismatch_details IS NULL` (analyzed but matched on all boundaries) are present in `analysis_results` with a `match_status` of `"match"` and `mismatch_details = None` — they count as `has_district_mismatch = false` for the target type.

**Primary recommendation:** Use SQLAlchemy `func.cast` with a `text()` JSONB containment predicate for the `has_district_mismatch=true` case, and an `IS NULL or empty array` check for `has_district_mismatch=false`. Extract the logic into a private helper `_build_mismatch_filter()` in `voter_history_service.py` so it is reused by both `_apply_voter_filters` and `get_participation_stats`.

## Standard Stack

### Core (all already in project — no new installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy 2.x async | 2.x | ORM + JSONB operators | Project-mandated; async session already in use |
| GeoAlchemy2 | existing | (not directly used here) | — |
| PostgreSQL dialect | psycopg/asyncpg | `JSONB`, `@>` operator, `jsonb_array_elements` | Project runs PostGIS 15+; these operators are available |
| Pydantic v2 | 2.x | Schema changes (`mismatch_district_type`, `mismatch_count`) | Project-mandated |

**No new packages are needed for this phase.**

## Architecture Patterns

### Existing Pattern: voter_filters_active Detection

`list_election_participants` already uses a `voter_filters_active` boolean to decide whether to execute the JOIN path or the default (VoterHistory-only) path. The current code includes `has_district_mismatch is not None` in the `voter_filters_active` check. Phase 9 extends the JOIN to also touch `analysis_results` when `has_district_mismatch` is active.

```python
# Current detection (voter_history_service.py:552-563)
voter_filters_active = any([
    q_terms,
    filters.county_precinct,
    ...
    filters.has_district_mismatch is not None,  # already triggers voter JOIN
])
```

A new boolean `mismatch_filter_active = filters.has_district_mismatch is not None` can further gate whether the `analysis_results` JOIN is needed (subset of `voter_filters_active`).

### Pattern: JSONB Containment Operator in SQLAlchemy

PostgreSQL's `@>` containment operator tests whether a JSONB column contains a given sub-structure. For an array column like `mismatch_details`, `mismatch_details @> '[{"boundary_type": "state_senate"}]'` returns true when any element in the array has that `boundary_type`.

**Option A — SQLAlchemy `cast` + `Comparator.contains` (recommended):**

```python
# Source: SQLAlchemy PostgreSQL dialect docs + GeoAlchemy2 cast pattern
from sqlalchemy import cast, type_coerce
from sqlalchemy.dialects.postgresql import JSONB

# has_district_mismatch=True: voter HAS a mismatch for this type
target = [{"boundary_type": district_type}]
mismatch_condition = AnalysisResult.mismatch_details.contains(
    type_coerce(target, JSONB)
)

# has_district_mismatch=False: voter has analysis but no mismatch for this type
no_mismatch_condition = ~AnalysisResult.mismatch_details.contains(
    type_coerce(target, JSONB)
)
```

**Option B — Raw `text()` predicate (simpler, always works):**

```python
from sqlalchemy import text, bindparam
import json

condition = text(
    "analysis_results.mismatch_details @> :target::jsonb"
).bindparams(target=json.dumps([{"boundary_type": district_type}]))
```

Option A is preferred because it keeps queries in ORM style consistent with the rest of `voter_history_service.py`. However, `JSONB.Comparator.contains()` on a `list`-typed column requires `type_coerce` to avoid the "can't adapt type 'list'" error. Both options produce identical SQL.

### Pattern: analysis_results JOIN for Mismatch Filter

The INNER JOIN to `analysis_results` using the `voter_id` FK gates the filter to analyzed voters only. Voters without an `analysis_results` row are excluded by the INNER JOIN semantics (satisfying the "excluded from mismatch filtering" requirement).

```python
from voter_api.models.analysis_result import AnalysisResult

# Extend the JOIN path query when mismatch_filter_active
query = query.join(
    AnalysisResult,
    AnalysisResult.voter_id == Voter.id,
)
count_query = count_query.join(
    AnalysisResult,
    AnalysisResult.voter_id == Voter.id,
)
```

Important: `analysis_results` has a UniqueConstraint on `(analysis_run_id, voter_id)` — a voter may have multiple rows if they have been analyzed in multiple runs. The JOIN must pick the latest result per voter to avoid multiplying rows. The safest approach is a subquery or DISTINCT ON, or using a lateral join. A simpler approach: use `DISTINCT ON (voter_id)` in a subquery to get the latest analysis result per voter, then join to that. Alternatively, since `match_status` and `mismatch_details` are updated in-place for each run (the `UPDATE voters SET has_district_mismatch = ...` pattern at `analysis_service.py:167-179` suggests results accumulate), the JOIN must deduplicate.

**Recommended deduplication approach:** Join on a subquery that selects the most-recent analysis result per voter:

```python
from sqlalchemy import select

latest_ar = (
    select(AnalysisResult)
    .distinct(AnalysisResult.voter_id)
    .order_by(AnalysisResult.voter_id, AnalysisResult.analyzed_at.desc())
    .subquery()
)
query = query.join(latest_ar, latest_ar.c.voter_id == Voter.id)
```

Or, if the project guarantees one analysis result per voter (one active run), a plain INNER JOIN is sufficient. Verify via the DB before deciding.

### Pattern: 422 Validation Error (consistent with FastAPI project conventions)

The existing pattern for 422s in this codebase uses `HTTPException(status_code=422, detail=...)` raised in the route handler after validating the election context:

```python
# In voter_history.py route handler
if filters.has_district_mismatch is not None:
    if not election.district_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="has_district_mismatch filter requires an election with a known district_type",
        )
    if election.district_type not in BOUNDARY_TYPE_TO_VOTER_FIELD:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"has_district_mismatch filter is not supported for district_type '{election.district_type}'",
        )
```

This validation requires the election to be fetched before calling the service function. The route handler currently calls the service which internally calls `_get_election_or_raise`. The cleanest approach: pass `district_type` into the service so validation can happen before the query, or let the service raise a new exception type that the route handler converts to 422.

### Pattern: Passing district_type Context into the Service

The service `list_election_participants` currently does not expose `district_type` to the caller. To support 422 from the route handler, the election must be fetched before the filter is applied. Two clean options:

- **Option A:** Route handler fetches election first via a new helper or direct query, validates, passes `district_type` as a parameter to the service function — requires changing the service signature.
- **Option B:** Service returns the election's `district_type` alongside results, and the route handler validates post-call — awkward.
- **Option C (recommended):** Service raises a new `ValueError` subclass (e.g., `MismatchFilterError`) when district_type is invalid/null, and the route handler converts it to 422 alongside the existing `ValueError → 404` handler.

This keeps the service as the owner of business logic, avoids duplicating the election fetch, and maintains the existing error-conversion pattern in the route handler.

### Pattern: mismatch_district_type in Response Metadata

`PaginatedElectionParticipationResponse` currently contains only `items` and `pagination`. The `mismatch_district_type` field belongs alongside `pagination` as top-level response metadata:

```python
class PaginatedElectionParticipationResponse(BaseModel):
    items: list[ElectionParticipationRecord]
    pagination: PaginationMeta
    mismatch_district_type: str | None = None  # set when has_district_mismatch filter used
```

The route handler sets this field from the election's `district_type` when the filter is active.

### Pattern: mismatch_count in ParticipationStatsResponse

```python
class ParticipationStatsResponse(BaseModel):
    election_id: UUID
    total_participants: int
    mismatch_count: int | None = None   # context-aware count; None if no district_type
    total_eligible_voters: int | None = None
    ...
```

`get_participation_stats` computes `mismatch_count` by counting rows in the same `analysis_results` JOIN used by `_apply_voter_filters`. Factor the JSONB condition into a utility so both paths reuse it.

### Anti-Patterns to Avoid

- **Joining analysis_results with LEFT JOIN when mismatch filter is active:** A LEFT JOIN returns all voters including unanalyzed, then you'd need a WHERE to filter them out. Use INNER JOIN to let the DB exclude unanalyzed rows naturally.
- **Using the blanket `Voter.has_district_mismatch` for `=false` context-aware queries:** The blanket flag says "any mismatch on any boundary type" — a voter might have `has_district_mismatch=True` globally but no mismatch on `state_senate`. Must use the JSONB check.
- **Not deduplicating analysis_results rows:** Multiple analysis runs produce multiple rows per voter. A plain INNER JOIN multiplies voter history rows. Always use `DISTINCT ON voter_id` + `ORDER BY analyzed_at DESC` or equivalent.
- **422 in service vs 422 in route:** The pattern for this codebase is that services raise `ValueError` and route handlers convert to `HTTPException`. Extend this pattern for the new 422 cases.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| JSONB array element containment | Custom Python-side filtering of JSONB data | PostgreSQL `@>` operator or `jsonb_array_elements` via SQLAlchemy |
| Deduplication of analysis_results | Application-side dedup after loading all rows | `DISTINCT ON (voter_id)` subquery in the JOIN |
| District type validation | Hard-coded string lists in route handler | `BOUNDARY_TYPE_TO_VOTER_FIELD` keys from `comparator.py` (already imported in service layer) |

**Key insight:** PostgreSQL's JSONB operators handle containment checks at the DB level with GIN index support. Fetching all analysis results and filtering in Python would be prohibitively expensive at scale and should never be done.

## Common Pitfalls

### Pitfall 1: Multiple analysis_results Rows per Voter

**What goes wrong:** `analysis_results` has a UniqueConstraint on `(analysis_run_id, voter_id)`, not just `voter_id`. A voter analyzed in 3 runs has 3 rows. An INNER JOIN without deduplication multiplies participation rows by 3, producing incorrect totals.

**Why it happens:** The analysis service (`analysis_service.py`) inserts one row per voter per run. No cleanup of old rows on re-run.

**How to avoid:** Use a subquery with `DISTINCT ON (voter_id) ORDER BY analyzed_at DESC` to get only the latest result per voter before joining. Verify against the live DB schema — a GIN index on `mismatch_details` would help performance.

**Warning signs:** Participation count suddenly 2x or 3x the expected value when filter is active.

### Pitfall 2: `has_district_mismatch=false` Semantics with Unanalyzed Voters

**What goes wrong:** When `has_district_mismatch=false`, the intent is "voters who participated and have NO mismatch on this district type." But unanalyzed voters also have no mismatch (trivially). The locked decision says both `=true` and `=false` must EXCLUDE unanalyzed voters.

**Why it happens:** A LEFT JOIN returns unanalyzed voters with NULL analysis data; `NULL @> '...'` is NULL (not false), so they'd slip through a NOT containment check.

**How to avoid:** INNER JOIN to `analysis_results` ensures only analyzed voters appear in either `=true` or `=false` results. For `=false`, use `NOT (mismatch_details @> target)` — but this also matches voters where `mismatch_details IS NULL` (matched on all boundaries). NULL mismatch_details means "match" (no mismatches), so those voters should appear in `=false` results. Use: `(mismatch_details IS NULL) OR NOT (mismatch_details @> target)`.

**Warning signs:** `has_district_mismatch=false` returns zero results even when most voters have clean analysis.

### Pitfall 3: Route Handler Double-Fetch of Election

**What goes wrong:** The route handler validates district_type before calling the service. The service also internally calls `_get_election_or_raise`. Two DB round-trips for the same election.

**How to avoid:** Use Option C (service raises a typed exception, route handler converts). The service fetches the election once and either proceeds or raises. The route handler catches both the `ValueError` (→ 404) and the new `MismatchFilterError` (→ 422).

### Pitfall 4: Forgetting the JOIN Path Branching in list_election_participants

**What goes wrong:** `list_election_participants` has two code paths — JOIN path and default path. The `analysis_results` JOIN only applies in the JOIN path (when `voter_filters_active` is True). If the JOIN path logic is added but the `voter_filters_active` detection is not updated, the query fails.

**How to avoid:** `has_district_mismatch is not None` already triggers `voter_filters_active = True`. The `analysis_results` JOIN is added inside the existing JOIN path branch. No change to the detection logic is needed — only the JOIN path body expands.

### Pitfall 5: E2E Test for mismatch_district_type Field

**What goes wrong:** The new `mismatch_district_type` field on the response is only present when `has_district_mismatch` is specified. If the E2E smoke test checks the participation response without the filter, it will not exercise this field.

**How to avoid:** Add a specific E2E smoke test that calls `?has_district_mismatch=true` on the seeded election (which has a `district_type`) and asserts `mismatch_district_type` is present in the response body.

## Code Examples

### JSONB Containment with SQLAlchemy 2.x

```python
# Source: SQLAlchemy PostgreSQL dialect documentation + project pattern (type_coerce in geocoding_service.py:1188)
import json
from sqlalchemy import type_coerce
from sqlalchemy.dialects.postgresql import JSONB

# Build target: list of one dict with the boundary_type key
target_value = [{"boundary_type": district_type}]

# has_district_mismatch=True: JSONB array contains an element with boundary_type
true_condition = AnalysisResult.mismatch_details.contains(
    type_coerce(target_value, JSONB)
)

# has_district_mismatch=False: no mismatch for this type (including voters where
# mismatch_details is NULL, meaning they matched on all boundaries)
false_condition = or_(
    AnalysisResult.mismatch_details.is_(None),
    ~AnalysisResult.mismatch_details.contains(type_coerce(target_value, JSONB)),
)
```

Note: `type_coerce` is already used in this codebase at `geocoding_service.py:1188` for JSONB array concatenation — the pattern is established.

### Latest analysis_results Subquery (deduplication)

```python
# Source: SQLAlchemy docs — DISTINCT ON with subquery
from sqlalchemy import select
from voter_api.models.analysis_result import AnalysisResult

# Subquery: latest analysis result per voter
latest_ar_subq = (
    select(AnalysisResult)
    .distinct(AnalysisResult.voter_id)
    .order_by(AnalysisResult.voter_id, AnalysisResult.analyzed_at.desc())
    .subquery("latest_ar")
)

# Join in the main query
query = query.join(latest_ar_subq, latest_ar_subq.c.voter_id == Voter.id)
```

### 422 Exception Pattern (new MismatchFilterError)

```python
# voter_history_service.py — new exception type
class MismatchFilterError(ValueError):
    """Raised when has_district_mismatch filter cannot be applied to this election."""
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

# voter_history.py — route handler conversion
try:
    results, total, voter_details_included = await voter_history_service.list_election_participants(...)
except voter_history_service.MismatchFilterError as exc:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc),
    ) from exc
except ValueError as exc:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Election not found",
    ) from exc
```

### mismatch_count in get_participation_stats

```python
# voter_history_service.py — get_participation_stats addition
mismatch_count: int | None = None
if election.district_type and election.district_type in BOUNDARY_TYPE_TO_VOTER_FIELD:
    target_value = [{"boundary_type": election.district_type}]
    latest_ar_subq = ...  # same dedup subquery
    mismatch_result = await session.execute(
        select(func.count(VoterHistory.id))
        .where(*base_where)
        .join(Voter, VoterHistory.voter_registration_number == Voter.voter_registration_number)
        .join(latest_ar_subq, latest_ar_subq.c.voter_id == Voter.id)
        .where(latest_ar_subq.c.mismatch_details.contains(type_coerce(target_value, JSONB)))
    )
    mismatch_count = mismatch_result.scalar_one()
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Blanket `Voter.has_district_mismatch` boolean | JSONB lookup on `analysis_results.mismatch_details` for specific district type | Accurate scoped mismatch reporting; slightly higher query cost (JSONB JOIN), acceptable at election scale |

## Open Questions

1. **Does `analysis_results` guarantee at most one row per voter per run?**
   - What we know: `UniqueConstraint("analysis_run_id", "voter_id")` ensures uniqueness per run. Multiple completed runs produce multiple rows.
   - What's unclear: How many completed runs exist in practice? Is there a cleanup step?
   - Recommendation: Check `SELECT voter_id, COUNT(*) FROM analysis_results GROUP BY voter_id HAVING COUNT(*) > 1` via MCP before deciding whether to use the dedup subquery or a plain INNER JOIN.

2. **Should `mismatch_district_type` be a top-level field or nested inside pagination?**
   - What we know: The decision is to include it alongside pagination as response metadata. Current `PaginatedElectionParticipationResponse` has `items` and `pagination`.
   - What's unclear: Whether to nest in a new `metadata` dict or add as a top-level optional field.
   - Recommendation: Top-level optional field is simpler and consistent with how `pagination` is already a top-level sibling of `items`. No new nesting needed.

3. **GIN index on mismatch_details?**
   - What we know: No GIN index exists on `analysis_results.mismatch_details`. PostgreSQL JSONB `@>` containment benefits significantly from a GIN index on large datasets.
   - What's unclear: How many rows are in `analysis_results` in the dev/prod databases?
   - Recommendation: Claude's discretion per CONTEXT.md. For planning: include an optional migration or note that a GIN index can be added without a schema-breaking migration using `CREATE INDEX CONCURRENTLY`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (async: pytest-asyncio) |
| Config file | `pyproject.toml` (pytest section) |
| Quick run command | `uv run pytest tests/unit/test_services/test_voter_history_service.py tests/unit/test_schemas/test_voter_history_schemas.py -x` |
| Full suite command | `uv run pytest tests/ -x --ignore=tests/e2e` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MISMATCH-01 | `has_district_mismatch=true` filters by election's district_type via JSONB | unit | `uv run pytest tests/unit/test_services/test_voter_history_service.py -k "mismatch" -x` | ❌ Wave 0 |
| MISMATCH-01 | `has_district_mismatch=false` excludes mismatched AND unanalyzed voters | unit | `uv run pytest tests/unit/test_services/test_voter_history_service.py -k "mismatch_false" -x` | ❌ Wave 0 |
| MISMATCH-01 | null `district_type` raises 422 | integration | `uv run pytest tests/integration/test_voter_history_api.py -k "mismatch_null_district_type" -x` | ❌ Wave 0 |
| MISMATCH-01 | unknown `district_type` raises 422 | integration | `uv run pytest tests/integration/test_voter_history_api.py -k "mismatch_unknown_district_type" -x` | ❌ Wave 0 |
| MISMATCH-01 | omitting filter returns unmodified results (no regression) | integration | `uv run pytest tests/integration/test_voter_history_api.py -k "participation" -x` | ✅ (existing) |
| MISMATCH-01 | `mismatch_count` present in stats response | unit | `uv run pytest tests/unit/test_services/test_voter_history_service.py -k "stats" -x` | ✅ (extend) |
| MISMATCH-01 | `mismatch_district_type` in response metadata | integration | `uv run pytest tests/integration/test_voter_history_api.py -k "mismatch_district_type" -x` | ❌ Wave 0 |
| MISMATCH-01 | E2E: context-aware filter on real election | e2e | `uv run pytest tests/e2e/test_smoke.py::TestVoterHistory -x` | ✅ (extend) |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/unit/test_services/test_voter_history_service.py tests/unit/test_schemas/test_voter_history_schemas.py -x`
- **Per wave merge:** `uv run pytest tests/ -x --ignore=tests/e2e`
- **Phase gate:** Full suite green (including e2e) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/unit/test_services/test_voter_history_service.py` — add test methods for JSONB mismatch filter (true/false/unanalyzed exclusion, 422 paths) — file exists, extend class
- [ ] `tests/integration/test_voter_history_api.py` — add test methods for 422 on null/unknown district_type and `mismatch_district_type` field in response — file exists, extend class
- [ ] `tests/e2e/test_smoke.py::TestVoterHistory` — add smoke test for `?has_district_mismatch=true` with `mismatch_district_type` field assertion — file exists, extend class

---

## Sources

### Primary (HIGH confidence)

- Source code: `src/voter_api/services/voter_history_service.py` — full service implementation read; exact lines documented above
- Source code: `src/voter_api/lib/analyzer/comparator.py` — `mismatch_details` structure, `BOUNDARY_TYPE_TO_VOTER_FIELD` keys
- Source code: `src/voter_api/models/analysis_result.py` — JSONB column definition, constraints
- Source code: `src/voter_api/models/election.py` — `district_type` field definition (line 72)
- Source code: `src/voter_api/schemas/voter_history.py` — all schema definitions to be modified
- Source code: `src/voter_api/api/v1/voter_history.py` — route handler structure
- Source code: `src/voter_api/services/geocoding_service.py:1188` — `type_coerce([], JSONB_TYPE)` pattern in project
- Test files: `tests/unit/test_services/test_voter_history_service.py`, `tests/integration/test_voter_history_api.py`, `tests/e2e/test_smoke.py` — existing test structure

### Secondary (MEDIUM confidence)

- SQLAlchemy 2.x PostgreSQL dialect: `JSONB.Comparator.contains()` and `type_coerce` usage documented in official SQLAlchemy docs (https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.JSONB)
- PostgreSQL JSONB `@>` operator: standard operator for array containment; GIN index support well-documented

### Tertiary (LOW confidence)

- None for this phase.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all changes use existing project patterns
- Architecture: HIGH — full source code read; exact integration points identified
- Pitfalls: HIGH — derived directly from reading live code, model constraints, and query structure
- JSONB operator approach: MEDIUM — SQLAlchemy JSONB containment is well-documented but `type_coerce` behavior on list-typed columns should be verified during implementation

**Research date:** 2026-03-16
**Valid until:** 2026-06-16 (stable stack — PostgreSQL JSONB operators and SQLAlchemy 2.x JSONB API are mature)
