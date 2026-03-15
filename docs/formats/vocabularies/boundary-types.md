# Boundary Types Vocabulary

This document lists all valid `boundary_type` values used in the voter-api system. These values identify the type of geographic boundary (district) that an elected office represents.

**Authoritative source:** The canonical list is defined in `src/voter_api/models/boundary.py::BOUNDARY_TYPES`. This document reflects the Phase 1 snapshot. Always check the model for the current list.

## Values

### Federal Scope

| Value | Name | Description |
|-------|------|-------------|
| `congressional` | Congressional District | U.S. House of Representatives district |
| `us_senate` | U.S. Senate | Statewide boundary for U.S. Senate seats |

### State Scope

| Value | Name | Description |
|-------|------|-------------|
| `state_senate` | State Senate District | Georgia State Senate district |
| `state_house` | State House District | Georgia State House of Representatives district |
| `judicial` | Judicial Circuit | Judicial circuit boundary (Superior Court, State Court) |
| `psc` | Public Service Commission District | Georgia Public Service Commission district |

### County Scope

| Value | Name | Description |
|-------|------|-------------|
| `county` | County | County boundary (also used for countywide at-large seats) |
| `county_commission` | County Commission District | County commission district boundary |
| `school_board` | School Board District | County board of education district boundary |
| `county_precinct` | County Precinct | County-level voting precinct |
| `super_council` | Super Council District | Consolidated government council district (super district) |
| `super_commissioner` | Super Commissioner District | Consolidated government commissioner district (super district) |
| `super_school_board` | Super School Board District | Consolidated government school board district (super district) |
| `fire_district` | Fire District | Fire service district boundary |

### Municipal Scope

| Value | Name | Description |
|-------|------|-------------|
| `city_council` | City Council District | Municipal city council district |
| `municipal_school_board` | Municipal School Board District | Municipal school board district |
| `water_board` | Water Board District | Water authority district boundary |
| `municipal_precinct` | Municipal Precinct | Municipal-level voting precinct |

## Usage in the Body/Seat Reference System

Boundary types do **not** appear directly in markdown election files. Instead, the converter resolves `boundary_type` from the Body/Seat reference system:

1. Contest markdown files contain **Body** and **Seat** metadata (e.g., `Body: bibb-boe`, `Seat: post-7`)
2. County reference files (`data/states/GA/counties/{county}.md`) map Body IDs to their `boundary_type` in the Governing Bodies table
3. The converter looks up the Body ID in the county reference file to resolve the `boundary_type`

If a Body ID from a contest file is not found in the corresponding county reference file, the converter emits a validation error (strict mode -- no fallback).

## Scope Groupings for Statewide/Federal Contests

For statewide and federal contests, the Body/Seat system uses state-scoped Body IDs that map to well-known boundary types:

| Body ID Pattern | Resolves To |
|-----------------|-------------|
| `ga-governor`, `ga-lt-governor`, `ga-sos`, `ga-ag`, etc. | Statewide office (no district boundary) |
| `ga-us-senate` | `us_senate` |
| `ga-us-house` | `congressional` |
| `ga-state-senate` | `state_senate` |
| `ga-state-house` | `state_house` |
| `ga-psc` | `psc` |

## Notes

- All values are lowercase with underscores (snake_case)
- Values must match the database constraint exactly -- no human-friendly aliases or mapping layers
- New boundary types may be added to the `BOUNDARY_TYPES` list in the model as needed; this document should be updated to reflect any additions
- The total count at Phase 1 is **18 boundary types**
