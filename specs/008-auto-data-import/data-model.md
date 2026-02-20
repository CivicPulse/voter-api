# Data Model: Automated Data Download & Import

**Feature**: 008-auto-data-import
**Date**: 2026-02-20

## Overview

This feature introduces no new database tables. It adds in-memory data structures for the remote manifest and download tracking, plus one new configuration setting.

## Entities

### SeedManifest

Represents the remote `manifest.json` fetched from the Data Root URL.

| Field | Type | Description |
| ----- | ---- | ----------- |
| version | string | Manifest schema version (currently `"1"`) |
| updated_at | datetime | When the manifest was last updated |
| files | list[DataFileEntry] | List of all available data files |

### DataFileEntry

Represents a single file listed in the remote manifest.

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| filename | string | Yes | File name (e.g., `congress-2023-shape.zip`) |
| sha512 | string | Yes | Expected SHA512 hex digest |
| category | string (enum) | Yes | One of: `boundary`, `voter`, `county_district`, `reference` |
| size_bytes | integer | Yes | File size in bytes |

**Category values**:

- `boundary` — Shapefile zip processed by `import all-boundaries`
- `voter` — Voter CSV processed by `import voters`
- `county_district` — County-district CSV processed by `import county-districts`
- `reference` — Downloaded but not imported (e.g., PDFs, documentation)

### DownloadResult

Tracks the outcome of downloading a single file.

| Field | Type | Description |
| ----- | ---- | ----------- |
| entry | DataFileEntry | The manifest entry this result is for |
| downloaded | boolean | Whether the file was freshly downloaded (False = skipped, already cached) |
| verified | boolean | Whether checksum verification passed |
| local_path | Path | Local filesystem path where the file is stored |
| error | string or null | Error message if download/verification failed |

### SeedResult

Tracks the overall outcome of a seed operation.

| Field | Type | Description |
| ----- | ---- | ----------- |
| downloads | list[DownloadResult] | Results for each file download |
| import_results | dict[string, object] | Keyed by category; import outcome per phase |
| total_downloaded_bytes | integer | Total bytes freshly downloaded |
| total_skipped | integer | Number of files skipped (already cached) |
| success | boolean | True if all downloads and imports succeeded |

## Configuration

### New Setting: `data_root_url`

| Property | Value |
| -------- | ----- |
| Environment variable | `DATA_ROOT_URL` |
| Type | `str` |
| Default | `https://data.hatchtech.dev/` |
| Required | No |
| Validation | Must be a valid HTTPS URL |

Added to the existing `Settings` class in `src/voter_api/core/config.py`.

## File Storage Layout

Downloaded files are stored in the existing `data/` directory structure:

```text
data/
├── manifest.json                          # Cached copy of remote manifest (optional)
├── congress-2023-shape.zip                # Boundary files at root
├── senate-2023-shape-file.zip
├── house-2023-shape.zip
├── psc-2022.zip
├── tl_2025_us_county.zip
├── gaprec_2024-website-shapefile.zip
├── bibbcc-2022-shape-file.zip
├── bibbsb-2022-shape-file.zip
├── counties-by-districts-2023.csv         # County-district mapping
├── counties-by-leg-and-cong-districts--2023.pdf  # Reference file
└── voter/
    ├── Bibb-20260203.csv                  # Voter files in voter/ subdirectory
    └── HOUSTON-2026.02.02.csv
```

**Download path rules**:

- `category == "voter"` → `data/voter/{filename}`
- All other categories → `data/{filename}`

This matches the current data directory layout.

## Relationships to Existing Entities

No foreign keys or database joins. The seed command interacts with existing entities indirectly through the import commands:

- **Voter** table — populated by `import voters`
- **Boundary** table — populated by `import all-boundaries`
- **CountyDistrict** table — populated by `import county-districts`
- **ImportJob** table — created by `import voters` (tracks import history)
- **CountyMetadata** table — populated by `import all-boundaries` (from county shapefile)
