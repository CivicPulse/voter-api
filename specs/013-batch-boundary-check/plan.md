# Implementation Plan: Batch Boundary Check

**Branch**: `013-batch-boundary-check` | **Date**: 2026-02-26 | **Spec**: `specs/013-batch-boundary-check/spec.md`

## Summary

Add `POST /api/v1/voters/{voter_id}/geocode/check-boundaries` — an admin-only endpoint that cross-joins every geocoded location for a voter against all their registered district boundaries using PostGIS `ST_Contains`, returning the inside/outside result per provider × district in a single query. Also fixes a security gap: `set_official_location_override()` will validate Georgia coordinate bounds before accepting an admin location override.

No new database tables or Alembic migrations are needed. All data is read from existing `geocoded_locations`, `voters`, and `boundaries` tables.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async, GeoAlchemy2, PostGIS `ST_Contains`, Pydantic v2
**Storage**: PostgreSQL + PostGIS (existing tables only — no migrations)
**Testing**: pytest + pytest-asyncio; unit (SQLite/mock), integration (mock session), E2E (real PostGIS)
**Target Platform**: Linux server (existing deployment)
**Performance Goals**: ≤2s for up to 10 providers × 10 districts (SC-002); single SQL round-trip via CROSS JOIN
**Constraints**: No full-table geometry scans (FR-011); GiST index on `boundaries.geometry` already exists
**Scale/Scope**: Single voter at a time; typical: 2–5 providers × 5–10 districts = ≤50 ST_Contains evaluations

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Library-First | ✅ PASS | Core logic in `lib/analyzer/batch_check.py`; independently testable |
| II. Code Quality | ✅ PASS | Type hints, Google docstrings, ruff before commit |
| III. Testing Discipline | ✅ PASS | Unit + integration + E2E smoke tests; coverage ≥90% maintained |
| IV. 12-Factor Config | ✅ PASS | No new config variables; reads from existing DB |
| V. Developer Experience | ✅ PASS | No new setup steps; uses existing docker-compose |
| VI. API Documentation | ✅ PASS | Pydantic schemas → OpenAPI auto-generated; contract in `contracts/openapi-patch.yaml` |
| VII. Security by Design | ✅ PASS | `require_role("admin")` enforced; Georgia validation added to location override |
| VIII. CI/CD | ✅ PASS | Existing CI pipeline; no new workflows needed |

**Complexity Tracking**: No violations. Zero new models, zero migrations, no new config.

## Project Structure

### Documentation (this feature)

```text
specs/013-batch-boundary-check/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/
│   └── openapi-patch.yaml   ← Phase 1 output
└── tasks.md             ← Phase 2 output (via /speckit.tasks — not yet created)
```

### Source Code

```text
src/voter_api/
├── lib/
│   └── analyzer/
│       ├── __init__.py              (modify — export check_batch_boundaries)
│       └── batch_check.py           (NEW — core library function)
├── schemas/
│   └── voter.py                    (modify — add 4 new Pydantic models)
├── services/
│   ├── voter_service.py            (modify — add check_batch_boundaries_for_voter())
│   └── geocoding_service.py        (modify — add Georgia validation to set_official_location_override)
└── api/
    └── v1/
        └── voters.py               (modify — add new POST route)

tests/
├── unit/
│   └── lib/
│       └── test_analyzer/
│           └── test_batch_check.py  (NEW)
├── integration/
│   └── api/
│       └── test_voters.py          (modify — add batch boundary test cases)
└── e2e/
    └── test_smoke.py               (modify — add smoke test for new endpoint)
```

**Structure Decision**: Single-project layout (existing). All changes are additive to existing modules; no new top-level directories.

---

## Phase 0: Research

**Status**: Complete — see `research.md`

Key findings:
1. Voter district assignments are **scalar columns on `Voter`** (not a `voter_districts` table). Use `extract_registered_boundaries(voter)` from `lib/analyzer/comparator.py`.
2. CROSS JOIN in SQLAlchemy 2.x: bare `select()` from two tables → `FROM geocoded_locations, boundaries WHERE ...`
3. Missing boundaries: handled at Python layer post-query (registered districts with no matching `boundaries` row get `has_geometry=False`)
4. Georgia validation: add `validate_georgia_coordinates()` call at top of `set_official_location_override()`
5. HTTP method: POST per spec; no request body

---

## Phase 1: Design & Contracts

**Status**: Complete

### Library: `lib/analyzer/batch_check.py`

Public function:

```python
async def check_batch_boundaries(
    session: AsyncSession,
    voter_id: uuid.UUID,
) -> BatchBoundaryCheckResult:
    """Cross-join all geocoded locations for a voter against their registered district boundaries.

    Args:
        session: Async database session.
        voter_id: UUID of the voter to check.

    Returns:
        BatchBoundaryCheckResult dataclass with districts list and provider_summary.

    Raises:
        VoterNotFoundError: If no voter with the given ID exists.
    """
```

Internal steps:
1. Load `Voter` by `voter_id` — raise `VoterNotFoundError` if missing
2. Call `extract_registered_boundaries(voter)` → `dict[str, str]`
3. If no registered districts: return empty result
4. Query `boundaries` WHERE `(boundary_type, boundary_identifier) IN (...)` → get boundary rows + IDs
5. Query `geocoded_locations` WHERE `voter_id = :voter_id` → get all provider locations
6. If no geocoded locations: return result with `total_locations=0`, districts populated with `has_geometry` status
7. Execute CROSS JOIN with `ST_Contains` → list of `(source_type, lat, lng, boundary_id, boundary_type, boundary_identifier, is_contained)` rows
8. Aggregate into `DistrictBoundaryResult` list (grouped by district)
9. Compute `ProviderSummary` list (count matches per provider)
10. Reconcile missing boundaries (registered districts with no DB row) → add `has_geometry=False` entries

### Service: `voter_service.check_batch_boundaries_for_voter()`

Thin orchestration layer — calls the library function, maps `VoterNotFoundError` to `None` (API layer returns 404).

### API Route

```python
@voters_router.post(
    "/{voter_id}/geocode/check-boundaries",
    response_model=BatchBoundaryCheckResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def check_voter_batch_boundaries(
    voter_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BatchBoundaryCheckResponse:
```

### Security Fix

```python
# geocoding_service.py — set_official_location_override()
# ADD before the DB write (line ~1082):
from voter_api.lib.geocoder.point_lookup import validate_georgia_coordinates
validate_georgia_coordinates(latitude, longitude)  # raises ValueError on failure
```

The `PUT /voters/{voter_id}/official-location` route already maps `ValueError` to HTTP 422 via its exception handler.

---

## Artifacts

| Artifact | Path | Status |
|---|---|---|
| Research | `specs/013-batch-boundary-check/research.md` | ✅ Done |
| Data model | `specs/013-batch-boundary-check/data-model.md` | ✅ Done |
| API contract | `specs/013-batch-boundary-check/contracts/openapi-patch.yaml` | ✅ Done |
| Quickstart | `specs/013-batch-boundary-check/quickstart.md` | ✅ Done |
| Tasks | `specs/013-batch-boundary-check/tasks.md` | ✅ Done |
