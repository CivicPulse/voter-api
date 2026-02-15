# Voter API — Frontend Integration Guide

> **Production API**: `https://voteapi.civpulse.org/api/v1`
> **CORS**: Configured for `*.civpulse.org`, `*.voter-web.pages.dev` (Cloudflare Pages previews), and `*.kerryhatcher.com`.

---

## Table of Contents

- [1. Election Result Tracking (NEW)](#1-election-result-tracking-new)
  - [1.1 Public Endpoints (no auth)](#11-public-endpoints-no-auth)
  - [1.2 Caching & Polling Strategy](#12-caching--polling-strategy)
  - [1.3 Admin Endpoints (JWT required)](#13-admin-endpoints-jwt-required)
- [2. Address Geocoding](#2-address-geocoding)
- [3. Boundaries (public, no auth)](#3-boundaries-public-no-auth)
- [4. Voters (auth required)](#4-voters-auth-required)
- [5. Other Endpoints](#5-other-endpoints)
- [6. Integration Notes](#6-integration-notes)
- [7. OpenAPI Specification — Election Tracking](#7-openapi-specification--election-tracking)

---

## 1. Election Result Tracking (NEW)

A full **live election results system** that ingests Georgia Secretary of State data. Active elections auto-refresh every 60 seconds on the backend.

### 1.1 Public Endpoints (no auth)

#### `GET /elections` — List elections

Paginated list with optional filters. Results ordered by `election_date` descending.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | `"active"` \| `"finalized"` | — | Filter by status |
| `election_type` | `"general"` \| `"primary"` \| `"special"` \| `"runoff"` | — | Filter by type |
| `district` | string | — | Partial match, case-insensitive |
| `date_from` | ISO date | — | Elections on or after this date |
| `date_to` | ISO date | — | Elections on or before this date |
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int (max 100) | 20 | Results per page |

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "General Election 2024",
      "election_date": "2024-11-05",
      "election_type": "general",
      "district": "Georgia Statewide",
      "status": "active",
      "last_refreshed_at": "2024-11-05T22:15:00Z",
      "precincts_reporting": 2650,
      "precincts_participating": 2700
    }
  ],
  "pagination": {
    "total": 47,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  }
}
```

---

#### `GET /elections/{election_id}` — Election detail

Returns full election record including `data_source_url`, `refresh_interval_seconds`, `created_at`, and `updated_at`.

---

#### `GET /elections/{election_id}/results` — Statewide + county results (JSON)

The primary results endpoint. Returns candidate vote totals statewide plus per-county breakdown, with vote method breakdowns (Election Day, Advance Voting, Absentee by Mail, Provisional).

**Response:**
```json
{
  "election_id": "uuid",
  "election_name": "General Election 2024",
  "election_date": "2024-11-05",
  "status": "active",
  "last_refreshed_at": "2024-11-05T22:15:00Z",
  "precincts_participating": 2700,
  "precincts_reporting": 2650,
  "candidates": [
    {
      "id": "2",
      "name": "Jane Doe",
      "political_party": "Democratic",
      "ballot_order": 1,
      "vote_count": 125000,
      "group_results": [
        { "group_name": "ELECTION_DAY", "vote_count": 80000 },
        { "group_name": "ADVANCE_VOTING", "vote_count": 45000 }
      ]
    }
  ],
  "county_results": [
    {
      "county_name": "Fulton",
      "precincts_participating": 400,
      "precincts_reporting": 395,
      "candidates": [
        { "id": "2", "name": "Jane Doe", "political_party": "Democratic", "ballot_order": 1, "vote_count": 35000, "group_results": [...] }
      ]
    }
  ]
}
```

---

#### `GET /elections/{election_id}/results/raw` — Raw SOS results

Same data but preserves the original Secretary of State **camelCase field names** (`politicalParty`, `ballotOrder`, `voteCount`, `groupResults`). Use this if you want to skip field mapping or need to display raw source data. Includes `source_created_at` (timestamp from SOS feed) and `statewide_results` / `county_results[].results` arrays as verbatim JSONB dicts.

---

#### `GET /elections/{election_id}/results/geojson` — County-level choropleth map data

Returns a GeoJSON `FeatureCollection` (content-type: `application/geo+json`) where each feature is a **county polygon** with election results in `properties`. Ready to drop directly into Mapbox GL, Leaflet, or deck.gl — no client-side geometry loading needed.

**Response:**
```json
{
  "type": "FeatureCollection",
  "election_id": "uuid",
  "election_name": "General Election 2024",
  "election_date": "2024-11-05",
  "status": "active",
  "last_refreshed_at": "2024-11-05T22:15:00Z",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "MultiPolygon",
        "coordinates": [[[[-84.5, 33.5], [-84.5, 33.8], [-84.2, 33.8], [-84.2, 33.5], [-84.5, 33.5]]]]
      },
      "properties": {
        "county_name": "Fulton",
        "precincts_reporting": 395,
        "precincts_participating": 400,
        "candidates": [
          { "id": "2", "name": "Jane Doe", "political_party": "Democratic", "ballot_order": 1, "vote_count": 35000, "group_results": [...] }
        ]
      }
    }
  ]
}
```

---

#### `GET /elections/{election_id}/results/geojson/precincts` — Precinct-level GeoJSON

Same concept as county GeoJSON but at **precinct granularity**. This is a much larger payload.

| Parameter | Type | Description |
|-----------|------|-------------|
| `county` | string (optional) | Filter to precincts in a single county (case-insensitive) |

**Response:**
```json
{
  "type": "FeatureCollection",
  "election_id": "uuid",
  "election_name": "...",
  "election_date": "2024-11-05",
  "status": "active",
  "last_refreshed_at": "...",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [...] },
      "properties": {
        "precinct_id": "PRECINCT_001",
        "precinct_name": "Precinct 1 - Downtown",
        "county": "Fulton",
        "reporting_status": "REPORTED",
        "candidates": [
          {
            "id": "2",
            "name": "Jane Doe",
            "political_party": "Democratic",
            "vote_count": 1250,
            "reporting_status": "REPORTED",
            "group_results": [
              { "group_name": "Mail", "vote_count": 450 },
              { "group_name": "In-Person", "vote_count": 800 }
            ]
          }
        ]
      }
    }
  ]
}
```

> **Tip**: Use the `?county=Fulton` filter and load precinct data on-demand when a user clicks or zooms into a county on the map.

---

### 1.2 Caching & Polling Strategy

The API sets `Cache-Control` headers on all results endpoints:

| Election Status | Cache Header | Meaning |
|-----------------|-------------|---------|
| `active` | `public, max-age=60` | Results may change — safe to poll every 60s |
| `finalized` | `public, max-age=86400` | Results are final — cache for 24 hours |

**Recommended frontend pattern:**
1. Poll `GET /elections/{id}/results` every 60 seconds for active elections.
2. Display `precincts_reporting / precincts_participating` as a progress indicator.
3. Show `last_refreshed_at` as a "last updated" timestamp for users.
4. Stop polling once `status` changes to `"finalized"`.

---

### 1.3 Admin Endpoints (JWT required)

These require a JWT token with admin role in the `Authorization: Bearer <token>` header.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/elections` | Create election (name, date, type, district, SOS data source URL, optional refresh interval) |
| `PATCH` | `/elections/{election_id}` | Update metadata or set `status` to `"finalized"` to stop auto-refresh |
| `POST` | `/elections/{election_id}/refresh` | Force an immediate data refresh from SOS; returns 502 if source unreachable |

---

## 2. Address Geocoding

All geocoding endpoints require JWT auth (any role).

#### `GET /geocoding/geocode?address=123 Main St, Atlanta, GA`

Single address to lat/lng coordinates. Returns `formatted_address`, `latitude`, `longitude`, `confidence`, and `metadata` (`cached`, `provider`). Returns 404 if no match, 502 if the Census geocoder is down.

#### `GET /geocoding/verify?address=123 Main St`

Address validation and autocomplete. Returns `is_well_formed`, lists of `present_components` / `missing_components` / `malformed_components`, and up to 10 address `suggestions` with coordinates. Good for address input forms.

#### `GET /geocoding/point-lookup?lat=33.749&lng=-84.388`

Reverse lookup: given coordinates, returns all districts/boundaries containing that point (county, precinct, legislative districts, etc.). Optional `accuracy` param in meters (max 100m).

#### `POST /geocoding/batch` (admin only)

Trigger bulk geocoding job for all voters. Returns 202 with a job ID.

#### `GET /geocoding/status/{job_id}`

Track progress of a batch geocoding job (processed, succeeded, failed, cache_hits).

#### `GET /geocoding/cache/stats`

Per-provider cache statistics for monitoring.

---

## 3. Boundaries (public, no auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/boundaries` | List boundaries with filtering by `boundary_type`, `county`, `source`. Paginated. |
| `GET` | `/boundaries/containing-point?latitude=...&longitude=...` | Find all boundaries containing a point. Filter by `boundary_type` or `county`. |
| `GET` | `/boundaries/geojson` | Full GeoJSON export (may redirect to R2/CDN). |
| `GET` | `/boundaries/types` | List all boundary types in the system (e.g., `county`, `county_precinct`, `state_house`, `state_senate`, `us_congress`). |
| `GET` | `/boundaries/{boundary_id}?include_geometry=true` | Single boundary detail with geometry. County boundaries include `county_metadata` (FIPS codes, land/water area). Precinct boundaries include `precinct_metadata`. |

---

## 4. Voters (auth required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/voters` | Search voters with multi-field filters. Paginated. |
| `GET` | `/voters/{voter_id}` | Full voter detail. |
| `GET` | `/voters/{voter_id}/geocoded-locations` | All geocoded locations for a voter. |
| `POST` | `/voters/{voter_id}/geocoded-locations/manual` | Add manual geocoded location (auth required). |
| `PUT` | `/voters/{voter_id}/geocoded-locations/{location_id}/set-primary` | Set location as primary (admin only). |

---

## 5. Other Endpoints

| Category | Method | Endpoint | Auth | Description |
|----------|--------|----------|------|-------------|
| **Health** | `GET` | `/health` | None | Health check (no `/api/v1` prefix) |
| **Auth** | `POST` | `/auth/login` | None | Get JWT tokens (username/password) |
| **Auth** | `POST` | `/auth/refresh` | None | Refresh access token |
| **Auth** | `GET` | `/auth/me` | Any | Current user profile |
| **Users** | `GET` | `/users` | Admin | List all users |
| **Users** | `POST` | `/users` | Admin | Create new user |
| **Imports** | `POST` | `/imports/voters` | Admin | Upload voter CSV (500 MB max) |
| **Imports** | `POST` | `/imports/boundaries` | Admin | Upload boundary shapefile/GeoJSON (200 MB max) |
| **Imports** | `GET` | `/imports` | Admin/Analyst | List import jobs |
| **Imports** | `GET` | `/imports/{job_id}` | Admin/Analyst | Import job status |
| **Imports** | `GET` | `/imports/{job_id}/diff` | Admin/Analyst | Import diff report |
| **Analysis** | `POST` | `/analysis/runs` | Admin/Analyst | Trigger analysis run |
| **Analysis** | `GET` | `/analysis/runs` | Admin/Analyst | List analysis runs |
| **Analysis** | `GET` | `/analysis/runs/{run_id}` | Admin/Analyst | Analysis run detail |
| **Analysis** | `GET` | `/analysis/runs/{run_id}/results` | Admin/Analyst | Analysis results (paginated) |
| **Analysis** | `GET` | `/analysis/compare` | Admin/Analyst | Compare two analysis runs |
| **Exports** | `POST` | `/exports` | Admin | Request bulk export (CSV/JSON/GeoJSON) |
| **Exports** | `GET` | `/exports` | Any | List export jobs |
| **Exports** | `GET` | `/exports/{job_id}` | Any | Export job status |
| **Exports** | `GET` | `/exports/{job_id}/download` | Any | Download export file |
| **Datasets** | `GET` | `/datasets` | None | Discover published static datasets on R2/CDN |

---

## 6. Integration Notes

### Authentication

All non-public endpoints require `Authorization: Bearer <token>`. Obtain tokens via `POST /auth/login`. Refresh via `POST /auth/refresh`. Roles: `admin`, `analyst`, `viewer`.

### Election Results for Mapping

The GeoJSON endpoints (`/results/geojson` and `/results/geojson/precincts`) return complete GeoJSON FeatureCollections with **embedded geometry**. Pass these directly to Mapbox/Leaflet as a source — no need to fetch boundaries separately. Color the choropleth based on `properties.candidates[n].vote_count`.

### Precinct Data is Large

The precinct GeoJSON for all 159 Georgia counties can be substantial. Use the `?county=Fulton` filter and load on-demand when a user clicks/zooms into a county.

### Polling for Live Results

During election night, poll `GET /elections/{id}/results` every 60 seconds. Show `precincts_reporting / precincts_participating` as a progress indicator. The `last_refreshed_at` field tells you when the backend last pulled from the SOS.

### Rate Limiting

The API enforces **60 requests/minute** per client. Plan polling and prefetch accordingly.

### CORS

Configured for `*.civpulse.org`, `*.voter-web.pages.dev` (Cloudflare Pages previews), and `*.kerryhatcher.com`. Request a new origin if needed.

---

## 7. OpenAPI Specification — Election Tracking

The complete OpenAPI 3.1 specification for the election tracking endpoints follows. This can be imported into Swagger UI, used for client code generation, or referenced for exact field types and constraints.

```yaml
openapi: "3.1.0"
info:
  title: voter-api Election Result Tracking Endpoints
  version: 0.1.0
  description: |
    Public and admin endpoints for tracking election results.
    Includes election listing, result retrieval in JSON and GeoJSON formats,
    and admin operations for creating, updating, and refreshing elections.
    Part of feature 004-election-tracking.

servers:
  - url: /api/v1
    description: API v1 prefix

paths:
  /elections:
    get:
      operationId: listElections
      summary: List elections with optional filters
      description: |
        Returns a paginated list of elections. No authentication required.
        Supports filtering by status, election type, and date range.
        Results are sorted by election_date descending.
      tags:
        - elections
      security: []
      parameters:
        - name: status
          in: query
          required: false
          description: Filter by election status
          schema:
            type: string
            enum: ["active", "finalized"]
          example: "active"
        - name: election_type
          in: query
          required: false
          description: Filter by election type
          schema:
            type: string
            enum: ["special", "general", "primary", "runoff"]
          example: "general"
        - name: district
          in: query
          required: false
          description: Filter by district/race identifier (case-insensitive partial match)
          schema:
            type: string
          example: "State Senate - District 18"
        - name: date_from
          in: query
          required: false
          description: Filter to elections on or after this date (ISO 8601)
          schema:
            type: string
            format: date
          example: "2024-01-01"
        - name: date_to
          in: query
          required: false
          description: Filter to elections on or before this date (ISO 8601)
          schema:
            type: string
            format: date
          example: "2024-12-31"
        - name: page
          in: query
          required: false
          description: Page number (1-indexed, default 1)
          schema:
            type: integer
            minimum: 1
            default: 1
          example: 1
        - name: page_size
          in: query
          required: false
          description: Results per page (min 1, max 100, default 20)
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
          example: 20
      responses:
        "200":
          description: List of elections with pagination metadata
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/PaginatedElectionListResponse"
        "422":
          description: Invalid query parameters
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ValidationErrorResponse"

    post:
      operationId: createElection
      summary: Create a new election
      description: |
        Admin-only operation to create a new election record.
        Returns 409 if an election with the same name and date already exists.
      tags:
        - elections
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/ElectionCreateRequest"
      responses:
        "201":
          description: Election created successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ElectionDetailResponse"
        "401":
          description: Missing or invalid JWT token
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "403":
          description: Insufficient permissions (not admin)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
              example:
                detail: "Only administrators can create elections."
        "409":
          description: Election already exists with this name and date
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
              example:
                detail: "An election with name 'General Election' and date '2024-11-05' already exists."
        "422":
          description: Validation error in request body
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ValidationErrorResponse"

  /elections/{election_id}:
    get:
      operationId: getElection
      summary: Get election detail
      description: |
        Returns full details of a single election by ID.
        No authentication required.
      tags:
        - elections
      security: []
      parameters:
        - name: election_id
          in: path
          required: true
          description: Election UUID
          schema:
            type: string
            format: uuid
          example: "123e4567-e89b-12d3-a456-426614174000"
      responses:
        "200":
          description: Election details
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ElectionDetailResponse"
        "404":
          description: Election not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
              example:
                detail: "Election not found."

    patch:
      operationId: updateElection
      summary: Update election metadata
      description: |
        Admin-only operation to update election fields.
        Partial updates are supported (only provided fields are updated).
      tags:
        - elections
      security:
        - bearerAuth: []
      parameters:
        - name: election_id
          in: path
          required: true
          description: Election UUID
          schema:
            type: string
            format: uuid
          example: "123e4567-e89b-12d3-a456-426614174000"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/ElectionUpdateRequest"
      responses:
        "200":
          description: Election updated successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ElectionDetailResponse"
        "401":
          description: Missing or invalid JWT token
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "403":
          description: Insufficient permissions (not admin)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "404":
          description: Election not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "422":
          description: Validation error
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ValidationErrorResponse"

  /elections/{election_id}/results:
    get:
      operationId: getElectionResults
      summary: Get election results as JSON
      description: |
        Returns statewide election results with candidate vote totals
        and breakdowns by vote method and county. Results are cached.
        Cache duration depends on election status: 60 seconds for active,
        86400 seconds (1 day) for finalized elections.
      tags:
        - results
      security: []
      parameters:
        - name: election_id
          in: path
          required: true
          description: Election UUID
          schema:
            type: string
            format: uuid
          example: "123e4567-e89b-12d3-a456-426614174000"
      responses:
        "200":
          description: Election results with candidate and county breakdowns
          headers:
            Cache-Control:
              description: Cache directive based on election status
              schema:
                type: string
              example: "public, max-age=60"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ElectionResultsResponse"
        "404":
          description: Election not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"

  /elections/{election_id}/results/raw:
    get:
      operationId: getRawElectionResults
      summary: Get raw SOS election results
      description: |
        Returns election results preserving the original Secretary of State
        data structure with camelCase field names (FR-006). Envelope fields
        use snake_case consistent with other API responses. The statewide_results
        and county_results[].results arrays contain the raw JSONB dicts verbatim.
        Uses same caching strategy as the JSON results endpoint.
      tags:
        - results
      security: []
      parameters:
        - name: election_id
          in: path
          required: true
          description: Election UUID
          schema:
            type: string
            format: uuid
          example: "123e4567-e89b-12d3-a456-426614174000"
      responses:
        "200":
          description: Raw election results with original SOS field names
          headers:
            Cache-Control:
              description: Cache directive based on election status
              schema:
                type: string
              example: "public, max-age=60"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/RawElectionResultsResponse"
        "404":
          description: Election not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"

  /elections/{election_id}/results/geojson:
    get:
      operationId: getElectionResultsGeoJSON
      summary: Get county election results as GeoJSON
      description: |
        Returns election results as a GeoJSON FeatureCollection with county
        boundary geometries. Each feature includes county results and candidate
        vote totals. Uses same caching strategy as JSON results endpoint.
      tags:
        - results
      security: []
      parameters:
        - name: election_id
          in: path
          required: true
          description: Election UUID
          schema:
            type: string
            format: uuid
          example: "123e4567-e89b-12d3-a456-426614174000"
      responses:
        "200":
          description: Election results as GeoJSON with county geometries
          headers:
            Cache-Control:
              description: Cache directive based on election status
              schema:
                type: string
              example: "public, max-age=60"
          content:
            application/geo+json:
              schema:
                $ref: "#/components/schemas/ElectionResultFeatureCollection"
        "404":
          description: Election not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"

  /elections/{election_id}/results/geojson/precincts:
    get:
      operationId: getElectionPrecinctResultsGeoJSON
      summary: Get precinct election results as GeoJSON
      description: |
        Returns election results as a GeoJSON FeatureCollection with precinct
        boundary geometries. Each feature includes precinct-level candidate
        results and reporting status. Supports optional county filter.
      tags:
        - results
      security: []
      parameters:
        - name: election_id
          in: path
          required: true
          description: Election UUID
          schema:
            type: string
            format: uuid
          example: "123e4567-e89b-12d3-a456-426614174000"
        - name: county
          in: query
          required: false
          description: Filter to precincts in a specific county (case-insensitive)
          schema:
            type: string
          example: "Fulton"
      responses:
        "200":
          description: Precinct-level election results as GeoJSON
          headers:
            Cache-Control:
              description: Cache directive based on election status
              schema:
                type: string
              example: "public, max-age=60"
          content:
            application/geo+json:
              schema:
                $ref: "#/components/schemas/PrecinctElectionResultFeatureCollection"
        "404":
          description: Election not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"

  /elections/{election_id}/refresh:
    post:
      operationId: refreshElection
      summary: Trigger manual election results refresh
      description: |
        Admin-only operation to manually refresh election results from
        the configured data source. Returns updated precinct counts and
        the number of counties with updated results.
      tags:
        - elections
      security:
        - bearerAuth: []
      parameters:
        - name: election_id
          in: path
          required: true
          description: Election UUID
          schema:
            type: string
            format: uuid
          example: "123e4567-e89b-12d3-a456-426614174000"
      responses:
        "200":
          description: Refresh completed successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/RefreshResponse"
        "401":
          description: Missing or invalid JWT token
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "403":
          description: Insufficient permissions (not admin)
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "404":
          description: Election not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
        "502":
          description: Data source is unreachable or returned an error
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ErrorResponse"
              example:
                detail: "Failed to retrieve results from data source. Please retry later."

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: |
        JWT Bearer token with role claim. Roles: admin, analyst, viewer.
        Admin role required for POST/PATCH operations and manual refresh.

  schemas:
    # Request schemas

    ElectionCreateRequest:
      type: object
      required:
        - name
        - election_date
        - election_type
        - district
        - data_source_url
      properties:
        name:
          type: string
          description: Human-readable election name
          minLength: 1
          maxLength: 500
          example: "General Election 2024"
        election_date:
          type: string
          format: date
          description: Election date in ISO 8601 format
          example: "2024-11-05"
        election_type:
          type: string
          enum: ["special", "general", "primary", "runoff"]
          description: Type of election
          example: "general"
        district:
          type: string
          description: >
            Race/contest identifier
            (e.g., "State Senate - District 18", "Georgia Statewide")
          minLength: 1
          maxLength: 200
          example: "State Senate - District 18"
        data_source_url:
          type: string
          format: uri
          description: URL to the official election results data source
          example: "https://sos.ga.gov/elections/results"
        refresh_interval_seconds:
          type: integer
          minimum: 60
          description: Seconds between automatic refreshes (optional, default 120)
          example: 120

    ElectionUpdateRequest:
      type: object
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 500
          description: Updated election name
          example: "General Election 2024 - Updated"
        data_source_url:
          type: string
          format: uri
          description: Updated data source URL
          example: "https://sos.ga.gov/elections/results"
        status:
          type: string
          enum: ["active", "finalized"]
          description: Updated election status
          example: "finalized"
        refresh_interval_seconds:
          type: integer
          minimum: 60
          description: Updated refresh interval in seconds
          example: 300

    # Response schemas

    ElectionSummary:
      type: object
      required:
        - id
        - name
        - election_date
        - election_type
        - district
        - status
        - last_refreshed_at
        - precincts_reporting
        - precincts_participating
      properties:
        id:
          type: string
          format: uuid
          description: Unique election identifier
          example: "123e4567-e89b-12d3-a456-426614174000"
        name:
          type: string
          description: Election name
          example: "General Election 2024"
        election_date:
          type: string
          format: date
          description: Election date
          example: "2024-11-05"
        election_type:
          type: string
          enum: ["special", "general", "primary", "runoff"]
          description: Type of election
          example: "general"
        district:
          type: string
          description: Geographic scope
          example: "Georgia Statewide"
        status:
          type: string
          enum: ["active", "finalized"]
          description: Current election status
          example: "active"
        last_refreshed_at:
          oneOf:
            - type: string
              format: date-time
              description: Timestamp of last results refresh
              example: "2024-11-05T18:30:00Z"
            - type: "null"
          nullable: true
          description: Null if election has not yet been refreshed
        precincts_reporting:
          oneOf:
            - type: integer
              minimum: 0
              description: Number of precincts that have reported results
              example: 2450
            - type: "null"
          nullable: true
          description: Null if results not yet available
        precincts_participating:
          oneOf:
            - type: integer
              minimum: 1
              description: Total number of precincts in the election
              example: 2600
            - type: "null"
          nullable: true
          description: Null if not yet determined

    ElectionDetailResponse:
      allOf:
        - $ref: "#/components/schemas/ElectionSummary"
        - type: object
          required:
            - data_source_url
            - refresh_interval_seconds
            - created_at
            - updated_at
          properties:
            data_source_url:
              type: string
              format: uri
              description: Official results data source URL
              example: "https://sos.ga.gov/elections/results"
            refresh_interval_seconds:
              type: integer
              minimum: 60
              description: Seconds between automatic refreshes
              example: 120
            created_at:
              type: string
              format: date-time
              description: Timestamp when the election was created
              example: "2024-10-01T10:00:00Z"
            updated_at:
              type: string
              format: date-time
              description: Timestamp of the last metadata update
              example: "2024-11-05T18:30:00Z"

    PaginationMeta:
      type: object
      required:
        - total
        - page
        - page_size
        - total_pages
      properties:
        total:
          type: integer
          minimum: 0
          description: Total number of results across all pages
          example: 47
        page:
          type: integer
          minimum: 1
          description: Current page number (1-indexed)
          example: 1
        page_size:
          type: integer
          minimum: 1
          maximum: 100
          description: Results per page
          example: 20
        total_pages:
          type: integer
          minimum: 0
          description: Total number of pages
          example: 3

    PaginatedElectionListResponse:
      type: object
      required:
        - items
        - pagination
      properties:
        items:
          type: array
          description: List of elections on this page
          items:
            $ref: "#/components/schemas/ElectionSummary"
        pagination:
          $ref: "#/components/schemas/PaginationMeta"

    VoteMethodResult:
      type: object
      required:
        - group_name
        - vote_count
      properties:
        group_name:
          type: string
          description: >
            Vote method group name
            (e.g., "Election Day", "Advance Voting", "Absentee by Mail", "Provisional")
          example: "Advance Voting"
        vote_count:
          type: integer
          minimum: 0
          description: Number of votes cast via this method
          example: 45000

    CandidateResult:
      type: object
      required:
        - id
        - name
        - political_party
        - ballot_order
        - vote_count
        - group_results
      properties:
        id:
          type: string
          description: Candidate identifier from SoS feed (opaque string, not UUID)
          example: "2"
        name:
          type: string
          description: Full candidate name
          example: "Jane Smith"
        political_party:
          type: string
          description: Political party affiliation
          example: "Democratic"
        ballot_order:
          type: integer
          minimum: 1
          description: Ballot position (1-indexed)
          example: 1
        vote_count:
          type: integer
          minimum: 0
          description: Total votes received
          example: 1234567
        group_results:
          type: array
          description: Votes broken down by method or group
          items:
            $ref: "#/components/schemas/VoteMethodResult"

    PrecinctCandidateResult:
      type: object
      required:
        - id
        - name
        - political_party
        - vote_count
        - reporting_status
        - group_results
      properties:
        id:
          type: string
          description: Candidate identifier
          example: "2"
        name:
          type: string
          description: Candidate name
          example: "Jane Smith"
        political_party:
          type: string
          description: Political party
          example: "Democratic"
        vote_count:
          type: integer
          minimum: 0
          description: Votes in this precinct
          example: 1250
        reporting_status:
          type: string
          description: Reporting status for this precinct
          example: "REPORTED"
        group_results:
          type: array
          description: Vote method breakdown
          items:
            $ref: "#/components/schemas/VoteMethodResult"

    CountyResultSummary:
      type: object
      required:
        - county_name
        - precincts_participating
        - precincts_reporting
        - candidates
      properties:
        county_name:
          type: string
          description: Georgia county name
          example: "Fulton County"
        precincts_participating:
          oneOf:
            - type: integer
              minimum: 1
            - type: "null"
          nullable: true
          description: Number of precincts in the county
          example: 245
        precincts_reporting:
          oneOf:
            - type: integer
              minimum: 0
            - type: "null"
          nullable: true
          description: Number of precincts that have reported
          example: 200
        candidates:
          type: array
          description: Candidate results for this county
          items:
            $ref: "#/components/schemas/CandidateResult"

    ElectionResultsResponse:
      type: object
      required:
        - election_id
        - election_name
        - election_date
        - status
        - last_refreshed_at
        - precincts_participating
        - precincts_reporting
        - candidates
        - county_results
      properties:
        election_id:
          type: string
          format: uuid
          description: Election UUID
          example: "123e4567-e89b-12d3-a456-426614174000"
        election_name:
          type: string
          description: Election name
          example: "General Election 2024"
        election_date:
          type: string
          format: date
          description: Election date
          example: "2024-11-05"
        status:
          type: string
          enum: ["active", "finalized"]
          description: Election status
          example: "active"
        last_refreshed_at:
          type: string
          format: date-time
          description: Timestamp of last results refresh
          example: "2024-11-05T18:30:00Z"
        precincts_participating:
          oneOf:
            - type: integer
              minimum: 1
            - type: "null"
          nullable: true
          description: Total precincts in the election
          example: 2600
        precincts_reporting:
          oneOf:
            - type: integer
              minimum: 0
            - type: "null"
          nullable: true
          description: Precincts with reported results
          example: 2450
        candidates:
          type: array
          description: Statewide candidate results
          items:
            $ref: "#/components/schemas/CandidateResult"
        county_results:
          type: array
          description: Results broken down by county
          items:
            $ref: "#/components/schemas/CountyResultSummary"

    RawCountyResult:
      type: object
      required:
        - county_name
        - precincts_participating
        - precincts_reporting
        - results
      properties:
        county_name:
          type: string
          description: Georgia county name
          example: "Houston County"
        precincts_participating:
          oneOf:
            - type: integer
              minimum: 1
            - type: "null"
          nullable: true
          description: Number of precincts in the county
          example: 7
        precincts_reporting:
          oneOf:
            - type: integer
              minimum: 0
            - type: "null"
          nullable: true
          description: Number of precincts that have reported
          example: 5
        results:
          type: array
          description: Raw SOS ballot option dicts with original camelCase keys
          items:
            type: object
            additionalProperties: true

    RawElectionResultsResponse:
      type: object
      required:
        - election_id
        - election_name
        - election_date
        - status
        - last_refreshed_at
        - source_created_at
        - precincts_participating
        - precincts_reporting
        - statewide_results
        - county_results
      properties:
        election_id:
          type: string
          format: uuid
          description: Election UUID
          example: "123e4567-e89b-12d3-a456-426614174000"
        election_name:
          type: string
          description: Election name
          example: "GA Senate District 18 Special"
        election_date:
          type: string
          format: date
          description: Election date
          example: "2026-02-17"
        status:
          type: string
          enum: ["active", "finalized"]
          description: Election status
          example: "active"
        last_refreshed_at:
          oneOf:
            - type: string
              format: date-time
            - type: "null"
          nullable: true
          description: Timestamp of last results refresh
          example: "2026-02-17T12:00:00Z"
        source_created_at:
          oneOf:
            - type: string
              format: date-time
            - type: "null"
          nullable: true
          description: Timestamp from the SOS feed's createdAt field
          example: "2026-02-09T17:40:56Z"
        precincts_participating:
          oneOf:
            - type: integer
              minimum: 1
            - type: "null"
          nullable: true
          description: Total precincts in the election
          example: 100
        precincts_reporting:
          oneOf:
            - type: integer
              minimum: 0
            - type: "null"
          nullable: true
          description: Precincts with reported results
          example: 95
        statewide_results:
          type: array
          description: Raw SOS ballot option dicts with original camelCase keys
          items:
            type: object
            additionalProperties: true
        county_results:
          type: array
          description: County-level raw results
          items:
            $ref: "#/components/schemas/RawCountyResult"

    ElectionResultFeature:
      type: object
      required:
        - type
        - geometry
        - properties
      properties:
        type:
          type: string
          enum: ["Feature"]
          description: GeoJSON Feature type
          example: "Feature"
        geometry:
          type: object
          description: GeoJSON geometry object (MultiPolygon or Polygon for county boundary)
          properties:
            type:
              type: string
              enum: ["Polygon", "MultiPolygon"]
            coordinates:
              type: array
              description: GeoJSON coordinates (raw array structure)
          example:
            type: "Polygon"
            coordinates:
              [
                [
                  [-84.5, 33.5],
                  [-84.5, 33.8],
                  [-84.2, 33.8],
                  [-84.2, 33.5],
                  [-84.5, 33.5],
                ],
              ]
        properties:
          type: object
          required:
            - county_name
            - precincts_reporting
            - precincts_participating
            - candidates
          properties:
            county_name:
              type: string
              description: County name
              example: "Fulton County"
            precincts_reporting:
              oneOf:
                - type: integer
                  minimum: 0
                - type: "null"
              nullable: true
              example: 200
            precincts_participating:
              oneOf:
                - type: integer
                  minimum: 1
                - type: "null"
              nullable: true
              example: 245
            candidates:
              type: array
              description: County-level candidate results
              items:
                $ref: "#/components/schemas/CandidateResult"

    PrecinctElectionResultFeature:
      type: object
      required:
        - type
        - geometry
        - properties
      properties:
        type:
          type: string
          enum: ["Feature"]
        geometry:
          type: object
          nullable: true
          description: GeoJSON geometry (Polygon/MultiPolygon) or null if precinct boundary not found
        properties:
          type: object
          required:
            - precinct_id
            - precinct_name
            - county
            - reporting_status
            - candidates
          properties:
            precinct_id:
              type: string
              description: Uppercased precinct identifier
              example: "PRECINCT_001"
            precinct_name:
              type: string
              description: Human-readable precinct name
              example: "Precinct 1 - Downtown"
            county:
              type: string
              description: County name
              example: "Fulton"
            reporting_status:
              type: string
              nullable: true
              description: Precinct reporting status (REPORTED, NOT_REPORTED, or null)
              example: "REPORTED"
            candidates:
              type: array
              description: Per-precinct candidate results
              items:
                $ref: "#/components/schemas/PrecinctCandidateResult"

    ElectionResultFeatureCollection:
      type: object
      required:
        - type
        - features
        - election_id
        - election_name
        - election_date
        - status
        - last_refreshed_at
      properties:
        type:
          type: string
          enum: ["FeatureCollection"]
          description: GeoJSON FeatureCollection type
          example: "FeatureCollection"
        election_id:
          type: string
          format: uuid
          description: Election UUID
          example: "123e4567-e89b-12d3-a456-426614174000"
        election_name:
          type: string
          description: Election name
          example: "General Election 2024"
        election_date:
          type: string
          format: date
          description: Election date
          example: "2024-11-05"
        status:
          type: string
          enum: ["active", "finalized"]
          description: Election status
          example: "active"
        last_refreshed_at:
          type: string
          format: date-time
          description: Timestamp of last results refresh
          example: "2024-11-05T18:30:00Z"
        features:
          type: array
          description: Array of county result features with boundaries
          items:
            $ref: "#/components/schemas/ElectionResultFeature"

    PrecinctElectionResultFeatureCollection:
      type: object
      required:
        - type
        - features
        - election_id
        - election_name
        - election_date
        - status
        - last_refreshed_at
      properties:
        type:
          type: string
          enum: ["FeatureCollection"]
        election_id:
          type: string
          format: uuid
        election_name:
          type: string
        election_date:
          type: string
          format: date
        status:
          type: string
          enum: ["active", "finalized"]
        last_refreshed_at:
          type: string
          format: date-time
        features:
          type: array
          items:
            $ref: "#/components/schemas/PrecinctElectionResultFeature"

    RefreshResponse:
      type: object
      required:
        - election_id
        - refreshed_at
        - precincts_reporting
        - precincts_participating
        - counties_updated
      properties:
        election_id:
          type: string
          format: uuid
          description: Election UUID
          example: "123e4567-e89b-12d3-a456-426614174000"
        refreshed_at:
          type: string
          format: date-time
          description: Timestamp when the refresh completed
          example: "2024-11-05T18:45:30Z"
        precincts_reporting:
          oneOf:
            - type: integer
              minimum: 0
            - type: "null"
          nullable: true
          description: Updated precinct count reporting
          example: 2500
        precincts_participating:
          oneOf:
            - type: integer
              minimum: 1
            - type: "null"
          nullable: true
          description: Updated total precinct count
          example: 2600
        counties_updated:
          type: integer
          minimum: 0
          description: Number of counties with updated results
          example: 25

    # Error schemas

    ErrorResponse:
      type: object
      required:
        - detail
      properties:
        detail:
          type: string
          description: Human-readable error message
          example: "Resource not found."

    ValidationErrorResponse:
      type: object
      required:
        - detail
      properties:
        detail:
          oneOf:
            - type: string
              description: General validation error message
            - type: array
              description: Array of validation errors (Pydantic format)
              items:
                type: object
                properties:
                  loc:
                    type: array
                    description: Location of the error (path in request)
                    items:
                      oneOf:
                        - type: string
                        - type: integer
                  msg:
                    type: string
                    description: Error message
                  type:
                    type: string
                    description: Error type code
```
