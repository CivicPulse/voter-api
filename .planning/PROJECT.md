# Better Imports

## What This Is

A three-stage data import pipeline for Georgia Secretary of State election data: AI-assisted skills produce human-reviewable markdown files from raw SOS data (CSVs, PDFs), a deterministic converter transforms markdown to validated JSONL, and an idempotent import pipeline loads JSONL into the voter-api database. Proven end-to-end with three Georgia 2026 elections (May 19 general primary, March 17 special, March 10 special). The markdown layer is the human-auditable, git-tracked source of truth.

## Core Value

Election and candidate data flows reliably from raw SOS sources into the database through a pipeline where every intermediate step is human-reviewable, version-controlled, and reproducible.

## Requirements

### Validated

- ✓ Voter CSV import (bulk UPSERT, Bibb + Houston counties) — existing
- ✓ Voter history import (yearly ZIP files, statewide) — existing
- ✓ Boundary/shapefile import (8 types, 3,153 boundaries) — existing
- ✓ Election auto-refresh from SOS JSON feeds — existing
- ✓ Election resolution pipeline (voter history ↔ elections, 3-tier) — existing
- ✓ Import job tracking (import_jobs table, status lifecycle) — existing
- ✓ In-process background task runner (asyncio, semaphore-limited) — existing
- ✓ JWT auth + RBAC (admin/analyst/viewer) — existing
- ✓ Candidate table + basic CRUD API — existing
- ✓ Enhanced markdown format with district linkage (boundary_type + district_identifier) — v1.0
- ✓ Enhanced markdown format with election metadata (early voting, registration deadlines, absentee deadlines) — v1.0
- ✓ Enhanced markdown format with candidate details (party, photo URL, bio, contact info, external IDs) — v1.0
- ✓ JSONL schema definitions for elections and candidates — v1.0
- ✓ Deterministic markdown → JSONL converter (fields mirror DB models 1:1) — v1.0
- ✓ JSONL → DB import pipeline for elections (CLI) — v1.0
- ✓ JSONL → DB import pipeline for candidates (CLI) — v1.0
- ✓ Claude Code skills to process raw SOS data (CSVs, PDFs) into structured markdown files — v1.0
- ✓ Full pipeline demo: May 19 SOS CSV → skill → markdown → review → JSONL → import → API query — v1.0

### Active

- [ ] Cloudflare R2 signed URL upload endpoint (handle large files without passing through API)
- [ ] Background job processing via procrastinate or equivalent (PostgreSQL-native, async-compatible)
- [ ] API import endpoints (POST /api/v1/imports/elections, POST /api/v1/imports/candidates)
- [ ] JSONL schema and import pipeline for voter registration data
- [ ] JSONL schema and import pipeline for voter history data
- [ ] Historical election backfill (2024-2025)

### Out of Scope

- Boundary JSONL import — existing shapefile import still works
- Real-time SOS feed integration — existing auto-refresh covers this
- Frontend/UI for reviewing markdown files — git diffs serve this purpose
- Multi-state support — Georgia only for now
- Direct SOS → DB import (skip markdown) — defeats the human-review purpose

## Context

Shipped v1.0 with 94,760 LOC Python across 1,294 files. Tech stack: FastAPI, SQLAlchemy 2.x async, PostgreSQL/PostGIS, mistune (AST parser), Pydantic v2, Typer CLI. Test suite: 2,323 passing (213 new unit + 7 integration + 166 E2E).

Three elections imported into the database: May 19 general primary (25 elections), March 17 special (7 elections), March 10 special (2 elections). 49 candidates with candidacy records across March elections. Pipeline walkthrough documented at `docs/pipeline-walkthrough.md`.

Four Claude Code skills operational: `/election:process` (CSV→MD), `/election:normalize` (deterministic cleanup), `/election:calendar` (PDF→dates), `/election:enrich` (web research→bios). 159 county reference files provide Body/Seat resolution for all Georgia counties.

Known remaining items from v1.0: R2 upload and procrastinate job queue were descoped to v2 (not needed for CLI-only pipeline). `election_event_id` FK is NULL after import — resolved by `voter-api import resolve-elections` step.

## Constraints

- **Storage**: Cloudflare R2 for file uploads — existing `data.hatchtech.dev` bucket already in use for data files
- **Job queue**: Must be PostgreSQL-native (no Redis dependency) and async-compatible with the existing FastAPI stack
- **Markdown format**: Must be parseable deterministically — no AI needed for MD → JSONL conversion
- **JSONL schema**: Fields mirror DB models 1:1 so import is a straightforward load, not a mapping exercise
- **Backwards compatibility**: Existing import CLI commands (`voter-api import voters`, `voter-api import voter-history`) continue to work
- **Git-trackable**: Markdown files must be reasonable size for git (per-county files are fine, not one giant file)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Three-stage pipeline (SOS→MD→JSONL→DB) | Human review gate between AI-processed data and database; git-tracked intermediate artifacts | ✓ Good — human checkpoint caught data quality issues in March elections |
| Claude Code skills for Stage 1 | User already works in Claude Code; skills integrate naturally into their workflow | ✓ Good — 4 skills operational, processed 3 elections successfully |
| R2 signed URLs for upload | Large files (voter reg, history) shouldn't pass through API server | — Deferred to v2 (not needed for CLI-only pipeline) |
| Procrastinate for job queue | PostgreSQL-native, async-compatible, no Redis dependency | — Deferred to v2 (not needed for CLI-only pipeline) |
| JSONL mirrors DB models | Simplest import path; no mapping layer needed; JSONL files serve as portable backups | ✓ Good — zero mapping code in import services |
| Elections + Candidates first | May 19 election is upcoming; smallest data type to prove the pipeline | ✓ Good — pipeline proven with 3 elections before May 19 deadline |
| mistune AST parsing for converter | Deterministic token-based parsing, no HTML rendering needed | ✓ Good — handles all markdown variations without regex fragility |
| Candidacy junction table | Many-to-many candidate-election relationship supports candidates running in multiple contests | ✓ Good — cleaner data model, enables proper relational queries |
| Body/Seat reference system | County reference files define governing body structures for district linkage resolution | ✓ Good — 159 county files cover all GA counties |
| Placeholder UUID for election_event_id | Converter can't know election_event_id at conversion time; resolved during import | ⚠️ Revisit — NULL FK after import requires separate resolve step |

---
*Last updated: 2026-03-15 after v1.0 milestone*
