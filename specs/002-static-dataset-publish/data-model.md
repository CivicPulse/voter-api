# Data Model: Static Dataset Publishing

**Feature**: 002-static-dataset-publish
**Date**: 2026-02-12

## Overview

This feature does **not** introduce new database tables. Published dataset metadata is stored in a `manifest.json` file on object storage, not in the database. This keeps the publish/redirect system fully decoupled from the database.

## Manifest Schema

The `manifest.json` file is the central data structure. It is stored on R2 alongside the published dataset files and is fetched/cached by the API to determine redirect targets.

### `manifest.json` Structure

```json
{
  "version": "1",
  "published_at": "2026-02-12T15:30:00Z",
  "publisher_version": "0.1.0",
  "datasets": {
    "all-boundaries": {
      "key": "boundaries/all-boundaries.geojson",
      "public_url": "https://geo.example.com/boundaries/all-boundaries.geojson",
      "content_type": "application/geo+json",
      "record_count": 1523,
      "file_size_bytes": 45230100,
      "published_at": "2026-02-12T15:30:00Z",
      "boundary_type": null,
      "filters": {}
    },
    "congressional": {
      "key": "boundaries/congressional.geojson",
      "public_url": "https://geo.example.com/boundaries/congressional.geojson",
      "content_type": "application/geo+json",
      "record_count": 14,
      "file_size_bytes": 2340500,
      "published_at": "2026-02-12T15:30:00Z",
      "boundary_type": "congressional",
      "filters": {
        "boundary_type": "congressional"
      }
    }
  }
}
```

### Field Definitions

#### Root Level

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| `version` | string | yes | Manifest schema version. Currently `"1"`. |
| `published_at` | ISO 8601 datetime | yes | Timestamp of the most recent publish operation. |
| `publisher_version` | string | yes | Version of the publisher library that generated this manifest. |
| `datasets` | object | yes | Map of dataset name to dataset metadata. |

#### Dataset Entry

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| `name` | string | yes | Dataset name (e.g., "congressional", "all-boundaries"). Also used as the key in the `datasets` map. The code DatasetEntry dataclass includes this field for convenience; in JSON it appears only as the map key. |
| `key` | string | yes | S3 object key (path within the bucket). |
| `public_url` | string | yes | Full public URL for consumer access (used as redirect target). |
| `content_type` | string | yes | MIME type of the file. Always `application/geo+json`. |
| `record_count` | integer | yes | Number of boundary features in the file. |
| `file_size_bytes` | integer | yes | File size in bytes. |
| `published_at` | ISO 8601 datetime | yes | Timestamp when this specific dataset was last published. |
| `boundary_type` | string or null | yes | Boundary type filter used to generate this dataset. `null` for the combined file. |
| `filters` | object | yes | Full filter set used to generate this dataset. Empty for the combined file. |

### Dataset Naming Convention

Dataset names in the manifest map directly to the GeoJSON file names:

| Dataset Name | File Key | Description |
| ------------ | -------- | ----------- |
| `all-boundaries` | `boundaries/all-boundaries.geojson` | All boundary types combined |
| `congressional` | `boundaries/congressional.geojson` | Congressional districts only |
| `state_senate` | `boundaries/state_senate.geojson` | State senate districts only |
| `county_precinct` | `boundaries/county_precinct.geojson` | County precincts only |
| *(other types)* | `boundaries/{type}.geojson` | One file per boundary type |

### Redirect Lookup Rules

The API uses the manifest to determine redirect targets for the `/api/v1/boundaries/geojson` endpoint:

1. **No filters** → Redirect to `datasets["all-boundaries"].public_url`
2. **`?boundary_type=X` only** (no county/source filters) → Redirect to `datasets[X].public_url` if the key exists
3. **`?boundary_type=X` not in manifest** → Fall back to database
4. **Any `county` or `source` filter present** (even with `boundary_type`) → Always fall back to database. Static files contain complete datasets and cannot serve county/source-scoped subsets.
5. **Manifest not loaded or empty** → Fall back to database

## Object Storage Layout

```
bucket-root/
├── manifest.json
└── boundaries/
    ├── all-boundaries.geojson
    ├── congressional.geojson
    ├── state_senate.geojson
    ├── state_house.geojson
    ├── judicial.geojson
    ├── county.geojson
    ├── county_commission.geojson
    ├── county_precinct.geojson
    ├── municipal_precinct.geojson
    └── ... (one per boundary type with data)
```

All keys are prefixed by the configurable `R2_PREFIX` setting (default: empty, files at bucket root).

## New Entities

### CountyMetadata (migration 011)

Census TIGER/Line attributes for county boundaries. Standalone table keyed by FIPS GEOID — no FK to `boundaries`. Linked via `boundaries.boundary_identifier = county_metadata.geoid` for county boundaries. Populated automatically during `import all-boundaries`.

| Field | Type | Nullable | Notes |
| ----- | ---- | -------- | ----- |
| `id` | UUID | no | Primary key |
| `geoid` | String(5) | no | Unique. FIPS state+county code (e.g. "13121"). Primary Census linkage key. |
| `fips_state` | String(2) | no | State FIPS (e.g. "13" for Georgia) |
| `fips_county` | String(3) | no | County FIPS (e.g. "121") |
| `gnis_code` | String(8) | yes | GNIS identifier |
| `geoid_fq` | String(20) | yes | Fully qualified GEOID (e.g. "0500000US13121") |
| `name` | String(100) | no | County name (e.g. "Fulton") |
| `name_lsad` | String(200) | no | Full legal name (e.g. "Fulton County") |
| `lsad_code` | String(2) | yes | Legal/Statistical Area Description code |
| `class_fp` | String(2) | yes | FIPS class code (e.g. "H1" = active government) |
| `mtfcc` | String(5) | yes | MAF/TIGER Feature Class Code |
| `csa_code` | String(3) | yes | Combined Statistical Area code |
| `cbsa_code` | String(5) | yes | Core-Based Statistical Area code (metro area) |
| `metdiv_code` | String(5) | yes | Metropolitan Division code |
| `functional_status` | String(1) | yes | "A" = active |
| `land_area_m2` | BigInteger | yes | Land area in square meters |
| `water_area_m2` | BigInteger | yes | Water area in square meters |
| `internal_point_lat` | String(15) | yes | Census internal point latitude |
| `internal_point_lon` | String(15) | yes | Census internal point longitude |
| `created_at` | DateTime(tz) | no | Auto-set via `server_default=func.now()` |

**Indexes**: Unique on `geoid`, indexed on `name` and `fips_state`.

**API exposure**: Included as `county_metadata` field in the `GET /api/v1/boundaries/{id}` response when `boundary_type == "county"`. Response also includes computed `land_area_km2` and `water_area_km2` fields.

**Future enrichment**: The `geoid` column is the standard join key for Census ACS demographic/population data products.

## Existing Entities (No Changes)

### Boundary (existing, unchanged)

The `boundaries` table is read-only in this feature. The publish command queries boundaries but does not modify them.

| Field | Type | Notes |
| ----- | ---- | ----- |
| `id` | UUID | Primary key |
| `name` | String(200) | Boundary name |
| `boundary_type` | String(50) | Type (congressional, state_senate, etc.) |
| `boundary_identifier` | String(50) | Unique ID within type |
| `source` | String(20) | "state" or "county" |
| `county` | String(100) | Nullable, county name |
| `geometry` | MultiPolygon(4326) | PostGIS geometry |
| `effective_date` | Date | Nullable |
| `properties` | JSONB | Additional shapefile attributes |
| `created_at` | DateTime | Auto-set |
| `updated_at` | DateTime | Auto-set |

## Configuration Model

New settings added to `Settings` (Pydantic Settings):

| Setting | Env Var | Type | Default | Description |
| ------- | ------- | ---- | ------- | ----------- |
| `r2_enabled` | `R2_ENABLED` | bool | `False` | Enable R2/S3 publishing and redirect |
| `r2_account_id` | `R2_ACCOUNT_ID` | str or None | `None` | Cloudflare R2 account ID |
| `r2_access_key_id` | `R2_ACCESS_KEY_ID` | str or None | `None` | R2 API token access key |
| `r2_secret_access_key` | `R2_SECRET_ACCESS_KEY` | str or None | `None` | R2 API token secret key |
| `r2_bucket` | `R2_BUCKET` | str or None | `None` | R2 bucket name |
| `r2_public_url` | `R2_PUBLIC_URL` | str or None | `None` | Public URL prefix (custom domain or r2.dev URL) |
| `r2_prefix` | `R2_PREFIX` | str | `""` | Key prefix within the bucket |
| `r2_manifest_ttl` | `R2_MANIFEST_TTL` | int | `300` | Manifest cache TTL in seconds |
