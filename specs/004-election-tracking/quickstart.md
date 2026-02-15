# Election Result Tracking Quickstart

This guide walks through setting up and using the Election Result Tracking feature to ingest, track, and serve Georgia Secretary of State election results.

## Prerequisites

Before using the election tracking feature, ensure you have:

1. **voter-api installed and running** — follow the main project quickstart in `specs/001-voter-data-management/quickstart.md`
2. **PostgreSQL 15+ with PostGIS 3.x** — the database must be running
3. **Georgia county boundaries imported** — required for county-level result aggregation:
   ```bash
   uv run voter-api import all-boundaries
   ```
4. **Admin user credentials** — you'll need JWT credentials to create elections and trigger refreshes

## Environment Variables

Add these variables to your `.env` file:

```bash
# Election auto-refresh configuration
ELECTION_REFRESH_ENABLED=true           # Enable/disable background refresh loop
ELECTION_REFRESH_INTERVAL=60            # Seconds between refresh cycles (default: 60)
```

**Optional**: For testing, you may want to disable auto-refresh and use manual triggers only:

```bash
ELECTION_REFRESH_ENABLED=false
```

## Database Setup

Run the new migration to create the `elections` and `election_results` tables:

```bash
uv run voter-api db upgrade
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade abc123 -> def456, add election tracking tables
```

## Admin Authentication

All admin endpoints require a JWT token. First, obtain a token:

```bash
# Login (replace with your admin credentials)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com" \
  -d "password=your-password" \
  | jq -r '.access_token')

# Verify token
echo $TOKEN
```

Store the token in a shell variable for subsequent requests.

## Create an Election

Create a new election to start tracking results:

```bash
curl -X POST http://localhost:8000/api/v1/elections \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "election_name": "November-2024-General",
    "election_date": "2024-11-05",
    "description": "2024 General Election",
    "metadata": {
      "contests": ["President", "U.S. Senate", "State House"],
      "voter_registration_deadline": "2024-10-07"
    }
  }' | jq
```

**Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "election_name": "November-2024-General",
  "election_date": "2024-11-05",
  "description": "2024 General Election",
  "status": "active",
  "feed_url": "https://results.sos.ga.gov/cdn/results/Georgia/export-November-2024-General.json",
  "last_fetch_at": null,
  "last_fetch_status": null,
  "cache_ttl_seconds": 60,
  "metadata": {
    "contests": ["President", "U.S. Senate", "State House"],
    "voter_registration_deadline": "2024-10-07"
  },
  "created_at": "2024-11-05T12:00:00Z",
  "updated_at": "2024-11-05T12:00:00Z"
}
```

**Key fields**:
- `feed_url` — auto-generated from `election_name` using the SoS URL format
- `status` — `active` by default; set to `finalized` when results are certified
- `cache_ttl_seconds` — 60 seconds for active elections (can be overridden)

## Trigger Manual Refresh

### Via API

Trigger a refresh for a specific election:

```bash
curl -X POST http://localhost:8000/api/v1/elections/550e8400-e29b-41d4-a716-446655440000/refresh \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "election_name": "November-2024-General",
  "status": "active",
  "last_fetch_at": "2024-11-05T12:05:30Z",
  "last_fetch_status": "success",
  "results_summary": {
    "total_contests": 3,
    "total_counties": 159,
    "last_updated": "2024-11-05T12:00:00Z"
  }
}
```

### Via CLI

Refresh all active elections:

```bash
uv run voter-api election refresh
```

**Output**:
```
INFO: Starting election refresh for all active elections
INFO: Refreshing election: November-2024-General (550e8400-e29b-41d4-a716-446655440000)
INFO: Fetched 159 county results for 3 contests
INFO: Refresh complete. Status: success
```

Refresh a specific election:

```bash
uv run voter-api election refresh --election-id 550e8400-e29b-41d4-a716-446655440000
```

## View Election Results

### List Elections

List all elections with optional filters:

```bash
# All elections
curl http://localhost:8000/api/v1/elections | jq

# Only active elections
curl "http://localhost:8000/api/v1/elections?status=active" | jq

# Elections after a specific date
curl "http://localhost:8000/api/v1/elections?min_date=2024-01-01" | jq

# Pagination
curl "http://localhost:8000/api/v1/elections?skip=0&limit=10" | jq
```

**Response**:
```json
{
  "elections": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "election_name": "November-2024-General",
      "election_date": "2024-11-05",
      "status": "active",
      "description": "2024 General Election",
      "last_fetch_at": "2024-11-05T12:05:30Z",
      "last_fetch_status": "success"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 100
}
```

### Get Election Detail

Retrieve detailed information about a specific election:

```bash
curl http://localhost:8000/api/v1/elections/550e8400-e29b-41d4-a716-446655440000 | jq
```

**Response**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "election_name": "November-2024-General",
  "election_date": "2024-11-05",
  "description": "2024 General Election",
  "status": "active",
  "feed_url": "https://results.sos.ga.gov/cdn/results/Georgia/export-November-2024-General.json",
  "last_fetch_at": "2024-11-05T12:05:30Z",
  "last_fetch_status": "success",
  "cache_ttl_seconds": 60,
  "metadata": {
    "contests": ["President", "U.S. Senate", "State House"],
    "voter_registration_deadline": "2024-10-07"
  },
  "created_at": "2024-11-05T12:00:00Z",
  "updated_at": "2024-11-05T12:05:30Z"
}
```

### Get Statewide Results (JSON)

Retrieve aggregated statewide results:

```bash
curl http://localhost:8000/api/v1/elections/550e8400-e29b-41d4-a716-446655440000/results | jq
```

**Response**:
```json
{
  "election_id": "550e8400-e29b-41d4-a716-446655440000",
  "election_name": "November-2024-General",
  "election_date": "2024-11-05",
  "last_updated": "2024-11-05T12:05:30Z",
  "contests": [
    {
      "contest_name": "President",
      "contest_type": "Federal",
      "candidates": [
        {
          "candidate_name": "Jane Doe",
          "party": "Democratic",
          "votes": 2500000,
          "percentage": 52.3
        },
        {
          "candidate_name": "John Smith",
          "party": "Republican",
          "votes": 2280000,
          "percentage": 47.7
        }
      ],
      "total_votes": 4780000,
      "precincts_reporting": 2500,
      "total_precincts": 2500,
      "reporting_percentage": 100.0
    }
  ]
}
```

### Get County Results (GeoJSON)

Retrieve county-level results as GeoJSON for mapping:

```bash
curl http://localhost:8000/api/v1/elections/550e8400-e29b-41d4-a716-446655440000/results/geojson | jq
```

**Response**:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "MultiPolygon",
        "coordinates": [[[[-84.5, 33.5], [-84.5, 34.0], [-84.0, 34.0], [-84.0, 33.5], [-84.5, 33.5]]]]
      },
      "properties": {
        "county_name": "Fulton",
        "county_fips": "13121",
        "contests": [
          {
            "contest_name": "President",
            "candidates": [
              {
                "candidate_name": "Jane Doe",
                "party": "Democratic",
                "votes": 350000,
                "percentage": 68.5
              },
              {
                "candidate_name": "John Smith",
                "party": "Republican",
                "votes": 161000,
                "percentage": 31.5
              }
            ],
            "total_votes": 511000,
            "precincts_reporting": 234,
            "total_precincts": 234
          }
        ]
      }
    }
  ]
}
```

**Use cases**:
- **Web mapping** — render choropleth maps in Leaflet, Mapbox GL, or other GIS libraries
- **Data analysis** — load into QGIS, GeoPandas, or PostGIS for spatial analysis
- **Export** — save to `.geojson` file for archival or redistribution

### Filter Results by Contest

Both JSON and GeoJSON endpoints support filtering by contest name:

```bash
# JSON results for President only
curl "http://localhost:8000/api/v1/elections/550e8400-e29b-41d4-a716-446655440000/results?contest=President" | jq

# GeoJSON for U.S. Senate
curl "http://localhost:8000/api/v1/elections/550e8400-e29b-41d4-a716-446655440000/results/geojson?contest=U.S.%20Senate" | jq
```

## Auto-Refresh Background Loop

When `ELECTION_REFRESH_ENABLED=true` (default), a background asyncio task runs continuously:

1. **Startup** — the loop starts when the FastAPI app initializes
2. **Interval** — every `ELECTION_REFRESH_INTERVAL` seconds (default: 60), the loop:
   - Queries all elections with `status = 'active'`
   - Fetches results from each election's `feed_url`
   - Parses and stores results in the `election_results` table
   - Updates `last_fetch_at` and `last_fetch_status` on the election record
3. **Error handling** — if a fetch fails (HTTP error, parse error), the election's `last_fetch_status` is set to `failed` but the loop continues
4. **Shutdown** — the loop stops gracefully when the app shuts down

**Disable auto-refresh** for testing or manual control:

```bash
ELECTION_REFRESH_ENABLED=false
```

Then use CLI or API refresh endpoints on-demand.

## Cache Behavior and TTL

Election results are cached with different TTL strategies based on election status:

### Active Elections (status = "active")

- **Default TTL**: 60 seconds (`cache_ttl_seconds` on the election record)
- **Behavior**: Results are cached for the TTL duration. If a request arrives after TTL expires, the API triggers a background refresh and serves stale data immediately (if available)
- **Use case**: Election night tracking with near-real-time updates

**Override TTL when creating an election**:

```bash
curl -X POST http://localhost:8000/api/v1/elections \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "election_name": "May-2024-Primary",
    "election_date": "2024-05-21",
    "cache_ttl_seconds": 30
  }' | jq
```

### Finalized Elections (status = "finalized")

- **Default TTL**: 86400 seconds (24 hours)
- **Behavior**: Results are effectively frozen. The background loop skips finalized elections. Manual refresh via API or CLI is still permitted for re-import scenarios
- **Use case**: Certified results that rarely change

**Finalize an election**:

```bash
curl -X PATCH http://localhost:8000/api/v1/elections/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "finalized",
    "description": "2024 General Election - CERTIFIED RESULTS"
  }' | jq
```

### HTTP Cache Headers

The `/results` and `/results/geojson` endpoints return cache-control headers:

```http
Cache-Control: public, max-age=60
Last-Modified: Tue, 05 Nov 2024 12:05:30 GMT
```

Clients (browsers, CDNs) can use these headers to avoid redundant requests.

## Common Workflows

### Election Night Tracking

1. **Pre-election**: Create the election record with `status=active` and `cache_ttl_seconds=30` for fast updates
2. **Polls close**: Ensure `ELECTION_REFRESH_ENABLED=true` and the background loop is running
3. **Monitor**: Query `/results` or `/results/geojson` from a frontend; the API auto-refreshes every 30 seconds
4. **Post-election**: When results are certified, PATCH the election to `status=finalized`

### Historical Data Import

1. **Create election** with a past `election_date` and `status=finalized`
2. **Manual refresh**: `uv run voter-api election refresh --election-id <UUID>`
3. **Verify**: Query `/results` to confirm data was imported

### Multi-Election Dashboard

1. **Create multiple elections** (primary, runoff, general)
2. **List elections**: `GET /elections` to populate a dashboard
3. **Lazy-load results**: Fetch `/results/geojson` for each election when a user clicks a map layer

## Troubleshooting

### "Election not found" error

- Verify the election ID exists: `curl http://localhost:8000/api/v1/elections | jq`
- Check that the UUID is correctly formatted

### "Feed URL returned 404"

- The SoS feed URL is generated as `https://results.sos.ga.gov/cdn/results/Georgia/export-{election_name}.json`
- Verify the `election_name` matches the SoS naming convention (e.g., `November-2024-General`, not `nov-2024`)
- Check the SoS website to confirm the feed exists

### Results not updating

- Check `last_fetch_status`: `curl http://localhost:8000/api/v1/elections/{id} | jq '.last_fetch_status'`
- If `failed`, check application logs for HTTP or parse errors
- Verify `ELECTION_REFRESH_ENABLED=true` in `.env`
- Manually trigger a refresh: `uv run voter-api election refresh --election-id <UUID>`

### Background loop not running

- Check logs on app startup for: `INFO: Election auto-refresh loop started`
- Verify `ELECTION_REFRESH_ENABLED=true`
- Restart the API server: `uv run voter-api serve --reload`

### Missing county geometries in GeoJSON

- Ensure county boundaries are imported: `uv run voter-api import all-boundaries`
- The `/results/geojson` endpoint requires the `boundaries` table to have county polygons
- If boundaries are missing, the GeoJSON will return features with `null` geometry

## API Reference

For the full OpenAPI specification, see `specs/004-election-tracking/contracts/openapi.yaml` or visit `http://localhost:8000/docs` when the server is running.

## Next Steps

- **Frontend integration**: Use the GeoJSON endpoint to render live election maps
- **Webhooks**: Extend the refresh loop to trigger webhooks when results change
- **Historical analysis**: Query multiple elections to analyze trends over time
- **Export**: Use the JSON endpoint as input to data pipelines or reporting tools
