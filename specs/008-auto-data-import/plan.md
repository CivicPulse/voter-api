# Implementation Plan: Automated Data Download & Import

**Branch**: `008-auto-data-import` | **Date**: 2026-02-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/008-auto-data-import/spec.md`

## Summary

Add a new `voter-api seed` CLI command that downloads a remote JSON manifest from the Data Root URL, fetches all listed data files (with checksum verification and skip-if-cached), then imports them in dependency order using the existing import pipelines: county-districts → boundaries → voters. Supports category filtering (`--category`), download-only mode (`--download-only`), and fail-fast (`--fail-fast`). The Data Root URL is configured via `DATA_ROOT_URL` environment variable.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: httpx (async HTTP downloads), typer (CLI), loguru (logging), tqdm (progress bars) — all already in pyproject.toml
**Storage**: PostgreSQL + PostGIS (via existing import commands); local filesystem for downloaded data files
**Testing**: pytest with pytest-asyncio, pytest-cov (90% threshold)
**Target Platform**: Linux server (piku deployment)
**Project Type**: Single project (existing structure)
**Performance Goals**: Download phase < 10 min on typical broadband; skip-if-cached download phase < 30 sec
**Constraints**: No new Python dependencies needed. Must not modify existing import commands.
**Scale/Scope**: ~12 files totaling ~180 MB. Manifest is small JSON (~2 KB).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
| --------- | ------ | ----- |
| I. Library-First Architecture | PASS | New `data_loader` library in `lib/` with clear public API |
| II. Code Quality (NON-NEGOTIABLE) | PASS | Type hints, Google docstrings, ruff compliance on all new code |
| III. Testing Discipline (NON-NEGOTIABLE) | PASS | Unit tests for downloader, manifest parser, checksum logic; integration tests for CLI |
| IV. Twelve-Factor Configuration | PASS | `DATA_ROOT_URL` in `.env`; Pydantic Settings validation |
| V. Developer Experience | PASS | Single `voter-api seed` command; `uv run` for all operations |
| VI. API Documentation | N/A | CLI-only feature, no new API endpoints |
| VII. Security by Design | PASS | HTTPS-only downloads; checksum verification; no credential storage needed |
| VIII. CI/CD & Version Control | PASS | Conventional Commits; tests run in CI |

No violations. Gate passes.

## Project Structure

### Documentation (this feature)

```text
specs/008-auto-data-import/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (manifest schema)
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (manifest JSON schema)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/voter_api/
├── core/
│   └── config.py                  # ADD: data_root_url setting
├── lib/
│   └── data_loader/               # NEW: standalone download + manifest library
│       ├── __init__.py            # Public API exports
│       ├── manifest.py            # Fetch & parse remote manifest.json
│       ├── downloader.py          # File download with progress, checksum, skip-if-cached
│       └── types.py               # DataFileEntry, SeedManifest, DownloadResult dataclasses
└── cli/
    └── seed_cmd.py                # NEW: `voter-api seed` command

tests/
├── unit/
│   └── lib/
│       └── test_data_loader/      # NEW: unit tests
│           ├── test_manifest.py   # Manifest parsing tests
│           ├── test_downloader.py # Download + checksum tests
│           └── test_types.py      # Type validation tests
└── integration/
    └── cli/
        └── test_seed_cmd.py       # NEW: integration tests for seed CLI
```

**Structure Decision**: Single project layout following existing convention. New `data_loader` library under `lib/` matches the library-first architecture. New CLI command registered in `cli/app.py` as a top-level command (`seed`), separate from the existing `import` group since it orchestrates across import types.

## Key Design Decisions

### 1. CLI Command: `voter-api seed` (not `import seed`)

The command orchestrates downloads + multiple import types, so it belongs as a top-level command rather than under the `import` group. The name "seed" communicates its primary use case (bootstrapping environments).

### 2. Remote Manifest as Download Control; Existing Manifests for Import Logic

The remote `manifest.json` controls **what gets downloaded**. The existing code-level `BOUNDARY_MANIFEST` controls **how boundaries get imported**. This separation means:
- Adding a new file to R2 requires: update remote manifest (download) + update code BOUNDARY_MANIFEST (import)
- This wraps existing import commands without modifying them (per spec)

### 3. Reuse Patterns from Existing Libraries

- **httpx**: Already used for election_tracker and deploy_check — follow the same async client patterns
- **tqdm**: Already a dependency for progress bars
- **checksum verification**: Implement in `data_loader` using the same `hashlib.sha512` streaming pattern as `boundary_loader/checksum.py`, but reading the expected hash from the manifest (not companion `.sha512.txt` files)
- **Pydantic Settings**: Add `data_root_url` to existing `Settings` class

### 4. Download Strategy

Files are downloaded sequentially (not in parallel) for simplicity and to avoid overwhelming the R2 endpoint. Downloads use streaming with progress reporting via tqdm. Files are written to a temporary path first, then renamed on success (atomic write pattern for FR-011).

### 5. Import Orchestration

After all downloads complete, imports run in fixed order:
1. `county-districts` — each matching CSV via existing `_import_county_districts()`
2. `boundaries` — via existing `_import_all_boundaries(data_dir)`
3. `voters` — each matching CSV via existing `_import_voters(file_path, batch_size)`

The `seed` command calls the existing async import functions directly (not via subprocess), reusing the same database session management pattern.

## Files to Create/Modify

| File | Action | Description |
| ---- | ------ | ----------- |
| `src/voter_api/core/config.py` | MODIFY | Add `data_root_url` setting |
| `.env.example` | MODIFY | Add `DATA_ROOT_URL` example |
| `src/voter_api/lib/data_loader/__init__.py` | CREATE | Public API exports |
| `src/voter_api/lib/data_loader/types.py` | CREATE | DataFileEntry, SeedManifest, DownloadResult dataclasses |
| `src/voter_api/lib/data_loader/manifest.py` | CREATE | Fetch + parse remote manifest.json |
| `src/voter_api/lib/data_loader/downloader.py` | CREATE | HTTP download with streaming, progress, checksum, skip-if-cached |
| `src/voter_api/cli/seed_cmd.py` | CREATE | `voter-api seed` CLI command |
| `src/voter_api/cli/app.py` | MODIFY | Register `seed` command |
| `tests/unit/lib/test_data_loader/test_manifest.py` | CREATE | Unit tests |
| `tests/unit/lib/test_data_loader/test_downloader.py` | CREATE | Unit tests |
| `tests/integration/cli/test_seed_cmd.py` | CREATE | Integration tests |

## Complexity Tracking

No constitution violations to justify.
