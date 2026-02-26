# Research: 013-batch-boundary-check

## Question 1: How are voter district assignments stored?

**Decision**: District assignments are stored as **scalar columns on the `Voter` model** (not a separate `voter_districts` table). Fields like `congressional_district`, `state_senate_district`, `state_house_district`, `county_precinct`, etc. — 15 types total — are mapped in `BOUNDARY_TYPE_TO_VOTER_FIELD` in `lib/analyzer/comparator.py`.

**Implication**: The proposed SQL using `voter_districts` table in the user prompt doesn't exist. Instead: load the voter, call `extract_registered_boundaries(voter)` to get `dict[str, str]` (boundary_type → identifier), then query the `boundaries` table WHERE `(boundary_type, boundary_identifier) IN (...)`.

**Rationale**: Consistent with existing `check_voter_districts` pattern. `extract_registered_boundaries()` already handles all 15 boundary types and skips null fields.

---

## Question 2: What is the correct CROSS JOIN pattern in SQLAlchemy 2.x async?

**Decision**: Use an implicit cross join via a bare `select()` from two tables without a `.join()` clause. SQLAlchemy renders this as `FROM geocoded_locations, boundaries WHERE ...`. This is the standard cartesian-product-with-filter pattern.

```python
stmt = (
    select(
        GeocodedLocation.source_type,
        GeocodedLocation.latitude,
        GeocodedLocation.longitude,
        Boundary.id.label("boundary_id"),
        Boundary.boundary_type,
        Boundary.boundary_identifier,
        func.ST_Contains(Boundary.geometry, GeocodedLocation.point).label("is_contained"),
    )
    .where(
        GeocodedLocation.voter_id == voter_id,
        Boundary.id.in_(boundary_ids),
    )
    .order_by(GeocodedLocation.source_type, Boundary.boundary_type)
)
```

**Rationale**: The GiST index on `boundaries.geometry` (`ix_boundaries_geometry`, line 59 of `boundary.py`) makes `ST_Contains` fast. With typical data (≤10 providers × ≤10 districts = ≤100 point-in-polygon checks), this is a single round-trip with no N+1 risk.

**Alternatives considered**:
- Multiple `find_boundaries_for_point()` calls per provider — N+1, rejected
- Raw SQL — violates "no raw SQL in application code" constitution rule, rejected

---

## Question 3: How should missing boundary geometry be handled (FR-008)?

**Decision**: After fetching the cross-join results, compare the set of `boundary_type+identifier` pairs returned by the DB query against the full registered set from `extract_registered_boundaries()`. Any registered district with no matching `boundaries` table row gets a `DistrictBoundaryResult` with `has_geometry=False` and an empty `providers` list.

**Rationale**: The cross-join naturally excludes unloaded boundaries (they have no rows in `boundaries`). The gap is filled at the Python layer by a post-query reconciliation step. This avoids nullable SQL joins and keeps the query simple.

---

## Question 4: Should `validate_georgia_coordinates()` be added to `set_official_location_override()`?

**Decision**: Yes. The function exists at `lib/geocoder/point_lookup.py` and is already used by geocoding flows. The `set_official_location_override()` service at `geocoding_service.py:1056-1090` does **not** call it, allowing worldwide coordinates to be stored as the voter's official location — a clear security gap.

**Implementation**: Call `validate_georgia_coordinates(latitude, longitude)` at the top of `set_official_location_override()`, before any DB work. Raise `ValueError` on failure (the API layer maps `ValueError` → 422 in the location override route).

**Alternatives considered**:
- Validate in the Pydantic schema (`SetOfficialLocationRequest`) — possible, but validation belongs in the service layer to stay consistent with the existing pattern (geocoding service validates there, not in schemas). Also, the schema can't import the library without creating a circular or unusual dependency.

---

## Question 5: Where should the new library function live?

**Decision**: New file `src/voter_api/lib/analyzer/batch_check.py` — alongside `spatial.py` and `comparator.py`. The analyzer library's `__init__.py` will export the new public function.

**Rationale**: Library-first constitution (Principle I). The batch check is spatially analytical, co-located with existing spatial query functions. The library function takes `(session, voter_id)` and returns a plain dataclass/dict structure — independently testable without FastAPI or service context.

---

## Question 6: Where does the new endpoint live — voters router or geocoding router?

**Decision**: **Voters router** (`api/v1/voters.py`), at path `POST /api/v1/voters/{voter_id}/geocode/check-boundaries`.

**Rationale**: The subject is the voter. The path mirrors the user prompt spec and the existing `GET /voters/{voter_id}/district-check` pattern. The endpoint uses the voter's geocoded locations as inputs but doesn't perform any geocoding — it's a read-only comparison.

---

## Question 7: Why POST for a read-only operation?

**Decision**: Accept the user's specified `POST` method. The endpoint takes no request body (path param only), so `GET` would be equally valid semantically. However, matching the user's spec minimizes divergence from their frontend integration plan.

**Alternatives considered**: `GET` — more RESTful for idempotent reads, but the user explicitly specified `POST` with `require_role("admin")` as a trigger action. Keeping `POST` preserves the spec.

---

## Summary of Design Decisions

| Concern | Decision |
|---|---|
| Voter district storage | Scalar columns on Voter, use `extract_registered_boundaries()` |
| SQL approach | Implicit CROSS JOIN via bare `select()` from two tables |
| Missing boundary handling | Post-query reconciliation at Python layer |
| Georgia validation | Add to `set_official_location_override()` service |
| Library location | `lib/analyzer/batch_check.py` |
| Router | `api/v1/voters.py` |
| HTTP method | POST (per spec) |
| New migrations | None required |
| New models | None required |
