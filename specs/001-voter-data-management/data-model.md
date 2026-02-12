# Data Model: Voter Data Management

**Branch**: `001-voter-data-management` | **Date**: 2026-02-11
**Source**: [spec.md](spec.md) entities + [plan.md](plan.md) technical context

## Overview

This document defines the relational data model for the voter data management
system. All entities map to PostgreSQL tables with PostGIS extensions for
geospatial columns. SQLAlchemy 2.x declarative models with GeoAlchemy2 types
are used throughout.

## Entity Relationship Diagram (Text)

```text
User ─────────────────────┐
  │                       │
  │ triggers              │ actor
  ▼                       ▼
ImportJob              AuditLog
  │
  │ produces
  ▼
Voter ◄──────────────── AnalysisResult
  │                          │
  │ has many                 │ belongs to
  ▼                          ▼
GeocodedLocation        AnalysisRun
  │
  │ cached via
  ▼
GeocoderCache

Boundary (independent, spatial join with Voter via GeocodedLocation)

ExportJob (independent, references filter criteria)
```

## Entities

### 1. Voter

**Table**: `voters`
**Description**: Individual voter record sourced from the Georgia Secretary of
State voter file. This is the central entity of the system.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | Internal surrogate key |
| county | VARCHAR(100) | NOT NULL, INDEX | First-class filter |
| voter_registration_number | VARCHAR(20) | UNIQUE, NOT NULL, INDEX | SoS unique ID |
| status | VARCHAR(20) | NOT NULL | ACTIVE, INACTIVE, etc. |
| status_reason | VARCHAR(100) | NULLABLE | e.g., CROSS STATE, NCOA |
| last_name | VARCHAR(100) | NOT NULL, INDEX | |
| first_name | VARCHAR(100) | NOT NULL, INDEX | |
| middle_name | VARCHAR(100) | NULLABLE | |
| suffix | VARCHAR(20) | NULLABLE | |
| birth_year | INTEGER | NULLABLE | 4-digit year |
| residence_street_number | VARCHAR(20) | NULLABLE | |
| residence_pre_direction | VARCHAR(10) | NULLABLE | N, S, E, W, etc. |
| residence_street_name | VARCHAR(100) | NULLABLE | |
| residence_street_type | VARCHAR(20) | NULLABLE | ST, AVE, BLVD, etc. |
| residence_post_direction | VARCHAR(10) | NULLABLE | |
| residence_apt_unit_number | VARCHAR(20) | NULLABLE | |
| residence_city | VARCHAR(100) | NULLABLE | |
| residence_zipcode | VARCHAR(10) | NULLABLE | INDEX |
| mailing_street_number | VARCHAR(20) | NULLABLE | |
| mailing_street_name | VARCHAR(100) | NULLABLE | |
| mailing_apt_unit_number | VARCHAR(20) | NULLABLE | |
| mailing_city | VARCHAR(100) | NULLABLE | |
| mailing_zipcode | VARCHAR(10) | NULLABLE | |
| mailing_state | VARCHAR(50) | NULLABLE | |
| mailing_country | VARCHAR(50) | NULLABLE | |
| county_precinct | VARCHAR(20) | NULLABLE | Registered code |
| county_precinct_description | VARCHAR(200) | NULLABLE | |
| municipal_precinct | VARCHAR(20) | NULLABLE | Registered code |
| municipal_precinct_description | VARCHAR(200) | NULLABLE | |
| congressional_district | VARCHAR(10) | NULLABLE | Registered |
| state_senate_district | VARCHAR(10) | NULLABLE | Registered |
| state_house_district | VARCHAR(10) | NULLABLE | Registered |
| judicial_district | VARCHAR(10) | NULLABLE | Registered |
| county_commission_district | VARCHAR(10) | NULLABLE | Registered |
| school_board_district | VARCHAR(10) | NULLABLE | Registered |
| city_council_district | VARCHAR(10) | NULLABLE | Registered |
| municipal_school_board_district | VARCHAR(10) | NULLABLE | Registered |
| water_board_district | VARCHAR(10) | NULLABLE | Registered |
| super_council_district | VARCHAR(10) | NULLABLE | Registered |
| super_commissioner_district | VARCHAR(10) | NULLABLE | Registered |
| super_school_board_district | VARCHAR(10) | NULLABLE | Registered |
| fire_district | VARCHAR(10) | NULLABLE | Registered |
| municipality | VARCHAR(100) | NULLABLE | |
| combo | VARCHAR(20) | NULLABLE | SoS combo code |
| land_lot | VARCHAR(20) | NULLABLE | |
| land_district | VARCHAR(20) | NULLABLE | |
| registration_date | DATE | NULLABLE | |
| race | VARCHAR(20) | NULLABLE | |
| gender | VARCHAR(10) | NULLABLE | |
| last_modified_date | DATE | NULLABLE | SoS last modified |
| date_of_last_contact | DATE | NULLABLE | |
| last_party_voted | VARCHAR(20) | NULLABLE | |
| last_vote_date | DATE | NULLABLE | |
| voter_created_date | DATE | NULLABLE | SoS creation date |
| present_in_latest_import | BOOLEAN | NOT NULL, DEFAULT TRUE | Soft-delete tracking |
| last_seen_in_import_id | UUID | FK → import_jobs.id, NULLABLE | Last import containing this voter |
| first_seen_in_import_id | UUID | FK → import_jobs.id, NULLABLE | First import containing this voter |
| soft_deleted_at | TIMESTAMP | NULLABLE | Set when absent from latest import |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | System timestamp |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW | System timestamp, auto-update |

**Indexes**:
- `ix_voters_county` — B-tree on `county`
- `ix_voters_registration_number` — Unique B-tree on `voter_registration_number`
- `ix_voters_last_name` — B-tree on `last_name`
- `ix_voters_first_name` — B-tree on `first_name`
- `ix_voters_residence_zipcode` — B-tree on `residence_zipcode`
- `ix_voters_status` — B-tree on `status`
- `ix_voters_county_precinct` — B-tree on `county_precinct`
- `ix_voters_congressional_district` — B-tree on `congressional_district`
- `ix_voters_present_in_latest` — B-tree on `present_in_latest_import`
- `ix_voters_name_search` — Composite on `(last_name, first_name)`

**Relationships**:
- One-to-many → `GeocodedLocation` (zero or more, one per source)
- Many-to-one → `ImportJob` (last_seen, first_seen)

---

### 2. GeocodedLocation

**Table**: `geocoded_locations`
**Description**: A single geocoding result for a voter's residence address
from a specific source. A voter may have multiple records (one per provider
plus manual entries).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| voter_id | UUID | FK → voters.id, NOT NULL, INDEX | |
| latitude | DOUBLE PRECISION | NOT NULL | WGS 84 |
| longitude | DOUBLE PRECISION | NOT NULL | WGS 84 |
| point | GEOMETRY(Point, 4326) | NOT NULL, SPATIAL INDEX | PostGIS point |
| confidence_score | DOUBLE PRECISION | NULLABLE | 0.0–1.0, provider-specific |
| source_type | VARCHAR(50) | NOT NULL | Provider name, "manual", "field-survey" |
| is_primary | BOOLEAN | NOT NULL, DEFAULT FALSE | One per voter must be TRUE |
| input_address | TEXT | NULLABLE | Reconstructed address sent to geocoder |
| geocoded_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |

**Indexes**:
- `ix_geocoded_voter_id` — B-tree on `voter_id`
- `ix_geocoded_point` — GIST spatial index on `point`
- `ix_geocoded_source` — B-tree on `source_type`
- `ix_geocoded_primary` — Partial index on `voter_id` WHERE `is_primary = TRUE`

**Constraints**:
- Unique constraint on `(voter_id, source_type)` — one result per
  provider per voter
- Application-level enforcement: exactly one `is_primary = TRUE` per voter
  (enforced via service layer, not DB constraint, to allow atomic swaps)

**Relationships**:
- Many-to-one → `Voter`

---

### 3. GeocoderCache

**Table**: `geocoder_cache`
**Description**: Cached geocoding response keyed by provider and normalized
address. Avoids redundant external API calls.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| provider | VARCHAR(50) | NOT NULL | Provider name |
| normalized_address | TEXT | NOT NULL | Normalized input address |
| latitude | DOUBLE PRECISION | NOT NULL | |
| longitude | DOUBLE PRECISION | NOT NULL | |
| confidence_score | DOUBLE PRECISION | NULLABLE | |
| raw_response | JSONB | NULLABLE | Full provider response |
| cached_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |

**Indexes**:
- `ix_cache_provider_address` — Unique composite on `(provider, normalized_address)`

**Constraints**:
- Unique on `(provider, normalized_address)` — one cache entry per
  provider per normalized address

---

### 4. GeocodingJob

**Table**: `geocoding_jobs`
**Description**: Tracks a batch geocoding operation. Persists job state
for progress tracking, checkpoint/resume, and API status queries.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| provider | VARCHAR(50) | NOT NULL | Geocoder provider used |
| county | VARCHAR(100) | NULLABLE | County filter (NULL = all) |
| force_regeocode | BOOLEAN | NOT NULL, DEFAULT FALSE | Re-geocode already geocoded |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | pending, running, completed, failed |
| total_records | INTEGER | NULLABLE | Total voters to geocode |
| processed | INTEGER | NULLABLE | Records processed so far |
| succeeded | INTEGER | NULLABLE | |
| failed | INTEGER | NULLABLE | |
| cache_hits | INTEGER | NULLABLE | |
| last_processed_voter_offset | INTEGER | NULLABLE | Checkpoint for resume |
| error_log | JSONB | NULLABLE | Array of error objects |
| triggered_by | UUID | NULLABLE | User ID who triggered |
| started_at | TIMESTAMP | NULLABLE | |
| completed_at | TIMESTAMP | NULLABLE | |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |

**Indexes**:
- `ix_geocoding_job_status` — B-tree on `status`
- `ix_geocoding_job_created_at` — B-tree on `created_at`

---

### 5. Boundary

**Table**: `boundaries`
**Description**: Political or administrative district/precinct boundary
polygon from state or county GIS data.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| name | VARCHAR(200) | NOT NULL | Human-readable name |
| boundary_type | VARCHAR(50) | NOT NULL, INDEX | See enum below |
| boundary_identifier | VARCHAR(50) | NOT NULL | District number/code |
| source | VARCHAR(20) | NOT NULL | "state" or "county" |
| county | VARCHAR(100) | NULLABLE, INDEX | NULL for statewide boundaries |
| geometry | GEOMETRY(MultiPolygon, 4326) | NOT NULL, SPATIAL INDEX | PostGIS geometry |
| effective_date | DATE | NULLABLE | When boundary took effect |
| properties | JSONB | NULLABLE | Additional GIS metadata |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |

**Boundary Types** (enum or check constraint):
- `congressional`
- `state_senate`
- `state_house`
- `judicial`
- `county_commission`
- `school_board`
- `city_council`
- `municipal_school_board`
- `water_board`
- `super_council`
- `super_commissioner`
- `super_school_board`
- `fire_district`
- `county_precinct`
- `municipal_precinct`

**Indexes**:
- `ix_boundary_type` — B-tree on `boundary_type`
- `ix_boundary_county` — B-tree on `county`
- `ix_boundary_geometry` — GIST spatial index on `geometry`
- `ix_boundary_type_identifier` — Unique composite on
  `(boundary_type, boundary_identifier, county)` — prevents duplicate
  boundaries

**Relationships**:
- Spatial join with `GeocodedLocation` via `ST_Contains` /
  `ST_Within` / `ST_Intersects`

---

### 6. User

**Table**: `users`
**Description**: Authenticated human user of the system with role-based
access control.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| username | VARCHAR(100) | UNIQUE, NOT NULL | |
| email | VARCHAR(255) | UNIQUE, NOT NULL | |
| hashed_password | VARCHAR(255) | NOT NULL | bcrypt hash |
| role | VARCHAR(20) | NOT NULL | admin, analyst, viewer |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE | |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |
| last_login_at | TIMESTAMP | NULLABLE | |

**Indexes**:
- `ix_users_username` — Unique B-tree on `username`
- `ix_users_email` — Unique B-tree on `email`

---

### 7. AuditLog

**Table**: `audit_logs`
**Description**: Immutable record of data access events. Write-only
(no updates or deletes).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| timestamp | TIMESTAMP | NOT NULL, DEFAULT NOW, INDEX | |
| user_id | UUID | NOT NULL | From JWT claims, no FK (immutable) |
| username | VARCHAR(100) | NOT NULL | Denormalized for query convenience |
| action | VARCHAR(20) | NOT NULL | view, query, export, import, analyze, update |
| resource_type | VARCHAR(50) | NOT NULL | voter, boundary, analysis, etc. |
| resource_ids | JSONB | NULLABLE | Array of affected resource IDs |
| request_ip | VARCHAR(45) | NULLABLE | IPv4 or IPv6 |
| request_endpoint | VARCHAR(255) | NULLABLE | |
| request_metadata | JSONB | NULLABLE | Additional context |

**Indexes**:
- `ix_audit_timestamp` — B-tree on `timestamp`
- `ix_audit_user_id` — B-tree on `user_id`
- `ix_audit_action` — B-tree on `action`
- `ix_audit_resource_type` — B-tree on `resource_type`

**Note**: No foreign key to `users` table — audit logs are retained
independently of user lifecycle and reference user ID from the JWT.

---

### 7. ImportJob

**Table**: `import_jobs`
**Description**: Tracks a data import operation (voter file or boundary file).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| file_name | VARCHAR(255) | NOT NULL | Original file name |
| file_type | VARCHAR(20) | NOT NULL | "voter_csv", "shapefile", "geojson" |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | pending, running, completed, failed |
| total_records | INTEGER | NULLABLE | Total records in file |
| records_succeeded | INTEGER | NULLABLE | |
| records_failed | INTEGER | NULLABLE | |
| records_inserted | INTEGER | NULLABLE | New records |
| records_updated | INTEGER | NULLABLE | Existing records updated |
| records_soft_deleted | INTEGER | NULLABLE | Voters absent from new import |
| error_log | JSONB | NULLABLE | Array of error objects |
| triggered_by | UUID | NULLABLE | User ID who triggered |
| started_at | TIMESTAMP | NULLABLE | |
| completed_at | TIMESTAMP | NULLABLE | |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |

**Indexes**:
- `ix_import_status` — B-tree on `status`
- `ix_import_file_type` — B-tree on `file_type`
- `ix_import_created_at` — B-tree on `created_at`

---

### 8. ExportJob

**Table**: `export_jobs`
**Description**: Tracks a bulk data export operation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| filters | JSONB | NOT NULL | Applied filter criteria |
| output_format | VARCHAR(20) | NOT NULL | csv, json, geojson |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | pending, running, completed, failed |
| record_count | INTEGER | NULLABLE | |
| file_path | VARCHAR(500) | NULLABLE | Path to generated file |
| file_size_bytes | BIGINT | NULLABLE | |
| triggered_by | UUID | NULLABLE | User ID who triggered |
| requested_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |
| completed_at | TIMESTAMP | NULLABLE | |

**Indexes**:
- `ix_export_status` — B-tree on `status`
- `ix_export_triggered_by` — B-tree on `triggered_by`

---

### 9. AnalysisRun

**Table**: `analysis_runs`
**Description**: A single execution of the location analysis process.
Each run produces a complete snapshot of results.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| triggered_by | UUID | NULLABLE | User ID |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | pending, running, completed, failed |
| total_voters_analyzed | INTEGER | NULLABLE | |
| match_count | INTEGER | NULLABLE | |
| mismatch_count | INTEGER | NULLABLE | |
| unable_to_analyze_count | INTEGER | NULLABLE | |
| notes | TEXT | NULLABLE | e.g., "post-redistricting re-analysis" |
| started_at | TIMESTAMP | NULLABLE | |
| completed_at | TIMESTAMP | NULLABLE | |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |

**Indexes**:
- `ix_analysis_run_status` — B-tree on `status`
- `ix_analysis_run_created_at` — B-tree on `created_at`

---

### 10. AnalysisResult

**Table**: `analysis_results`
**Description**: Outcome of comparing a voter's physical location to their
registration within a specific analysis run. Immutable once the parent run
completes.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen | |
| analysis_run_id | UUID | FK → analysis_runs.id, NOT NULL, INDEX | |
| voter_id | UUID | FK → voters.id, NOT NULL, INDEX | |
| determined_boundaries | JSONB | NOT NULL | Map of boundary_type → boundary_identifier |
| registered_boundaries | JSONB | NOT NULL | Map of boundary_type → registered value |
| match_status | VARCHAR(30) | NOT NULL | match, mismatch-district, mismatch-precinct, mismatch-both, unable-to-analyze |
| mismatch_details | JSONB | NULLABLE | Array of {type, registered, determined} |
| analyzed_at | TIMESTAMP | NOT NULL, DEFAULT NOW | |

**Indexes**:
- `ix_result_run_id` — B-tree on `analysis_run_id`
- `ix_result_voter_id` — B-tree on `voter_id`
- `ix_result_match_status` — B-tree on `match_status`
- `ix_result_run_voter` — Unique composite on `(analysis_run_id, voter_id)`

**Relationships**:
- Many-to-one → `AnalysisRun`
- Many-to-one → `Voter`

---

## State Transitions

### ImportJob Status

```text
pending → running → completed
                  → failed
```

### ExportJob Status

```text
pending → running → completed
                  → failed
```

### AnalysisRun Status

```text
pending → running → completed
                  → failed
```

### Voter Soft-Delete Lifecycle

```text
[New Import]
  → present_in_latest_import = TRUE, soft_deleted_at = NULL

[Absent from next import]
  → present_in_latest_import = FALSE, soft_deleted_at = NOW

[Reappears in future import]
  → present_in_latest_import = TRUE, soft_deleted_at = NULL
```

## Validation Rules

| Entity | Field | Rule |
|--------|-------|------|
| Voter | voter_registration_number | Required, unique, alphanumeric |
| Voter | status | Required, enum: ACTIVE, INACTIVE |
| Voter | county | Required, non-empty |
| Voter | last_name | Required, non-empty |
| Voter | first_name | Required, non-empty |
| Voter | birth_year | If present, 4-digit integer, 1900–current year |
| Voter | registration_date | If present, valid date, not future |
| GeocodedLocation | latitude | -90.0 to 90.0 |
| GeocodedLocation | longitude | -180.0 to 180.0 |
| GeocodedLocation | source_type | Required, non-empty |
| GeocoderCache | provider | Required, non-empty |
| GeocoderCache | normalized_address | Required, non-empty |
| Boundary | boundary_type | Required, one of 15 defined types |
| Boundary | geometry | Required, valid MultiPolygon, ST_IsValid |
| User | username | Required, unique, 3–100 chars |
| User | email | Required, unique, valid email format |
| User | role | Required, enum: admin, analyst, viewer |
| User | hashed_password | Required, bcrypt format |

## Data Volume Estimates

| Entity | Initial (2 counties) | Statewide (159 counties) |
|--------|---------------------|--------------------------|
| Voter | ~500,000 | ~7,000,000 |
| GeocodedLocation | ~500,000–1,500,000 | ~7,000,000–21,000,000 |
| GeocoderCache | ~300,000 | ~5,000,000 |
| Boundary | ~500–2,000 | ~10,000–50,000 |
| AnalysisResult (per run) | ~500,000 | ~7,000,000 |
| AuditLog | Growth over time | Millions/year |

## Migration Strategy

All schema changes managed via Alembic. Initial migration creates all tables
with PostGIS extensions (`CREATE EXTENSION IF NOT EXISTS postgis`). Spatial
indexes created in the migration. GeoAlchemy2 column types are handled by
Alembic with the `geoalchemy2` dialect registered.
