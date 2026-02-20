# Quickstart: Automated Data Download & Import

**Feature**: 008-auto-data-import

## Prerequisites

- PostgreSQL + PostGIS running with database created
- `DATABASE_URL` and `JWT_SECRET_KEY` configured in `.env`
- `uv sync` completed

## Configuration

Add to `.env` (optional — defaults to `https://data.hatchtech.dev/`):

```bash
DATA_ROOT_URL=https://data.hatchtech.dev/
```

## Usage

### Bootstrap a fresh environment (download + import everything)

```bash
uv run voter-api seed
```

This will:

1. Fetch `manifest.json` from the Data Root URL
2. Download all listed files to `data/` (skipping files that already exist with matching checksums)
3. Import in order: county-districts → boundaries → voters

### Download only (no database import)

```bash
uv run voter-api seed --download-only
```

### Import only specific categories

```bash
# Boundaries only
uv run voter-api seed --category boundaries

# Voters only
uv run voter-api seed --category voters

# County-district mappings only
uv run voter-api seed --category county-districts
```

### Override the Data Root URL

```bash
uv run voter-api seed --data-root https://custom-data.example.com/
```

### Stop on first error

```bash
uv run voter-api seed --fail-fast
```

## CLI Reference

```text
voter-api seed [OPTIONS]

Options:
  --data-root TEXT       Override the Data Root URL (default: from DATA_ROOT_URL env var)
  --data-dir PATH        Local directory for downloaded files (default: data)
  --category TEXT        Filter by category: boundaries, voters, county-districts (repeatable)
  --download-only        Download files without importing
  --fail-fast            Stop on first download or import error
  --skip-checksum        Skip SHA512 checksum verification
  --help                 Show this help message
```

## Remote Manifest

The Data Root URL must serve a `manifest.json` file listing all available files.
See `contracts/manifest-schema.json` for the schema and `contracts/manifest-example.json` for a complete example.

## Generating the Remote Manifest

The remote `manifest.json` must be created and uploaded to the Data Root server whenever files are added or updated. This is a manual process:

1. Update `data/data.md` with the new file's information
2. Create a `manifest.json` matching the schema in `contracts/manifest-schema.json`
3. Upload both the data file and updated `manifest.json` to the R2 bucket

## Verifying

After running `seed`, verify the data was imported:

```bash
# Check boundary counts
uv run voter-api serve &
curl -s http://localhost:8000/api/v1/boundaries | python -m json.tool | head -20

# Check voter counts
curl -s http://localhost:8000/api/v1/voters?limit=1 | python -m json.tool
```
