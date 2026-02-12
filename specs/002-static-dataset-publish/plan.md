# Implementation Plan: Static Dataset Publishing

**Branch**: `002-static-dataset-publish` | **Date**: 2026-02-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-static-dataset-publish/spec.md`

## Summary

Generate static GeoJSON files from boundary data and upload them to Cloudflare R2 (S3-compatible) object storage via a CLI command. The existing `/api/v1/boundaries/geojson` endpoint is modified to return HTTP 302 redirects to the static files when available, falling back to database-served responses when not. A `manifest.json` file on R2 tracks published datasets and is cached by the API with a 5-minute TTL. A public discovery endpoint (`GET /api/v1/datasets`) exposes the R2 base URL and published dataset list for consumers.

**Technical approach**: boto3 for R2 uploads (sync CLI + `asyncio.to_thread()` for async manifest fetch), library-first architecture with `lib/publisher/`, manifest-based redirect lookup, ordered uploads (data files first, manifest last) for atomicity.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x + GeoAlchemy2, Typer, Pydantic v2, boto3 (new), Loguru
**Storage**: PostgreSQL + PostGIS (read-only for this feature), Cloudflare R2 (new, S3-compatible)
**Testing**: pytest + moto[s3] (new, for S3 mocking)
**Target Platform**: Linux server
**Project Type**: Single project (API + CLI)
**Performance Goals**: Publish full Georgia dataset (all boundary types) in under 5 minutes
**Constraints**: 5-minute manifest cache TTL, atomic uploads via ordered write, R2-specific boto3 config (checksum workaround)
**Scale/Scope**: ~31 boundary types, ~1,500 total boundaries, files typically 1–50 MB each

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Library-First Architecture | PASS | New `lib/publisher/` library with explicit `__init__.py` exports, independently testable |
| II. Code Quality (NON-NEGOTIABLE) | PASS | Type hints, Google-style docstrings, ruff compliance on all new code |
| III. Testing Discipline (NON-NEGOTIABLE) | PASS | Unit tests for library (moto for S3), integration tests for CLI + API redirect, contract tests for endpoint changes. 90% coverage target |
| IV. Twelve-Factor Configuration | PASS | All R2 config via env vars (`R2_ENABLED`, `R2_ACCOUNT_ID`, etc.), validated by Pydantic Settings |
| V. Developer Experience | PASS | CLI via Typer (`voter-api publish datasets`, `voter-api publish status`), works with `uv run` |
| VI. API Documentation | PASS | Modified endpoint + new discovery endpoint + new status endpoint documented via OpenAPI/Pydantic schemas |
| VII. Security by Design | PASS | R2 credentials in env vars only, publish commands require DB access (admin context), status endpoint requires admin auth, discovery endpoint intentionally public per spec |
| VIII. CI/CD & Version Control | PASS | Conventional commits, feature branch, all quality gates |

**Post-Phase 1 re-check**: All principles satisfied. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-static-dataset-publish/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research output
├── data-model.md        # Phase 1 data model
├── quickstart.md        # Phase 1 quickstart guide
├── contracts/
│   └── openapi-changes.yaml  # Phase 1 API contract changes
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/voter_api/
├── core/
│   └── config.py                  # MODIFY: Add R2 settings
├── lib/
│   └── publisher/                 # NEW: Publisher library
│       ├── __init__.py            # Public API exports
│       ├── generator.py           # GeoJSON generation from boundary dicts
│       ├── storage.py             # S3/R2 upload operations
│       ├── manifest.py            # Manifest generation, parsing, caching
│       └── types.py               # Dataclasses (PublishResult, DatasetEntry, etc.)
├── services/
│   └── publish_service.py         # NEW: Orchestrate DB queries + publisher library
├── cli/
│   ├── app.py                     # MODIFY: Register publish subcommand
│   └── publish_cmd.py             # NEW: Typer publish commands
├── api/v1/
│   ├── boundaries.py              # MODIFY: Add redirect logic to geojson endpoint
│   └── datasets.py                # NEW: Public discovery endpoint
└── schemas/
    └── publish.py                 # NEW: Pydantic schemas for publish status + discovery

tests/
├── unit/
│   └── lib/
│       └── test_publisher/        # NEW: Unit tests for publisher library
│           ├── test_generator.py
│           ├── test_storage.py
│           └── test_manifest.py
├── integration/
│   ├── test_publish_cli.py        # NEW: CLI integration tests
│   └── test_publish_redirect.py   # NEW: API redirect integration tests
└── contract/
    └── test_publish_contract.py   # NEW: OpenAPI contract tests
```

**Structure Decision**: Single project structure, following existing patterns. New `lib/publisher/` library is the core, with service, CLI, and API layers wrapping it. All new files are in established directories — no new top-level directories.

### Files Modified vs Created

| Action | File | Purpose |
| ------ | ---- | ------- |
| MODIFY | `src/voter_api/core/config.py` | Add R2 settings to `Settings` class |
| MODIFY | `src/voter_api/cli/app.py` | Register `publish` subcommand |
| MODIFY | `src/voter_api/api/v1/boundaries.py` | Add redirect logic to `get_boundaries_geojson` |
| MODIFY | `.env.example` | Add R2 env var documentation |
| MODIFY | `pyproject.toml` | Add `boto3` dependency, `moto[s3]` dev dependency |
| CREATE | `src/voter_api/lib/publisher/__init__.py` | Public API |
| CREATE | `src/voter_api/lib/publisher/types.py` | Dataclasses |
| CREATE | `src/voter_api/lib/publisher/generator.py` | GeoJSON generation |
| CREATE | `src/voter_api/lib/publisher/storage.py` | S3/R2 operations |
| CREATE | `src/voter_api/lib/publisher/manifest.py` | Manifest logic + caching |
| CREATE | `src/voter_api/services/publish_service.py` | Service orchestration |
| CREATE | `src/voter_api/cli/publish_cmd.py` | CLI commands |
| CREATE | `src/voter_api/schemas/publish.py` | Response schemas (status + discovery) |
| CREATE | `src/voter_api/api/v1/datasets.py` | Public discovery endpoint (FR-022) |
| CREATE | `tests/unit/lib/test_publisher/` | Unit tests |
| CREATE | `tests/integration/test_publish_cli.py` | CLI integration tests |
| CREATE | `tests/integration/test_publish_redirect.py` | API redirect tests |
| CREATE | `tests/contract/test_publish_contract.py` | Contract tests |

## Component Design

### Publisher Library (`lib/publisher/`)

The library is stateless and independently testable. It operates on plain dicts and boto3 clients, with no database or FastAPI dependencies.

#### `types.py` — Data Types

```python
@dataclass
class DatasetEntry:
    """Metadata for a single published dataset."""
    name: str
    key: str
    public_url: str
    content_type: str
    record_count: int
    file_size_bytes: int
    boundary_type: str | None
    filters: dict[str, str]
    published_at: datetime

@dataclass
class PublishResult:
    """Result of a publish operation."""
    datasets: list[DatasetEntry]
    manifest_key: str
    total_records: int
    total_size_bytes: int
    duration_seconds: float

@dataclass
class ManifestData:
    """Parsed manifest.json contents."""
    version: str
    published_at: datetime
    publisher_version: str
    datasets: dict[str, DatasetEntry]
```

#### `generator.py` — GeoJSON Generation

- `generate_boundary_geojson(boundaries: list[dict], output_path: Path) -> int`
  - Takes boundary dicts (pre-converted from ORM objects by the service layer)
  - Writes a GeoJSON FeatureCollection to a local temp file
  - Returns record count
  - Uses streaming writes (same pattern as existing `geojson_writer.py`)
  - Feature structure matches the existing endpoint output (FR-009)

#### `storage.py` — S3/R2 Operations

- `create_r2_client(account_id, access_key_id, secret_access_key) -> boto3.client`
  - Creates a boto3 S3 client configured for R2 (endpoint URL, checksum workaround)
- `upload_file(client, bucket, key, file_path, content_type) -> int`
  - Uploads a file to R2, returns file size in bytes
  - Uses `TransferConfig` with 25 MB multipart threshold
- `upload_manifest(client, bucket, key, manifest_data) -> None`
  - Uploads the manifest JSON
- `fetch_manifest(client, bucket, key) -> ManifestData | None`
  - Downloads and parses manifest.json, returns None if not found
- `validate_config(client, bucket) -> None`
  - Verifies bucket exists and credentials are valid, raises on failure

#### `manifest.py` — Manifest Caching

- `ManifestCache` class:
  - `__init__(ttl_seconds: int)`
  - `get() -> ManifestData | None` — returns cached manifest if TTL not expired
  - `set(data: ManifestData) -> None` — updates cache
  - `invalidate() -> None` — clears cache
  - `is_stale() -> bool` — checks if TTL expired
- `get_redirect_url(manifest: ManifestData, boundary_type: str | None, county: str | None, source: str | None) -> str | None`
  - Determines redirect URL from manifest based on query parameters
  - Returns URL if an exact match exists, None if fallback to DB needed
- `build_manifest(datasets: list[DatasetEntry], publisher_version: str) -> dict`
  - Constructs the manifest.json dict from dataset entries

### Service Layer (`services/publish_service.py`)

Orchestrates database queries and publisher library calls:

- `publish_datasets(session, client, bucket, public_url, prefix, boundary_type, county, source) -> PublishResult`
  - Queries boundaries from DB with optional filters
  - Groups by boundary_type
  - Calls generator for each group + combined
  - Calls storage.upload_file for each generated file
  - Builds and uploads manifest
  - Returns PublishResult
- `get_publish_status(client, bucket, prefix) -> ManifestData | None`
  - Fetches manifest from R2 for status display
- `boundary_to_feature_dict(boundary: Boundary) -> dict`
  - Converts Boundary ORM model to the same dict structure as the existing endpoint

### API Redirect Logic (`api/v1/boundaries.py`)

The existing `get_boundaries_geojson` function is modified:

1. Check if R2 is enabled (`settings.r2_enabled`)
2. If enabled, check manifest cache (fetch/refresh if stale via `asyncio.to_thread()`)
3. Call `get_redirect_url(manifest, boundary_type, county, source)`
4. If redirect URL found → return `RedirectResponse(url, status_code=302)`
5. If no redirect URL → fall through to existing database logic (unchanged)

### Discovery Endpoint (`api/v1/datasets.py`)

New public endpoint implementing FR-022:

- `GET /api/v1/datasets` — no authentication required
- Reads `r2_public_url` from settings as `base_url`
- Reads cached manifest for dataset list
- Returns `DatasetDiscoveryResponse` with `base_url` + datasets list
- Returns empty datasets list with `base_url` when no manifest loaded
- Returns 200 with `base_url: null` and empty `datasets` list when R2 not configured

### CLI Commands (`cli/publish_cmd.py`)

- `voter-api publish datasets [--boundary-type] [--county] [--source] [--verbose]`
  - Generates and uploads boundary GeoJSON files to R2
  - --boundary-type: regenerate only this type's file
  - --county/--source: scope which types to regenerate (files always contain complete data for their type)
  - Shows progress (record counts, file sizes, upload status)
- `voter-api publish status`
  - Fetches manifest from R2 and displays published dataset info
