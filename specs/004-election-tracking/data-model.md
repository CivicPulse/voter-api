# Election Result Tracking Data Model

## Overview

This document defines the database schema for tracking Georgia Secretary of State election results. The data model is designed to:

- Track multiple elections with their metadata and configuration
- Store statewide and county-level results as JSONB for full SoS feed fidelity
- Enable GeoJSON visualization by joining county results to the existing `boundaries` table
- Support auto-refresh with configurable intervals
- Preserve source data structure while enabling efficient querying

## Entities

### elections

The main election entity. Represents a single race or election event being tracked. Each election has a unique SoS JSON feed URL and refresh configuration.

**Key Design Choices**:
- `district` field stores the race identifier (e.g., "State Senate - District 18") to distinguish elections on the same date
- `status` enables filtering active vs finalized elections without deletion
- `refresh_interval_seconds` allows per-election refresh cadence (default 2 minutes)
- `last_refreshed_at` tracks health of auto-refresh jobs

### election_results

Stores a single statewide result snapshot per election. This table uses an upsert pattern — each refresh replaces the existing row for the election. Historical snapshots are not retained.

**Key Design Choices**:
- `results_data` JSONB stores the full `ballotOptions` array from `results.ballotItems[0]` in the SoS feed
- `source_created_at` captures the feed's `createdAt` timestamp for staleness detection
- `fetched_at` records when the data was retrieved by the API
- One-to-one relationship with `elections` enforced by unique constraint

### election_county_results

County-level results for GeoJSON visualization. Each row represents one county's results for one election.

**Key Design Choices**:
- `county_name` stores the original SoS feed value (e.g., "Houston County")
- `county_name_normalized` strips " County" suffix for matching against `boundaries.name` (e.g., "Houston")
- `results_data` JSONB stores the county-specific `ballotOptions` array
- Separate from statewide results to enable efficient spatial joins without parsing JSONB

## Schema

### elections

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid_generate_v4() | Primary key |
| name | VARCHAR(500) | NOT NULL | Election display name (e.g., "State Senate District 18 Special Election") |
| election_date | DATE | NOT NULL | Election day (from SoS feed `electionDate`) |
| election_type | VARCHAR(50) | NOT NULL | Election category: "special", "general", "primary", "runoff" |
| district | VARCHAR(200) | NOT NULL | District/race identifier (e.g., "State Senate - District 18") |
| data_source_url | TEXT | NOT NULL | Full URL to SoS JSON feed for this election |
| status | VARCHAR(20) | NOT NULL, default 'active' | "active" (auto-refreshing) or "finalized" (archived) |
| last_refreshed_at | TIMESTAMPTZ | NULL | Timestamp of last successful data fetch |
| refresh_interval_seconds | INTEGER | NOT NULL, default 120 | Auto-refresh interval in seconds (default 2 minutes) |
| created_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record last modified timestamp |

**Constraints**:
- `UNIQUE (name, election_date)` — prevents duplicate election tracking
- `CHECK (status IN ('active', 'finalized'))` — enforce valid status values
- `CHECK (refresh_interval_seconds >= 60)` — minimum 1-minute refresh interval

**Indexes**:
- `idx_elections_status` on `(status)` — filter active elections for auto-refresh
- `idx_elections_election_date` on `(election_date DESC)` — sort by recency

### election_results

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid_generate_v4() | Primary key |
| election_id | UUID | FK → elections.id, NOT NULL, ON DELETE CASCADE | Parent election |
| precincts_participating | INTEGER | NULL | Total precincts in the election (may be null initially) |
| precincts_reporting | INTEGER | NULL | Number of precincts reporting results |
| results_data | JSONB | NOT NULL | Full `ballotOptions` array from `results.ballotItems[0]` in SoS feed |
| source_created_at | TIMESTAMPTZ | NULL | `createdAt` timestamp from the SoS feed |
| fetched_at | TIMESTAMPTZ | NOT NULL, default now() | When this snapshot was fetched from SoS |
| created_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record creation timestamp |

**Constraints**:
- `UNIQUE (election_id)` — enforces one result row per election (upsert pattern)

**Indexes**:
- Primary key index on `id`
- Unique index on `election_id` (from UNIQUE constraint)
- `GIN (results_data)` — enable JSONB queries on ballot options

### election_county_results

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid_generate_v4() | Primary key |
| election_id | UUID | FK → elections.id, NOT NULL, ON DELETE CASCADE | Parent election |
| county_name | VARCHAR(100) | NOT NULL | County name as it appears in SoS feed (e.g., "Houston County") |
| county_name_normalized | VARCHAR(100) | NOT NULL | Normalized county name for boundary matching (e.g., "Houston") |
| precincts_participating | INTEGER | NULL | County-level precincts participating |
| precincts_reporting | INTEGER | NULL | County-level precincts reporting |
| results_data | JSONB | NOT NULL | `ballotOptions` array for this county from `localResults[]` in SoS feed |
| created_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record creation timestamp |

**Constraints**:
- `UNIQUE (election_id, county_name)` — one result row per county per election

**Indexes**:
- `idx_election_county_results_election_id` on `(election_id)` — fast lookup by election
- `idx_election_county_results_county_normalized` on `(county_name_normalized)` — join to boundaries
- `GIN (results_data)` — enable JSONB queries on county ballot options

## Relationships

```
elections (1) ──< (1) election_results
    │
    └──< (*) election_county_results
                     │
                     │ soft join (county_name_normalized ⇔ name)
                     │
                county_metadata
                     │
                     │ soft join (geoid ⇔ boundary_identifier)
                     │
                boundaries (boundary_type='county')
```

**Foreign Keys**:
- `election_results.election_id` → `elections.id` (ON DELETE CASCADE)
- `election_county_results.election_id` → `elections.id` (ON DELETE CASCADE)

**Soft Join** (no FK, two-hop path for GeoJSON):
- `election_county_results.county_name_normalized` ⇔ `county_metadata.name` (case-insensitive match)
- `county_metadata.geoid` ⇔ `boundaries.boundary_identifier` where `boundaries.boundary_type = 'county'`

## Entity-Relationship Diagram

```
┌─────────────────────────────────────────┐
│ elections                               │
├─────────────────────────────────────────┤
│ id (PK)                        UUID     │
│ name                           VARCHAR  │
│ election_date                  DATE     │
│ election_type                  VARCHAR  │
│ district                       VARCHAR  │
│ data_source_url                TEXT     │
│ status                         VARCHAR  │
│ last_refreshed_at              TIMESTAMPTZ │
│ refresh_interval_seconds       INTEGER  │
│ created_at                     TIMESTAMPTZ │
│ updated_at                     TIMESTAMPTZ │
└────────────┬────────────────────────────┘
             │
             │ 1
             │
     ┌───────┴────────┐
     │                │
     │ 1              │ *
     │                │
┌────▼─────────────────────────────────┐ ┌────▼─────────────────────────────────┐
│ election_results                     │ │ election_county_results              │
├──────────────────────────────────────┤ ├──────────────────────────────────────┤
│ id (PK)                     UUID     │ │ id (PK)                     UUID     │
│ election_id (FK, UNIQUE)    UUID     │ │ election_id (FK)            UUID     │
│ precincts_participating     INTEGER  │ │ county_name                 VARCHAR  │
│ precincts_reporting         INTEGER  │ │ county_name_normalized      VARCHAR  │
│ results_data                JSONB    │ │ precincts_participating     INTEGER  │
│ source_created_at           TIMESTAMPTZ │ │ precincts_reporting      INTEGER  │
│ fetched_at                  TIMESTAMPTZ │ │ results_data             JSONB    │
│ created_at                  TIMESTAMPTZ │ │ created_at               TIMESTAMPTZ │
└──────────────────────────────────────┘ └────────┬─────────────────────────────┘
                                                  │
                                                  │ soft join
                                                  │ (county_name_normalized = name)
                                                  │
                                         ┌────────▼─────────────────────────────┐
                                         │ county_metadata (existing)           │
                                         ├──────────────────────────────────────┤
                                         │ id (PK)                     UUID     │
                                         │ geoid                       VARCHAR  │
                                         │ name                        VARCHAR  │
                                         │ name_lsad                   VARCHAR  │
                                         │ ...                                  │
                                         └────────┬─────────────────────────────┘
                                                  │
                                                  │ soft join
                                                  │ (geoid = boundary_identifier)
                                                  │
                                         ┌────────▼─────────────────────────────┐
                                         │ boundaries (existing)                │
                                         ├──────────────────────────────────────┤
                                         │ id (PK)                     UUID     │
                                         │ name                        VARCHAR  │
                                         │ boundary_type               VARCHAR  │
                                         │ boundary_identifier         VARCHAR  │
                                         │ geometry                    GEOMETRY │
                                         │ ...                                  │
                                         └──────────────────────────────────────┘
```

## JSONB Structure

### election_results.results_data

Stores the `ballotOptions` array from `results.ballotItems[0]` in the SoS feed:

```json
[
  {
    "id": "2",
    "name": "LeMario Nicholas Brown (Dem)",
    "ballotOrder": 1,
    "voteCount": 1234,
    "politicalParty": "Dem",
    "groupResults": [
      {"groupName": "Election Day", "voteCount": 800, "isFromVirtualPrecinct": false},
      {"groupName": "Advance Voting", "voteCount": 300, "isFromVirtualPrecinct": false},
      {"groupName": "Absentee by Mail", "voteCount": 120, "isFromVirtualPrecinct": false},
      {"groupName": "Provisional", "voteCount": 14, "isFromVirtualPrecinct": false}
    ],
    "precinctResults": null
  },
  {
    "id": "4",
    "name": "Steven McNeel (Rep)",
    "ballotOrder": 2,
    "voteCount": 5678,
    "politicalParty": "Rep",
    "groupResults": [...]
  }
]
```

### election_county_results.results_data

Stores the `ballotOptions` array from `localResults[i].ballotItems[0]` for a specific county:

```json
[
  {
    "id": "2",
    "name": "LeMario Nicholas Brown (Dem)",
    "ballotOrder": 1,
    "voteCount": 42,
    "politicalParty": "Dem",
    "groupResults": [
      {"groupName": "Election Day", "voteCount": 25, "isFromVirtualPrecinct": false},
      {"groupName": "Advance Voting", "voteCount": 12, "isFromVirtualPrecinct": false},
      {"groupName": "Absentee by Mail", "voteCount": 4, "isFromVirtualPrecinct": false},
      {"groupName": "Provisional", "voteCount": 1, "isFromVirtualPrecinct": false}
    ],
    "precinctResults": [
      {
        "id": "ANNX", "name": "ANNX", "isVirtual": false,
        "voteCount": 10, "reportingStatus": "Reported",
        "groupResults": [...]
      }
    ]
  }
]
```

## Design Decisions

### 1. JSONB for results_data

**Decision**: Store ballot options as JSONB rather than normalizing into `candidates` and `vote_results` tables.

**Rationale**:
- Preserves full SoS feed structure and fidelity (FR-006 requirement)
- Simplifies refresh logic (replace entire JSONB blob vs managing relational inserts/updates/deletes)
- The data is always consumed as a unit (candidates with their vote breakdowns)
- JSONB indexing (GIN) enables efficient queries if needed (e.g., filter by candidate name)
- Avoids schema brittleness if SoS adds new fields or changes structure

**Trade-offs**:
- Slightly larger storage footprint vs normalized tables
- Requires JSONB query syntax for filtering/aggregation (acceptable given PostgreSQL's mature JSONB support)

### 2. Single result row per election (upsert pattern)

**Decision**: Each election has exactly one row in `election_results` (and N rows in `election_county_results`, one per county). Refreshes replace existing data.

**Rationale**:
- Historical snapshots are not a stated requirement
- Keeps database size small (especially for frequent auto-refresh)
- Simplifies queries (no need to filter by "latest" timestamp)
- Immutable source data is preserved at the SoS feed URL (available via `data_source_url`)

**Trade-offs**:
- Cannot track result changes over time without external logging
- If historical analysis becomes a requirement, would need to add a `snapshots` table or change to append-only model

### 3. Separate county_results table

**Decision**: Store county results in a dedicated table rather than embedding in statewide `results_data` JSONB.

**Rationale**:
- Enables efficient GeoJSON generation via direct join to `boundaries` table
- Avoids parsing large JSONB arrays to extract county data for spatial queries
- County-level metadata (precincts_participating/reporting) is first-class data, not nested JSONB
- Matches the SoS feed structure (`localResults[]` is separate from `results`)

### 4. county_name_normalized

**Decision**: Store both original (`county_name`) and normalized (`county_name_normalized`) county names.

**Rationale**:
- SoS feed uses "Houston County" format
- Existing `boundaries` table uses "Houston" format (without " County" suffix)
- Normalization enables reliable join while preserving source fidelity for display/debugging
- Computed during ingest, not at query time (performance)

### 5. Minimal constraints, no candidate normalization

**Decision**: Do not enforce referential integrity between elections and external entities (e.g., a `candidates` table or `districts` table).

**Rationale**:
- The SoS feed is the source of truth — all entities (candidates, districts) are defined there
- Election tracking is ephemeral (tracked during the election period, finalized afterward)
- Adding normalized tables for candidates/parties/districts would require complex deduplication logic and ongoing maintenance
- JSONB approach keeps the schema simple and aligned with the feed structure

## Indexes

All indexes are B-tree unless otherwise specified.

### elections
- **Primary key**: `id`
- **idx_elections_status**: `(status)` — filter active elections for background refresh jobs
- **idx_elections_election_date**: `(election_date DESC)` — sort by recency in list endpoints
- **Unique constraint index**: `(name, election_date)` — prevent duplicates

### election_results
- **Primary key**: `id`
- **Unique constraint index**: `(election_id)` — enforce one result per election
- **idx_election_results_jsonb**: `GIN (results_data)` — enable JSONB queries (e.g., filter by candidate)

### election_county_results
- **Primary key**: `id`
- **Unique constraint index**: `(election_id, county_name)` — one result per county per election
- **idx_election_county_results_election_id**: `(election_id)` — fast lookup for GeoJSON generation
- **idx_election_county_results_county_normalized**: `(county_name_normalized)` — join to boundaries table
- **idx_election_county_results_jsonb**: `GIN (results_data)` — enable JSONB queries

## Migration Notes

### Prerequisites

Requires:
- PostgreSQL 12+ with JSONB support
- `uuid-ossp` extension (for `uuid_generate_v4()`)
- Existing `boundaries` table with `boundary_type = 'county'` and `name` column

### Migration Steps

1. **Create elections table** with UUIDMixin, TimestampMixin, status enum check, and unique constraint
2. **Create election_results table** with FK to elections, JSONB column, unique constraint on election_id, GIN index on results_data
3. **Create election_county_results table** with FK to elections, JSONB column, unique constraint on (election_id, county_name), indexes on election_id, county_name_normalized, and GIN index on results_data

### Sample Data

```sql
-- Insert sample election
INSERT INTO elections (id, name, election_date, election_type, district, data_source_url, status, refresh_interval_seconds)
VALUES (
  gen_random_uuid(),
  'State Senate District 18 Special Election',
  '2026-02-18',
  'special',
  'State Senate - District 18',
  'https://results.enr.clarityelections.com/GA/127380/current_ver.json',
  'active',
  120
);

-- Insert sample statewide result
INSERT INTO election_results (election_id, precincts_participating, precincts_reporting, results_data, source_created_at, fetched_at)
SELECT
  e.id,
  100,
  95,
  '[{"id": "1", "name": "John Doe (R)", "groupResults": [{"groupName": "Early Voting", "totalCount": 1234, "totalPercent": "45.67%"}]}]'::jsonb,
  '2026-02-18T20:15:00Z',
  NOW()
FROM elections e
WHERE e.name = 'State Senate District 18 Special Election';

-- Insert sample county result
INSERT INTO election_county_results (election_id, county_name, county_name_normalized, precincts_participating, precincts_reporting, results_data)
SELECT
  e.id,
  'Houston County',
  'Houston',
  10,
  9,
  '[{"id": "1", "name": "John Doe (R)", "groupResults": [{"groupName": "Early Voting", "totalCount": 42, "totalPercent": "40.00%"}]}]'::jsonb
FROM elections e
WHERE e.name = 'State Senate District 18 Special Election';
```

## Performance Considerations

### Auto-Refresh Scalability

With default 120-second refresh intervals:
- 10 active elections → 10 HTTP requests + 10 DB transactions every 2 minutes (negligible load)
- 100 active elections → 100 HTTP requests + 100 DB transactions every 2 minutes (still acceptable)

Each refresh:
1. Fetches JSON from SoS (external HTTP call, typically <500ms)
2. Upserts 1 row in `election_results` (O(1))
3. Upserts N rows in `election_county_results` (O(N) where N = number of counties, typically <160 for Georgia)

**Optimization**: Batch upserts for county results using SQLAlchemy's bulk operations.

### JSONB Query Performance

GIN indexes on `results_data` enable efficient JSONB queries:

```sql
-- Find elections where a specific candidate is on the ballot
SELECT e.* FROM elections e
JOIN election_results er ON er.election_id = e.id
WHERE er.results_data @> '[{"name": "John Doe (R)"}]'::jsonb;

-- Get county-level results for a specific candidate
SELECT county_name, results_data
FROM election_county_results
WHERE election_id = :election_id
  AND results_data @> '[{"name": "John Doe (R)"}]'::jsonb;
```

### GeoJSON Generation Performance

County results are pre-normalized for spatial joins via two-hop through county_metadata:

```sql
-- Efficient GeoJSON generation (two-hop join through county_metadata)
SELECT
  b.geometry,
  ecr.county_name,
  ecr.precincts_reporting,
  ecr.results_data
FROM election_county_results ecr
JOIN county_metadata cm ON LOWER(cm.name) = LOWER(ecr.county_name_normalized)
JOIN boundaries b ON b.boundary_identifier = cm.geoid
  AND b.boundary_type = 'county'
WHERE ecr.election_id = :election_id;
```

Index on `county_name_normalized` and `county_metadata.name` ensures this join is fast even with 159 Georgia counties.

## Future Enhancements

### Historical Snapshots

If historical tracking becomes a requirement:

1. Add `election_result_snapshots` table with `(election_id, snapshot_at)` composite key
2. Change refresh logic to INSERT new rows instead of UPSERT
3. Update API to include `?as_of=<timestamp>` query parameter
4. Add retention policy to limit storage (e.g., keep snapshots for 30 days after finalization)

### Candidate Normalization

If cross-election candidate analytics are needed:

1. Add `candidates` table with deduplication logic (fuzzy matching on name)
2. Add FK from `ballot_option_id` in JSONB to `candidates.id`
3. Requires complex ETL to map SoS names to canonical candidate records

### District/Precinct Granularity

If precinct-level results become available:

1. Add `election_precinct_results` table with FK to `boundaries` (boundary_type = 'precinct')
2. Import precinct boundaries from SoS shapefiles
3. Extend GeoJSON API to support precinct-level visualization

## References

- **SoS Feed Structure**: See `specs/004-election-tracking/spec.md` FR-006 for example JSON
- **Existing Schema**: `boundaries` and `county_metadata` tables defined in migrations 010-011
- **SQLAlchemy Models**: `src/voter_api/models/base.py` (UUIDMixin, TimestampMixin, Base)
