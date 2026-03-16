# CivPulse Voter API

## What This Is

A Python/FastAPI REST API for managing Georgia Secretary of State voter and election data with geospatial capabilities. Features a three-stage election data pipeline (SOS→Markdown→JSONL→DB) with AI-assisted skills, voter registration import, boundary/shapefile import, and geocoding. Proven with three Georgia 2026 elections. Elections are searchable by text, filterable by race category/county/date, with progressive discovery endpoints for frontend integration.

## Core Value

Georgia election and voter data is accurately maintained and queryable — from raw SOS sources through human-reviewable pipelines into a searchable, filterable API that powers civic engagement tools.

## Current Milestone: v1.2 Context-Aware District Mismatch

**Goal:** When filtering election participation by `has_district_mismatch`, only flag voters whose mismatch is on the district type relevant to that specific election.

**Target features:**
- Context-aware mismatch filtering on the participation endpoint (JOIN to analysis_results, scope by election's district_type)

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
- ✓ Capabilities endpoint (`GET /elections/capabilities`) for progressive filter discovery — v1.1
- ✓ Free-text search (`q`) across election name and district fields — v1.1
- ✓ Race category filter (`race_category`) mapping to existing `district_type` — v1.1
- ✓ County filter (`county`) matching `eligible_county` — v1.1
- ✓ Exact date filter (`election_date`) complementing existing date range — v1.1
- ✓ Filter options endpoint (`GET /elections/filter-options`) for dropdown values — v1.1
- ✓ Keep existing `district` filter as partial match (no breaking change) — v1.1

### Active

- [ ] Participation endpoint `has_district_mismatch` filter scoped to election's district_type via analysis_results JOIN

### Backlog

- [ ] Cloudflare R2 signed URL upload endpoint (handle large files without passing through API)
- [ ] Background job processing via procrastinate or equivalent (PostgreSQL-native, async-compatible)
- [ ] API import endpoints (POST /api/v1/imports/elections, POST /api/v1/imports/candidates)
- [ ] JSONL schema and import pipeline for voter registration data
- [ ] JSONL schema and import pipeline for voter history data
- [ ] Historical election backfill (2024-2025)
- [ ] Statewide election inclusion in county filter (geospatial boundary logic)
- [ ] Scoped filter options (context-sensitive dropdown values)

### Out of Scope

- Boundary JSONL import — existing shapefile import still works
- Real-time SOS feed integration — existing auto-refresh covers this
- Frontend/UI for reviewing markdown files — git diffs serve this purpose
- Multi-state support — Georgia only for now
- Direct SOS → DB import (skip markdown) — defeats the human-review purpose

## Context

Shipped v1.1 with ~304,293 LOC Python. Tech stack: FastAPI, SQLAlchemy 2.x async, PostgreSQL/PostGIS, mistune (AST parser), Pydantic v2, Typer CLI. Test suite: 185 E2E tests (up from 166), plus unit and integration tests.

Three elections imported into the database: May 19 general primary (25 elections), March 17 special (7 elections), March 10 special (2 elections). 49 candidates with candidacy records across March elections. Pipeline walkthrough documented at `docs/pipeline-walkthrough.md`.

v1.1 added election search and discovery: capabilities endpoint, filter-options endpoint, free-text search, and race category/county/date filters. All backward-compatible. Zero new dependencies.

Four Claude Code skills operational: `/election:process` (CSV→MD), `/election:normalize` (deterministic cleanup), `/election:calendar` (PDF→dates), `/election:enrich` (web research→bios). 159 county reference files provide Body/Seat resolution for all Georgia counties.

Known remaining items: R2 upload and procrastinate job queue deferred to backlog. `eligible_county` not populated for all elections (SOS feed elections may lack it). Statewide election inclusion in county filter requires geospatial boundary logic (deferred).

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
| Elections + Candidates first | May 19, 2026 election; smallest data type to prove the pipeline | ✓ Good — pipeline proven with 3 elections before May 19 deadline |
| mistune AST parsing for converter | Deterministic token-based parsing, no HTML rendering needed | ✓ Good — handles all markdown variations without regex fragility |
| Candidacy junction table | Many-to-many candidate-election relationship supports candidates running in multiple contests | ✓ Good — cleaner data model, enables proper relational queries |
| Body/Seat reference system | County reference files define governing body structures for district linkage resolution | ✓ Good — 159 county files cover all GA counties |
| Placeholder UUID for election_event_id | Converter can't know election_event_id at conversion time; resolved during import | ⚠️ Revisit — NULL FK after import requires separate resolve step |

| `race_category` maps to `district_type` | Avoid new column; `district_type` already populated during import | ✓ Good — zero migrations, RACE_CATEGORY_MAP handles mapping cleanly |
| Keep `district` as partial match | Changing to exact match is a breaking change for existing consumers | ✓ Good — backward compatible, no consumer breakage |
| County filter without statewide inclusion | Geospatial boundary logic is complex; simple `eligible_county` match first | ✓ Good — simple approach shipped; geospatial deferred to backlog |
| Unscoped filter options first | Scoped options add combinatorial query complexity; fast-follow if needed | ✓ Good — unscoped sufficient for ~34 elections; scoped deferred |
| Static capabilities endpoint | No DB dependency; 1-hour cache; establishes route ordering pattern | ✓ Good — route ordering prevented /{election_id} shadowing |
| ILIKE wildcard escaping | Escape %, _, \ in user search input to prevent SQL wildcard injection | ✓ Good — safe text search without full-text search overhead |

---
*Last updated: 2026-03-16 after v1.2 milestone start*
