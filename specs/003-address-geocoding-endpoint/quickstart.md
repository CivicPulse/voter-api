# Quickstart: Address Geocoding Endpoints

**Feature**: 003-address-geocoding-endpoint

## Prerequisites

- Running voter-api instance with PostGIS database
- At least one boundary dataset imported (for point-lookup testing)
- A valid JWT token (any role: viewer, analyst, or admin)

## Setup

The feature builds on existing infrastructure with one new table:
- **`addresses` table** *(new)* — canonical address store, created by this feature's migration
- Geocoder cache table (from feature 001) — modified to add `address_id` FK
- Voters table (from feature 001) — modified to add `residence_address_id` FK
- Boundary polygons (from feature 001)
- JWT authentication (from feature 001)

After implementation, run the migrations to create the addresses table and add FK columns:

```bash
uv run voter-api db upgrade
```

Optionally, backfill existing geocoder cache entries and voter records with address links:

```bash
# Backfill runs as a background task (idempotent, safe to re-run)
uv run voter-api db upgrade  # data migration included
```

## Obtaining a JWT Token

```bash
# Login to get a token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=<your-password>"

# Extract the access_token from the response
export TOKEN="<access_token_from_response>"
```

## Endpoint 1: Geocode an Address

Geocode a freeform street address to geographic coordinates.

```bash
# Geocode a valid Georgia address
curl -s "http://localhost:8000/api/v1/geocoding/geocode?address=100+Peachtree+St+NW,+Atlanta,+GA+30303" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**Expected response** (200):
```json
{
  "formatted_address": "100 PEACHTREE ST NW, ATLANTA, GA 30303",
  "latitude": 33.7589985,
  "longitude": -84.3879824,
  "confidence": 1.0,
  "metadata": {
    "cached": false,
    "provider": "census"
  }
}
```

**Error cases**:
```bash
# Empty address → 422
curl -s "http://localhost:8000/api/v1/geocoding/geocode?address=" \
  -H "Authorization: Bearer $TOKEN"

# Unmatchable address → 404
curl -s "http://localhost:8000/api/v1/geocoding/geocode?address=99999+Nonexistent+Rd,+Nowhere,+GA+00000" \
  -H "Authorization: Bearer $TOKEN"

# No auth → 401
curl -s "http://localhost:8000/api/v1/geocoding/geocode?address=100+Main+St"
```

## Endpoint 2: Verify/Autocomplete an Address

Submit a partial or malformed address for validation feedback and autocomplete suggestions.

```bash
# Partial address with autocomplete
curl -s "http://localhost:8000/api/v1/geocoding/verify?address=100+Peachtree" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**Expected response** (200):
```json
{
  "input_address": "100 Peachtree",
  "normalized_address": "100 PEACHTREE",
  "is_well_formed": false,
  "validation": {
    "present_components": ["street_number", "street_name"],
    "missing_components": ["city", "state", "zip"],
    "malformed_components": []
  },
  "suggestions": [
    {
      "address": "100 PEACHTREE ST NW, ATLANTA, GA 30303",
      "latitude": 33.7589985,
      "longitude": -84.3879824,
      "confidence_score": 1.0
    }
  ]
}
```

```bash
# Malformed address with abbreviation normalization
curl -s "http://localhost:8000/api/v1/geocoding/verify?address=100+main+street,+atlanta" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# Too short for suggestions (< 5 chars)
curl -s "http://localhost:8000/api/v1/geocoding/verify?address=100" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

## Endpoint 3: Point Lookup (District Identification)

Submit coordinates to find all boundary districts containing that point.

```bash
# Downtown Atlanta
curl -s "http://localhost:8000/api/v1/geocoding/point-lookup?lat=33.749&lng=-84.388" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**Expected response** (200):
```json
{
  "latitude": 33.749,
  "longitude": -84.388,
  "accuracy": null,
  "districts": [
    {
      "boundary_type": "county",
      "name": "Fulton",
      "boundary_identifier": "13121",
      "boundary_id": "...",
      "metadata": {"STATEFP": "13", "COUNTYFP": "121"}
    },
    {
      "boundary_type": "congressional",
      "name": "Congressional District 5",
      "boundary_identifier": "05",
      "boundary_id": "...",
      "metadata": {}
    }
  ]
}
```

```bash
# With GPS accuracy radius (50 meters)
curl -s "http://localhost:8000/api/v1/geocoding/point-lookup?lat=33.749&lng=-84.388&accuracy=50" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# Outside Georgia → 422
curl -s "http://localhost:8000/api/v1/geocoding/point-lookup?lat=40.7128&lng=-74.0060" \
  -H "Authorization: Bearer $TOKEN"
```

## Testing

```bash
# Run all tests for this feature
uv run pytest tests/unit/lib/test_geocoder/ tests/integration/api/v1/test_geocode_endpoint.py tests/integration/api/v1/test_verify_endpoint.py tests/integration/api/v1/test_point_lookup_endpoint.py -v

# Run unit tests only (no database required)
uv run pytest tests/unit/lib/test_geocoder/test_verify.py tests/unit/lib/test_geocoder/test_geo_validators.py -v

# Run with coverage
uv run pytest --cov=voter_api --cov-report=term-missing
```

## Swagger UI

Once the server is running, the endpoints are documented and testable at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

Use the "Authorize" button in Swagger UI to enter your JWT token, then test the endpoints interactively.
