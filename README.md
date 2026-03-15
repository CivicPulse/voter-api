# voter-api

A FastAPI-based REST API and CLI for managing Georgia Secretary of State voter data with geospatial capabilities. Ingests voter files, geocodes addresses, imports district/precinct boundary shapefiles, performs point-in-polygon analysis, and supports data import pipelines for candidates, absentee ballots, and election calendars.

## Features

- **Voter search** — Query voter records by name, address, voter ID, with pagination and filtering
- **Geocoding** — Pluggable geocoder with provider abstraction and caching
- **Boundary analysis** — Import shapefiles/GeoJSON, point-in-polygon queries, registration-location mismatch detection
- **Election tracking** — Create elections, import results from GA SoS feeds, auto-refresh
- **Candidate import** — Two-stage pipeline: preprocess GA SoS CSV → JSONL, then import to DB (with optional AI-assisted district parsing)
- **Absentee ballot import** — Import GA SoS absentee ballot application CSVs with query and stats endpoints
- **Election calendar import** — Multi-format preprocessor (XLSX, PDF, HTML) with merge support
- **Elected officials** — Multi-source official records with admin approval workflow
- **Voter history** — Import and query voter participation records
- **JWT auth** — Role-based access control (admin, analyst, viewer)
- **Export** — CSV, JSON, GeoJSON bulk export

## Local Development

### Quick Start

```bash
docker compose up --build
```

No `.env` file or manual configuration required. The API will be available at `http://localhost:8000` and the interactive docs at `http://localhost:8000/docs`.

### What Happens on Startup

1. **PostGIS** starts and waits for healthy (`pg_isready`)
2. **Alembic migrations** run automatically (with retries for startup races)
3. **Dev seed data** is inserted via `voter-api db seed-dev` (idempotent — safe to re-run)
4. **Uvicorn** starts with `--reload` — edit files under `src/` on the host and changes are picked up automatically

### Seed Data Summary

| Data | Count | Details |
|---|---|---|
| Users | 3 | admin, analyst, viewer |
| Elections | 2 | 2024 General + 2024 Primary (finalized) |
| Boundaries | 3 | Congressional District 5, State Senate District 36, Fulton County (real-ish ATL-area polygons) |
| Voters | 5 | Fulton County, geocoded with PostGIS points (4 active, 1 inactive) |
| Voter History | 3 | Participation records linked to elections |
| Elected Officials | 2 | Linked to congressional + state senate boundaries |
| Candidates | 2 | One per election |

### Common Workflows

**Fresh reset** (destroy database volume and rebuild):

```bash
docker compose down -v
docker compose up --build
```

**Re-seed without reset** (data is upserted, not duplicated):

```bash
docker compose exec api voter-api db seed-dev
```

**Run tests outside Docker** (requires PostGIS running):

```bash
docker compose up -d db
uv run pytest
```

### Port Conflicts

If port 8000 is already in use, override it in `docker-compose.yml` or via the CLI:

```bash
docker compose up --build -e API_PORT=8001  # or edit ports: in docker-compose.yml
```

If port 5432 conflicts with a local PostgreSQL, stop the local instance or change the host port mapping in `docker-compose.yml`.

## Data Import

All import commands use the `voter-api` CLI. The API also exposes upload endpoints for admin users.

### Candidate Import

Two-stage workflow for importing qualified candidates from the Georgia Secretary of State.

**Stage 1: Preprocess** — Parse the raw GA SoS Qualified Candidates CSV into a reviewable JSONL template. District strings (e.g., "State House District 45") are parsed via regex with optional AI fallback.

```bash
# Basic preprocessing
uv run voter-api import preprocess-candidates raw_candidates.csv \
  --output candidates.jsonl \
  --election-date 2026-05-19 \
  --election-type primary

# With AI-assisted district parsing (requires ANTHROPIC_API_KEY env var)
ANTHROPIC_API_KEY=sk-... uv run voter-api import preprocess-candidates raw_candidates.csv \
  --output candidates.jsonl \
  --election-date 2026-05-19 \
  --election-type general
```

**Stage 2: Import** — Load the preprocessed JSONL into the database.

```bash
uv run voter-api import candidates candidates.jsonl --batch-size 500
```

**API endpoint:**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/imports/candidates` | admin | Upload JSONL template (multipart, 50 MB limit) |

### Absentee Ballot Application Import

Single-stage import of GA SoS 38-column absentee ballot application CSVs.

```bash
uv run voter-api import absentee absentee_applications.csv --batch-size 400
```

**API endpoints:**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/imports/absentee` | admin | Upload absentee CSV (multipart, 100 MB limit) |
| `GET` | `/api/v1/absentee` | admin/analyst | List with filters (county, status, party) |
| `GET` | `/api/v1/absentee/stats` | admin/analyst | Aggregate statistics |
| `GET` | `/api/v1/absentee/by-voter/{reg_num}` | admin/analyst | Applications for a specific voter |
| `GET` | `/api/v1/absentee/{id}` | admin/analyst | Single application detail |

### Election Calendar Import

Two-stage workflow supporting multiple source formats (XLSX, PDF, HTML) with optional merge from multiple files.

**Stage 1: Preprocess** — Convert source file(s) into a JSONL template.

```bash
# Single source
uv run voter-api election preprocess-calendar calendar.xlsx --output calendar.jsonl

# Merge multiple sources (e.g., XLSX primary + PDF supplement)
uv run voter-api election preprocess-calendar calendar.xlsx \
  --output calendar.jsonl \
  --merge supplement.pdf \
  --merge addendum.html
```

**Stage 2: Import** — Load calendar dates into the database, matching entries to existing elections.

```bash
uv run voter-api election import-calendar calendar.jsonl
```

No API endpoint — CLI only.

## Architecture

Library-first design: all features are standalone, testable libraries under `src/voter_api/lib/` before integration into services and routes.

```
src/voter_api/
├── lib/               # Standalone libraries (core logic)
│   ├── candidate_importer/    # CSV parsing, district resolution, JSONL generation
│   ├── absentee_parser/       # GA SoS absentee CSV field mapping
│   ├── election_calendar/     # XLSX/PDF/HTML preprocessors + JSONL parser
│   ├── geocoder/              # Pluggable geocoding with caching
│   ├── importer/              # Voter CSV import engine
│   ├── boundary_loader/       # Shapefile + GeoJSON ingestion
│   └── analyzer/              # Point-in-polygon analysis
├── services/          # Business logic orchestration
├── api/v1/            # FastAPI route handlers
├── cli/               # Typer CLI commands
├── models/            # SQLAlchemy + GeoAlchemy2 ORM
├── schemas/           # Pydantic v2 request/response models
└── core/              # Config, database, auth, logging
```

## Packages

- fastAPI
- SQLAlchemy + GeoAlchemy2
- PostGIS
- Alembic
- Pydantic v2
- Typer
- Loguru
- Pandas
- Jinja2
- openpyxl (XLSX calendar parsing)
- pdfplumber (PDF calendar parsing)
- beautifulsoup4 + lxml (HTML calendar parsing)

## Tech Notes

- 12 factor principles for configuration management
- Alembic for database migrations
- Loguru for logging
- Pydantic models for data validation and serialization
- Database updates use transactions to ensure data integrity
- Async programming for handling requests
- Conventional Commits standards — see [docs/convential_commits.md](docs/convential_commits.md)
- OpenAPI standards for API documentation
- pytest for testing
- Docker for containerization
- GitHub Actions for CI/CD
- `uv` for all Python commands and environment management
