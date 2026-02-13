# Data Model: Single-Address Geocoding Endpoint

**Feature**: 003-address-geocoding-endpoint
**Date**: 2026-02-13

## Overview

This feature introduces a **new `addresses` table** as the canonical address store and modifies two existing tables (`geocoder_cache` and `voters`) to reference it via FK. The three API endpoints operate across these tables:

- **`addresses`** *(new)* — canonical address store with parsed components + normalized string
- **`geocoder_cache`** *(modified)* — provider-specific geocoding results, now linked to addresses via FK
- **`voters`** *(modified)* — adds `residence_address_id` FK to addresses (inline fields retained as government-sourced truth)
- **`boundaries`** *(unchanged)* — geospatial boundary polygons for point-lookup endpoint

## New Entity

### Address

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Primary key |
| `normalized_address` | TEXT | NOT NULL, UNIQUE | Normalized freeform address string (USPS-abbreviated, uppercased, whitespace-collapsed). Used as deduplication key and for cache/provider lookups. |
| `street_number` | VARCHAR(20) | NULLABLE | House/building number |
| `pre_direction` | VARCHAR(10) | NULLABLE | Pre-directional (N, S, E, W, NE, NW, SE, SW) |
| `street_name` | VARCHAR(100) | NULLABLE | Street name |
| `street_type` | VARCHAR(20) | NULLABLE | USPS street type abbreviation (ST, AVE, BLVD, etc.) |
| `post_direction` | VARCHAR(10) | NULLABLE | Post-directional |
| `apt_unit` | VARCHAR(20) | NULLABLE | Apartment/unit/suite number |
| `city` | VARCHAR(100) | NULLABLE | City name |
| `state` | VARCHAR(2) | NULLABLE | State abbreviation (e.g., GA) |
| `zipcode` | VARCHAR(10) | NULLABLE | ZIP code (5-digit or ZIP+4) |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | When the address record was created |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | When the address record was last updated |

**Why components are nullable**: Addresses can be created from freeform API input where parsing may not extract all components. The `normalized_address` string is always present (NOT NULL) and serves as the canonical representation. Components are best-effort parsed and used for structured display/queries.

**Constraints**:
- `uq_address_normalized` — UNIQUE(`normalized_address`)

**Indexes**:
- `ix_addresses_normalized_prefix` — B-tree with `text_pattern_ops` on `normalized_address` (prefix search for autocomplete)
- `ix_addresses_zipcode` — B-tree on `zipcode` (geographic filtering)
- `ix_addresses_city_state` — B-tree on `(city, state)` (geographic filtering)

## Modified Entities

### GeocoderCache (modified)

**New column**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `address_id` | UUID | NULLABLE, FK → `addresses.id` | Link to canonical address record. Nullable for backward compatibility with existing rows. |

**New index**:
- `ix_geocoder_cache_address_id` — B-tree on `address_id` (FK lookup)

**Existing columns, constraints, and indexes**: Unchanged. The `(provider, normalized_address)` unique constraint remains for cache lookup compatibility.

**Relationship**: Many geocoder_cache rows can reference the same address (one per provider).

### Voter (modified)

**New column**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `residence_address_id` | UUID | NULLABLE, FK → `addresses.id` | Link to canonical address record. Nullable because existing rows won't have it until backfill. |

**New index**:
- `ix_voters_residence_address_id` — B-tree on `residence_address_id` (FK lookup)

**Existing columns**: All inline residence address fields (`residence_street_number`, `residence_street_name`, etc.) are permanently retained. They represent government-sourced truth from the GA Secretary of State voter file and are not replaced by the FK.

**Two-phase pipeline**: The inline address fields are populated during CSV import (phase 1) directly from the voter file. The `residence_address_id` FK is NOT set during import — raw voter data is frequently malformed and the `addresses` table is a canonical, validated store. Instead, the FK is set during post-import processing (phase 2) after the address has been normalized and successfully geocoded. The post-import step normalizes the inline components into a `normalized_address`, attempts geocoding, and on success upserts into the `addresses` table and sets the FK. Voters whose addresses fail validation or geocoding retain `residence_address_id IS NULL` until resolved.

### Boundary (unchanged)

No modifications. Existing schema and indexes are sufficient for point-in-polygon queries.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Primary key |
| `name` | VARCHAR(200) | NOT NULL | Boundary display name |
| `boundary_type` | VARCHAR(50) | NOT NULL, INDEXED | Type (county, congressional, etc.) |
| `boundary_identifier` | VARCHAR(50) | NOT NULL | Unique identifier within type |
| `source` | VARCHAR(20) | NOT NULL | Data source (state/county) |
| `county` | VARCHAR(100) | NULLABLE, INDEXED | County name |
| `geometry` | MULTIPOLYGON | NOT NULL, GIST INDEX | PostGIS geometry (SRID 4326) |
| `effective_date` | DATE | NULLABLE | Boundary effective date |
| `properties` | JSONB | NULLABLE | Type-specific metadata |
| `created_at` | TIMESTAMPTZ | NOT NULL | Record creation time |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update time |

## Migrations

### Migration 1: Create addresses table + FK columns

```sql
-- Create addresses table
CREATE TABLE addresses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_address TEXT NOT NULL,
    street_number VARCHAR(20),
    pre_direction VARCHAR(10),
    street_name VARCHAR(100),
    street_type VARCHAR(20),
    post_direction VARCHAR(10),
    apt_unit VARCHAR(20),
    city VARCHAR(100),
    state VARCHAR(2),
    zipcode VARCHAR(10),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_address_normalized UNIQUE (normalized_address)
);

-- Prefix search index for autocomplete
CREATE INDEX ix_addresses_normalized_prefix
ON addresses (normalized_address text_pattern_ops);

-- Geographic filtering indexes
CREATE INDEX ix_addresses_zipcode ON addresses (zipcode);
CREATE INDEX ix_addresses_city_state ON addresses (city, state);

-- Add FK to geocoder_cache
ALTER TABLE geocoder_cache
ADD COLUMN address_id UUID REFERENCES addresses(id);

CREATE INDEX ix_geocoder_cache_address_id ON geocoder_cache (address_id);

-- Add FK to voters
ALTER TABLE voters
ADD COLUMN residence_address_id UUID REFERENCES addresses(id);

CREATE INDEX ix_voters_residence_address_id ON voters (residence_address_id);
```

**Migration type**: Alembic revision. Non-destructive — adds a new table and nullable columns. Safe to run on a live database.

### Migration 2: Geocoder Cache Backfill (data migration)

A separate Alembic data migration that backfills geocoder cache address links:

1. Iterates unique `normalized_address` values in `geocoder_cache`
2. Parses components from the normalized string (best-effort)
3. Inserts into `addresses` table
4. Updates `geocoder_cache.address_id` to link to the new address row

This is idempotent (safe to re-run). Does NOT backfill voters — voter `residence_address_id` is set by the post-import address processing pipeline (a separate service method or CLI command) because raw voter addresses require normalization and geocoding before linking to the canonical address store. See "Post-Import Address Processing" in Data Flow below.

## Query Patterns

### Geocode Endpoint

```sql
-- Step 1: Cache lookup via geocoder_cache (existing pattern, unchanged)
SELECT gc.*, a.normalized_address
FROM geocoder_cache gc
LEFT JOIN addresses a ON gc.address_id = a.id
WHERE gc.provider = :provider AND gc.normalized_address = :address;

-- Step 2 (on cache miss + successful provider result): Upsert address
INSERT INTO addresses (normalized_address, street_number, street_name, street_type, city, state, zipcode)
VALUES (:normalized, :num, :name, :type, :city, :state, :zip)
ON CONFLICT (normalized_address) DO UPDATE SET updated_at = now()
RETURNING id;

-- Step 3: Store cache entry linked to address
INSERT INTO geocoder_cache (provider, normalized_address, latitude, longitude, confidence_score, raw_response, address_id)
VALUES (:provider, :address, :lat, :lng, :confidence, :raw, :address_id)
ON CONFLICT (provider, normalized_address) DO NOTHING;
```

### Verify Endpoint — Prefix Search

```sql
-- Prefix search on addresses table (replaces geocoder_cache search)
-- Uses DISTINCT ON to pick the highest-confidence provider result per address
SELECT DISTINCT ON (a.normalized_address)
    a.normalized_address, gc.latitude, gc.longitude, gc.confidence_score
FROM addresses a
JOIN geocoder_cache gc ON gc.address_id = a.id
WHERE a.normalized_address LIKE :prefix || '%'
ORDER BY a.normalized_address, gc.confidence_score DESC NULLS LAST
LIMIT 10;
```

**Note**: With the address table as the canonical store, prefix search is cleaner — no duplicate results from multiple providers for the same address. The JOIN to geocoder_cache fetches the best available coordinates.

### Point-Lookup Endpoint — Point-in-Polygon

```sql
-- Exact point containment (existing, uses GIST spatial index)
SELECT * FROM boundaries
WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326));

-- With accuracy radius (uses GIST spatial index)
SELECT * FROM boundaries
WHERE ST_DWithin(
    geometry,
    ST_SetSRID(ST_MakePoint(:lng, :lat), 4326),
    :accuracy_in_degrees
);
```

### Post-Import Address Processing (Phase 2)

```sql
-- Runs after voter CSV import, processing voters with residence_address_id IS NULL:
-- 1. Select unlinked voters
SELECT id, residence_street_number, residence_pre_direction, residence_street_name,
       residence_street_type, residence_post_direction, residence_apt_unit,
       residence_city, residence_zipcode
FROM voters WHERE residence_address_id IS NULL;

-- 2. For each voter: normalize address components, attempt geocode, on success upsert address row
INSERT INTO addresses (normalized_address, street_number, pre_direction, street_name, street_type, post_direction, apt_unit, city, state, zipcode)
VALUES (:normalized, :num, :pre_dir, :name, :type, :post_dir, :apt, :city, :state, :zip)
ON CONFLICT (normalized_address) DO UPDATE SET updated_at = now()
RETURNING id;

-- 3. Set FK on voter (only after successful geocode + address upsert)
UPDATE voters SET residence_address_id = :address_id WHERE id = :voter_id;
```

## Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│   voters     │       │    addresses     │       │ geocoder_    │
│              │       │                  │       │ cache        │
│ residence_   │──FK──▶│ id               │◀──FK──│ address_id   │
│ address_id   │       │ normalized_addr  │       │ provider     │
│              │       │ street_number    │       │ normalized_  │
│ (inline addr │       │ street_name      │       │ address      │
│  fields kept)│       │ city, state, zip │       │ lat, lng     │
│              │       │ ...              │       │ confidence   │
└──────────────┘       └──────────────────┘       └──────────────┘
                                                         │
                                                   (cache lookup
                                                    still uses
                                                    provider +
                                                    normalized_
                                                    address)
```

## Data Flow

```
Consumer → API Endpoint → Service Layer → Library Layer → PostgreSQL

Geocode:
  address string
  → normalize (lib/geocoder/address.py)
  → cache lookup (geocoder_cache by provider + normalized_address)
  → [miss: provider call → upsert address row → cache store with address_id]
  → response

Verify:
  address string
  → parse components (lib/geocoder/verify.py)
  → validate completeness
  → normalize (lib/geocoder/address.py)
  → prefix search addresses table (JOIN geocoder_cache for coordinates)
  → response

Point-Lookup:
  lat, lng, accuracy
  → Georgia bbox check (lib/geocoder/point_lookup.py)
  → spatial query on boundaries (ST_Contains or ST_DWithin)
  → response

Voter Import (phase 1 — CSV ingestion):
  voter CSV row
  → import voter record (inline fields only)
  → residence_address_id stays NULL

Post-Import Address Processing (phase 2 — runs after import):
  voters with residence_address_id IS NULL
  → reconstruct normalized address from inline components
  → attempt geocode via provider
  → [success: upsert addresses row → set voters.residence_address_id FK]
  → [failure: flag for manual review, FK stays NULL]
```
