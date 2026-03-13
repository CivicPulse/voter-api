# Better Imports

## What This Is

A three-stage data import pipeline for Georgia Secretary of State election data: AI-assisted normalization into human-reviewable markdown files, deterministic conversion to JSONL, and reliable import into the voter-api database. Designed for elections and candidates first, extensible to voter registration, voter history, and boundary data. The markdown layer is the human-auditable, git-tracked source of truth.

## Core Value

Election and candidate data flows reliably from raw SOS sources into the database through a pipeline where every intermediate step is human-reviewable, version-controlled, and reproducible.

## Requirements

### Validated

<!-- Existing capabilities inferred from codebase -->

- ✓ Voter CSV import (bulk UPSERT, Bibb + Houston counties) — existing
- ✓ Voter history import (yearly ZIP files, statewide) — existing
- ✓ Boundary/shapefile import (8 types, 3,153 boundaries) — existing
- ✓ Election auto-refresh from SOS JSON feeds — existing
- ✓ Election resolution pipeline (voter history ↔ elections, 3-tier) — existing
- ✓ Import job tracking (import_jobs table, status lifecycle) — existing
- ✓ In-process background task runner (asyncio, semaphore-limited) — existing
- ✓ JWT auth + RBAC (admin/analyst/viewer) — existing
- ✓ Candidate table + basic CRUD API — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] Claude Code skills to process raw SOS data (CSVs, PDFs) into structured markdown files
- [ ] Enhanced markdown format with district linkage (boundary_type + district_identifier)
- [ ] Enhanced markdown format with election metadata (early voting, registration deadlines, absentee deadlines)
- [ ] Enhanced markdown format with candidate details (party, photo URL, bio, contact info, external IDs)
- [ ] Deterministic markdown → JSONL converter (fields mirror DB models 1:1)
- [ ] JSONL schema definitions for elections and candidates
- [ ] Cloudflare R2 signed URL upload endpoint (handle large files without passing through API)
- [ ] Background job processing via procrastinate or equivalent (PostgreSQL-native, async-compatible)
- [ ] JSONL → DB import pipeline for elections (CLI + API)
- [ ] JSONL → DB import pipeline for candidates (CLI + API)
- [ ] Full pipeline demo: May 19 SOS CSV → skill → markdown → review → JSONL → import → API query

### Out of Scope

- Voter registration JSONL import — future milestone after election/candidate pipeline is proven
- Voter history JSONL import — future milestone (existing ZIP import still works)
- Boundary JSONL import — future milestone (existing shapefile import still works)
- Historical election backfill (2024-2025) — separate effort, different data source
- Real-time SOS feed integration — existing auto-refresh covers this
- Frontend/UI for reviewing markdown files — git diffs serve this purpose
- Multi-state support — Georgia only for now

## Context

The current import pipeline has significant data quality issues documented in `data/DATA_QUALITY_REPORT.md`: 96.7% of voter history records unresolved, 100% of elections missing boundary_id, election type mapping gaps. These stem from the raw SOS data not being well-suited for direct import — it needs transformation, enrichment, and human review before loading.

The `data/elections/` directory already contains ~200 structured markdown files for the March 17 special and May 19 general primary elections, including per-county candidate files for all 159 Georgia counties. Format specs exist in `data/elections/formats/`. These represent an early iteration of Stage 1 output, but the format needs enhancement (missing district linkage, election metadata, candidate details).

The existing `BackgroundTaskRunner` protocol in `core/background.py` uses `asyncio.create_task` with a semaphore limit of 2. This is insufficient for large file processing — a PostgreSQL-backed job queue (procrastinate) would provide persistence, retries, and concurrency control without blocking the API.

File sizes range from small (election JSONL, likely <5MB) to very large (statewide voter registration, potentially hundreds of MB; voter history, 50MB+ per year). The R2 signed URL approach avoids pushing large files through the API server and supports the use case of backup restoration and open-source operator imports.

## Constraints

- **Storage**: Cloudflare R2 for file uploads — existing `data.hatchtech.dev` bucket already in use for data files
- **Job queue**: Must be PostgreSQL-native (no Redis dependency) and async-compatible with the existing FastAPI stack
- **Markdown format**: Must be parseable deterministically — no AI needed for MD → JSONL conversion
- **JSONL schema**: Fields mirror DB models 1:1 so import is a straightforward load, not a mapping exercise
- **Backwards compatibility**: Existing import CLI commands (`voter-api import voters`, `voter-api import voter-history`) continue to work
- **Git-trackable**: Markdown files must be reasonable size for git (per-county files are fine, not one giant file)

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Three-stage pipeline (SOS→MD→JSONL→DB) | Human review gate between AI-processed data and database; git-tracked intermediate artifacts | — Pending |
| Claude Code skills for Stage 1 | User already works in Claude Code; skills integrate naturally into their workflow | — Pending |
| R2 signed URLs for upload | Large files (voter reg, history) shouldn't pass through API server; supports backup restore and open-source operator imports | — Pending |
| Procrastinate for job queue | PostgreSQL-native, async-compatible, no Redis dependency; fits existing stack | — Pending |
| JSONL mirrors DB models | Simplest import path; no mapping layer needed; JSONL files serve as portable backups | — Pending |
| Elections + Candidates first | May 19 election is upcoming; smallest data type to prove the pipeline; highest immediate value | — Pending |

---
*Last updated: 2026-03-13 after initialization*
