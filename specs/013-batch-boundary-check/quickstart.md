# Quickstart: 013-batch-boundary-check

## What this feature adds

1. **`POST /api/v1/voters/{voter_id}/geocode/check-boundaries`** — Admin-only endpoint that checks every geocoded location on file for a voter against all their registered district boundaries. Returns the inside/outside result for every provider × district combination in one response.

2. **Security fix**: `set_official_location_override()` now validates that supplied coordinates fall within Georgia's bounding box before saving.

## Prerequisites

- Running PostGIS dev database (via `docker compose up -d db`)
- Migrations applied: `uv run voter-api db upgrade`
- At least one voter with geocoded locations and district assignments in the DB

## Running the new endpoint

```bash
# Authenticate
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin@example.com","password":"changeme"}' | jq -r .access_token)

# Run batch boundary check for a voter
curl -s -X POST \
  http://localhost:8000/api/v1/voters/{voter_id}/geocode/check-boundaries \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### Example Response

```json
{
  "voter_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "districts": [
    {
      "boundary_id": "d1e2f3a4-b5c6-7890-abcd-ef1234567890",
      "boundary_type": "congressional",
      "boundary_identifier": "7",
      "has_geometry": true,
      "providers": [
        { "source_type": "census", "is_contained": true },
        { "source_type": "nominatim", "is_contained": false }
      ]
    },
    {
      "boundary_id": null,
      "boundary_type": "state_senate",
      "boundary_identifier": "42",
      "has_geometry": false,
      "providers": []
    }
  ],
  "provider_summary": [
    {
      "source_type": "census",
      "latitude": 33.748,
      "longitude": -84.387,
      "confidence_score": 0.95,
      "districts_matched": 3,
      "districts_checked": 4
    }
  ],
  "total_locations": 2,
  "total_districts": 5,
  "checked_at": "2026-02-26T12:00:00Z"
}
```

### Edge case responses

**Voter has no geocoded locations** (200, not an error):
```json
{
  "voter_id": "...",
  "districts": [
    { "boundary_type": "congressional", "boundary_identifier": "7", "has_geometry": true, "providers": [] },
    { "boundary_type": "state_senate", "boundary_identifier": "42", "has_geometry": false, "providers": [] }
  ],
  "provider_summary": [],
  "total_locations": 0,
  "total_districts": 2,
  "checked_at": "..."
}
```

**Voter not found** → 404

**Non-admin user** → 403

## Running tests

```bash
# All tests
uv run pytest

# Unit tests for the new library function only
uv run pytest tests/unit/lib/test_analyzer/test_batch_check.py -v

# Integration tests for the new endpoint
uv run pytest tests/integration/api/test_voters.py -k "batch_boundary" -v

# E2E smoke tests (requires running PostGIS)
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  ELECTION_REFRESH_ENABLED=false \
  uv run pytest tests/e2e/ -v -k "batch_boundary"

# Lint
uv run ruff check . && uv run ruff format --check .
```

## Files changed by this feature

### New files
| File | Purpose |
|---|---|
| `src/voter_api/lib/analyzer/batch_check.py` | Library: cross-join spatial query + result aggregation |
| `tests/unit/lib/test_analyzer/test_batch_check.py` | Unit tests for library function |

### Modified files
| File | Change |
|---|---|
| `src/voter_api/lib/analyzer/__init__.py` | Export `check_batch_boundaries` |
| `src/voter_api/schemas/voter.py` | Add `ProviderResult`, `DistrictBoundaryResult`, `ProviderSummary`, `BatchBoundaryCheckResponse` |
| `src/voter_api/services/voter_service.py` | Add `check_batch_boundaries_for_voter()` service function |
| `src/voter_api/api/v1/voters.py` | Add `POST /{voter_id}/geocode/check-boundaries` route |
| `src/voter_api/services/geocoding_service.py` | Add Georgia validation to `set_official_location_override()` |
| `tests/integration/api/test_voters.py` | Integration tests for new endpoint |
| `tests/e2e/test_smoke.py` | Smoke tests for new endpoint |

## Security fix details

`set_official_location_override(session, voter_id, latitude, longitude)` in `geocoding_service.py` previously accepted any worldwide coordinates. After this fix, it calls `validate_georgia_coordinates(latitude, longitude)` before writing to the DB. Invalid coordinates raise `ValueError`, which the API layer maps to HTTP 422.

```python
# Before (geocoding_service.py:1082)
point = from_shape(Point(longitude, latitude), srid=4326)

# After
from voter_api.lib.geocoder.point_lookup import validate_georgia_coordinates
validate_georgia_coordinates(latitude, longitude)  # raises ValueError if out of bounds
point = from_shape(Point(longitude, latitude), srid=4326)
```
