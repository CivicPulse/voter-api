# Data Model: 013-batch-boundary-check

## Overview

This feature adds a **read-only** endpoint. No new database tables, columns, or Alembic migrations are required. The implementation reads from three existing tables:

| Table | Used For |
|---|---|
| `voters` | Load voter record; extract registered district columns |
| `geocoded_locations` | All provider results (one per `source_type`) for the voter |
| `boundaries` | Boundary geometry polygons, matched by `(boundary_type, boundary_identifier)` |

---

## Existing Tables (read-only access)

### `geocoded_locations`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `voter_id` | UUID FK | Filter by this |
| `source_type` | VARCHAR(50) | Provider name: "census", "nominatim", "google", "manual", etc. |
| `latitude` | DOUBLE | Included in response |
| `longitude` | DOUBLE | Included in response |
| `point` | GEOMETRY(POINT, 4326) | Used for ST_Contains; PostGIS WKBElement |
| `confidence_score` | DOUBLE nullable | Included in provider summary |
| `is_primary` | BOOLEAN | Not used in this feature (we take ALL locations) |

**Unique constraint**: `(voter_id, source_type)` — one record per provider per voter, so "most recent per provider" is already enforced by the table design.

### `voters` (district columns)

All registered district values are scalar columns on the `Voter` model. The mapping is defined in `lib/analyzer/comparator.py:BOUNDARY_TYPE_TO_VOTER_FIELD`:

| `boundary_type` | Voter field | Example value |
|---|---|---|
| `congressional` | `congressional_district` | `"7"` |
| `state_senate` | `state_senate_district` | `"42"` |
| `state_house` | `state_house_district` | `"097"` |
| `county_precinct` | `county_precinct` | `"08F"` |
| `municipal_precinct` | `municipal_precinct` | `"3A"` |
| `judicial` | `judicial_district` | `"4"` |
| `county_commission` | `county_commission_district` | `"2"` |
| `school_board` | `school_board_district` | `"5"` |
| `city_council` | `city_council_district` | `"3"` |
| `municipal_school_board` | `municipal_school_board_district` | `"1"` |
| `water_board` | `water_board_district` | `"6"` |
| `super_council` | `super_council_district` | `"1"` |
| `super_commissioner` | `super_commissioner_district` | `"2"` |
| `super_school_board` | `super_school_board_district` | `"3"` |
| `fire_district` | `fire_district` | `"B"` |

### `boundaries`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Included in response as `boundary_id` |
| `boundary_type` | VARCHAR(50) | Matched against voter's registered district types |
| `boundary_identifier` | VARCHAR(50) | Matched against voter's registered district values |
| `geometry` | GEOMETRY(MULTIPOLYGON, 4326) | Used in ST_Contains; GiST indexed |

**GiST index**: `ix_boundaries_geometry` — ensures ST_Contains is fast (no full table scan).

---

## Core Query

The batch boundary check executes this conceptual query:

```sql
-- Step 1: find boundary IDs for voter's registered districts
-- (done in Python via extract_registered_boundaries + Boundary query)

-- Step 2: CROSS JOIN geocoded_locations × matched boundaries
SELECT
    gl.source_type,
    gl.latitude,
    gl.longitude,
    b.id           AS boundary_id,
    b.boundary_type,
    b.boundary_identifier,
    ST_Contains(b.geometry, gl.point) AS is_contained
FROM
    geocoded_locations gl,
    boundaries b
WHERE
    gl.voter_id = :voter_id
    AND b.id IN (:boundary_id_1, :boundary_id_2, ...)
ORDER BY
    gl.source_type, b.boundary_type;
```

For a voter with 5 geocoded locations and 5 district boundaries, this is 25 ST_Contains evaluations in one round-trip.

---

## Response Schema (new Pydantic models)

Location: `src/voter_api/schemas/voter.py` (add below existing district-check schemas)

### `ProviderResult`

```python
class ProviderResult(BaseModel):
    source_type: str          # "census", "nominatim", etc.
    is_contained: bool        # True if point falls inside the boundary polygon
```

### `DistrictBoundaryResult`

```python
class DistrictBoundaryResult(BaseModel):
    boundary_id: UUID | None          # None if no boundary geometry loaded
    boundary_type: str                # "congressional", "state_senate", etc.
    boundary_identifier: str          # "7", "42", etc.
    has_geometry: bool                # False if boundary not in DB (FR-008)
    providers: list[ProviderResult]   # Empty if has_geometry=False
```

### `ProviderSummary`

```python
class ProviderSummary(BaseModel):
    source_type: str          # Provider name
    latitude: float
    longitude: float
    confidence_score: float | None
    districts_matched: int    # Count where is_contained=True
    districts_checked: int    # Total districts with geometry
```

### `BatchBoundaryCheckResponse`

```python
class BatchBoundaryCheckResponse(BaseModel):
    voter_id: UUID
    districts: list[DistrictBoundaryResult]   # Grouped by district (FR-007)
    provider_summary: list[ProviderSummary]   # Per-provider totals (FR-012)
    total_locations: int
    total_districts: int
    checked_at: datetime
```

---

## Security Fix (in-scope)

`geocoding_service.set_official_location_override()` at line 1056 currently accepts any worldwide coordinates. Add a `validate_georgia_coordinates(latitude, longitude)` call from `lib/geocoder/point_lookup.py` before the DB write. Raises `ValueError` on failure → FastAPI returns 422.

---

## Migration

**None required.** All tables already exist with the correct columns and indexes.
