# Elected Officials Data Model

## Overview

This document defines the database schema for managing elected official records. The data model is designed to:

- Store canonical elected official records served by the API (one per seat/district)
- Cache raw responses from multiple external data providers (Open States, Google Civic, etc.)
- Support an admin approval workflow (auto -> approved <- manual)
- Enable flexible district linkage without foreign key coupling to boundary geometries
- Preserve data provenance and multi-source comparison

## Entities

### elected_officials

The canonical elected official record served by the API. Represents the admin-approved (or auto-populated) view of who holds a given office. One record per seat/district at a time.

**Key Design Choices**:
- Soft join to boundaries via `(boundary_type, district_identifier)` — no FK, since officials may be entered before boundary geometries are imported
- Three-state approval workflow: `auto` (populated from automated source, not yet reviewed), `approved` (admin verified), `manual` (admin manually entered or overrode)
- `external_ids` JSONB stores flexible cross-reference identifiers (bioguide_id, open_states_id, etc.)
- `approved_by_id` FK to `users` tracks which admin approved the record

### elected_official_sources

Cached responses from external data providers. Each row represents a single provider's view of an elected official for a given district. Multiple sources may exist for the same seat.

**Key Design Choices**:
- Nullable FK to `elected_officials` with `ON DELETE SET NULL` — sources persist even if the canonical record is deleted (orphaned sources can be re-matched later)
- Denormalized `boundary_type` and `district_identifier` fields enable querying unmatched sources by district without joining to the canonical record
- `raw_data` JSONB preserves the full provider response for debugging and re-processing
- Normalized fields (`full_name`, `party`, etc.) are extracted from `raw_data` for display and comparison
- `is_current` flag distinguishes latest vs historical fetches from the same provider
- `source_name` + `source_record_id` unique constraint prevents duplicate source records

## Schema

### elected_officials

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid_generate_v4() | Primary key |
| boundary_type | VARCHAR(50) | NOT NULL, indexed | District boundary type (e.g. "congressional", "state_senate") |
| district_identifier | VARCHAR(50) | NOT NULL | District identifier (e.g. "18", "GA-05") |
| full_name | VARCHAR(200) | NOT NULL | Official's full name |
| first_name | VARCHAR(100) | NULL | First name |
| last_name | VARCHAR(100) | NULL | Last name |
| party | VARCHAR(50) | NULL | Party affiliation |
| title | VARCHAR(100) | NULL | Office title (e.g. "State Senator") |
| photo_url | TEXT | NULL | URL to official's photo |
| term_start_date | DATE | NULL | Term start date |
| term_end_date | DATE | NULL | Term end date |
| last_election_date | DATE | NULL | Date of last election |
| next_election_date | DATE | NULL | Date of next election |
| website | TEXT | NULL | Official's website |
| email | VARCHAR(200) | NULL | Contact email |
| phone | VARCHAR(50) | NULL | Contact phone |
| office_address | TEXT | NULL | Office address |
| external_ids | JSONB | NULL | External identifiers for cross-referencing |
| status | VARCHAR(20) | NOT NULL, default 'auto' | Approval status: "auto", "approved", "manual" |
| approved_by_id | UUID | FK -> users.id, NULL | Admin who approved the record |
| approved_at | TIMESTAMPTZ | NULL | When the record was approved |
| created_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record last modified timestamp |

**Constraints**:
- `UNIQUE (boundary_type, district_identifier, full_name)` — prevents duplicate officials per district (`uq_official_district_name`)
- `CHECK (status IN ('auto', 'approved', 'manual'))` — enforce valid status values (`ck_official_status`)

**Indexes**:
- `ix_elected_officials_boundary_type` on `(boundary_type)` — filter by boundary type
- `ix_elected_officials_district` on `(boundary_type, district_identifier)` — lookup officials for a district
- `ix_elected_officials_name` on `(last_name, first_name)` — name-based searches

### elected_official_sources

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default uuid_generate_v4() | Primary key |
| elected_official_id | UUID | FK -> elected_officials.id (ON DELETE SET NULL), NULL, indexed | Link to canonical record (nullable until matched) |
| source_name | VARCHAR(50) | NOT NULL, indexed | Data provider name (e.g. "open_states", "google_civic") |
| source_record_id | VARCHAR(200) | NOT NULL | Unique identifier from the source provider |
| boundary_type | VARCHAR(50) | NOT NULL | Boundary type (denormalized for unmatched-source queries) |
| district_identifier | VARCHAR(50) | NOT NULL | District identifier (denormalized) |
| raw_data | JSONB | NULL | Full cached response from the provider |
| full_name | VARCHAR(200) | NOT NULL | Official's full name (normalized from raw_data) |
| first_name | VARCHAR(100) | NULL | First name |
| last_name | VARCHAR(100) | NULL | Last name |
| party | VARCHAR(50) | NULL | Party affiliation |
| title | VARCHAR(100) | NULL | Office title |
| photo_url | TEXT | NULL | Photo URL |
| term_start_date | DATE | NULL | Term start date (if available from source) |
| term_end_date | DATE | NULL | Term end date (if available from source) |
| website | TEXT | NULL | Website |
| email | VARCHAR(200) | NULL | Contact email |
| phone | VARCHAR(50) | NULL | Contact phone |
| office_address | TEXT | NULL | Office address |
| fetched_at | TIMESTAMPTZ | NOT NULL, server_default now() | When this record was fetched from the provider |
| is_current | BOOLEAN | NOT NULL, default true | Whether this is the latest record from this source |
| created_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record last modified timestamp |

**Constraints**:
- `UNIQUE (source_name, source_record_id)` — one record per provider-identifier pair (`uq_source_record`)

**Indexes**:
- `ix_elected_official_sources_elected_official_id` on `(elected_official_id)` — find sources for a canonical record
- `ix_elected_official_sources_source_name` on `(source_name)` — filter by provider
- `ix_source_district` on `(boundary_type, district_identifier)` — find sources for a district (including unmatched)

## Relationships

```
elected_officials (1) ──< (*) elected_official_sources
        │                              │
        │ soft join                    │ FK (ON DELETE SET NULL)
        │ (boundary_type,             │
        │  district_identifier)        │
        │                              │
boundaries (boundary_type + boundary_identifier)
```

**Foreign Keys**:
- `elected_official_sources.elected_official_id` -> `elected_officials.id` (ON DELETE SET NULL)
- `elected_officials.approved_by_id` -> `users.id`

**Soft Join** (no FK):
- `elected_officials.(boundary_type, district_identifier)` <-> `boundaries.(boundary_type, boundary_identifier)` — matches officials to their district boundary geometry

## Entity-Relationship Diagram

```
┌─────────────────────────────────────────┐
│ elected_officials                       │
├─────────────────────────────────────────┤
│ id (PK)                        UUID     │
│ boundary_type                  VARCHAR  │
│ district_identifier            VARCHAR  │
│ full_name                      VARCHAR  │
│ first_name                     VARCHAR  │
│ last_name                      VARCHAR  │
│ party                          VARCHAR  │
│ title                          VARCHAR  │
│ photo_url                      TEXT     │
│ term_start_date                DATE     │
│ term_end_date                  DATE     │
│ last_election_date             DATE     │
│ next_election_date             DATE     │
│ website                        TEXT     │
│ email                          VARCHAR  │
│ phone                          VARCHAR  │
│ office_address                 TEXT     │
│ external_ids                   JSONB    │
│ status                         VARCHAR  │
│ approved_by_id (FK)            UUID     │
│ approved_at                    TIMESTAMPTZ │
│ created_at                     TIMESTAMPTZ │
│ updated_at                     TIMESTAMPTZ │
└────────────┬────────────────────────────┘
             │
             │ 1
             │
             │ * (ON DELETE SET NULL)
             │
┌────────────▼────────────────────────────┐
│ elected_official_sources                │
├─────────────────────────────────────────┤
│ id (PK)                        UUID     │
│ elected_official_id (FK, NULL) UUID     │
│ source_name                    VARCHAR  │
│ source_record_id               VARCHAR  │
│ boundary_type                  VARCHAR  │
│ district_identifier            VARCHAR  │
│ raw_data                       JSONB    │
│ full_name                      VARCHAR  │
│ first_name                     VARCHAR  │
│ last_name                      VARCHAR  │
│ party                          VARCHAR  │
│ title                          VARCHAR  │
│ photo_url                      TEXT     │
│ term_start_date                DATE     │
│ term_end_date                  DATE     │
│ website                        TEXT     │
│ email                          VARCHAR  │
│ phone                          VARCHAR  │
│ office_address                 TEXT     │
│ fetched_at                     TIMESTAMPTZ │
│ is_current                     BOOLEAN  │
│ created_at                     TIMESTAMPTZ │
│ updated_at                     TIMESTAMPTZ │
└─────────────────────────────────────────┘
```

## Design Decisions

### 1. Soft join to boundaries (no FK)

**Decision**: Link officials to districts via `(boundary_type, district_identifier)` without a foreign key to the `boundaries` table.

**Rationale**:
- Officials may be entered (manually or from a data provider) before boundary geometries are imported
- Boundary imports may be refreshed independently of official data
- The two-column composite key naturally matches the boundary table's `(boundary_type, boundary_identifier)` pair
- Avoids circular dependency between data ingestion pipelines

**Trade-offs**:
- No referential integrity enforcement at the database level
- Application code must handle the case where a district has no matching boundary

### 2. Three-state approval workflow

**Decision**: Use `auto`, `approved`, and `manual` status values instead of a boolean `is_approved` flag.

**Rationale**:
- Distinguishes auto-populated records (from data providers) that haven't been reviewed from those that have been explicitly approved
- `manual` status differentiates admin-created records from auto-populated ones
- Enables audit trail: `approved_by_id` and `approved_at` record who approved and when
- Supports future workflow extensions (e.g. "pending_review", "rejected") via the VARCHAR column

### 3. ON DELETE SET NULL for sources

**Decision**: When a canonical `elected_officials` record is deleted, set `elected_official_id` to NULL on linked sources rather than cascading the delete.

**Rationale**:
- Source records represent cached provider data — they have value independent of the canonical record
- Orphaned sources can be re-matched to a new canonical record if one is created
- Prevents data loss when admin restructures canonical records
- The application cascade on the ORM relationship (`cascade="all, delete-orphan"`) handles the common case; the DB-level SET NULL is a safety net

### 4. Denormalized district fields on sources

**Decision**: Store `boundary_type` and `district_identifier` directly on source records, duplicating the canonical record's district fields.

**Rationale**:
- Enables querying sources by district even when `elected_official_id` is NULL (unmatched sources)
- The district sources endpoint (`GET /elected-officials/district/{boundary_type}/{district_identifier}/sources`) needs this for its query
- Avoids a join to `elected_officials` for source-centric queries
- Immutable per source record (set at fetch time), so no update anomaly risk

### 5. JSONB external_ids

**Decision**: Use a JSONB column for external identifiers rather than a normalized key-value table.

**Rationale**:
- Each data provider has its own identifier scheme (bioguide_id, open_states_id, google_civic_id, etc.)
- The set of identifier types is open-ended and evolves as new providers are added
- JSONB enables efficient `@>` containment queries for lookups (e.g. find official by Open States ID)
- A dedicated table would add complexity with no clear benefit for the expected query patterns

## Migration Notes

### Prerequisites

Requires:
- PostgreSQL 12+ with JSONB support
- `uuid-ossp` extension (for `uuid_generate_v4()`)
- Existing `users` table (for `approved_by_id` FK)

### Migration: 015_elected_officials

1. **Create `elected_officials` table** with UUIDMixin, TimestampMixin, all columns
2. **Create indexes**: `ix_elected_officials_district`, `ix_elected_officials_name`
3. **Create unique constraint**: `uq_official_district_name` on `(boundary_type, district_identifier, full_name)`
4. **Create check constraint**: `ck_official_status` ensuring status IN ('auto', 'approved', 'manual')
5. **Create `elected_official_sources` table** with UUIDMixin, TimestampMixin, all columns
6. **Create indexes**: `ix_source_district`
7. **Create unique constraint**: `uq_source_record` on `(source_name, source_record_id)`

### Downgrade

Drops both tables in reverse order (`elected_official_sources` first, then `elected_officials`).

## References

- **API Contract**: `specs/005-elected-officials/contracts/openapi.yaml`
- **SQLAlchemy Models**: `src/voter_api/models/elected_official.py`
- **Alembic Migration**: `alembic/versions/015_elected_officials.py`
- **SQLAlchemy Base**: `src/voter_api/models/base.py` (UUIDMixin, TimestampMixin, Base)
