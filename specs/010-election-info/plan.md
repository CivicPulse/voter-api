# Implementation Plan: Election Information

**Branch**: `010-election-info` | **Date**: 2026-02-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/010-election-info/spec.md`

## Summary

Extend the voter-api election data model with candidate profiles and election metadata enrichment. Two new tables (`candidates`, `candidate_links`) store forward-looking candidate information independently of SOS results. Nine new nullable columns on the existing `elections` table store descriptive metadata and milestone dates. Seven new API endpoints enable full candidate CRUD with public read access and admin-only writes, plus extended filtering on the existing election list endpoint.

## Technical Context

**Language/Version**: Python 3.13 (see `.python-version`)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), Pydantic v2, Alembic
**Storage**: PostgreSQL 15+ / PostGIS 3.x (existing)
**Testing**: pytest with pytest-asyncio, pytest-cov (90% threshold)
**Target Platform**: Linux server (piku deployment)
**Project Type**: Single project (API + CLI)
**Performance Goals**: Candidate list response < 2 seconds (SC-002)
**Constraints**: Full backward compatibility with existing election responses (SC-003)
**Scale/Scope**: ~6-10 candidates per election, ~50-100 elections total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Library-First Architecture | PASS | Candidate logic in `services/candidate_service.py` follows service-layer pattern; no standalone library needed (candidates are CRUD-only, no complex business logic warranting a `lib/` module) |
| II. Code Quality (NON-NEGOTIABLE) | PASS | All new code will include type hints, Google-style docstrings, pass ruff check/format |
| III. Testing Discipline (NON-NEGOTIABLE) | PASS | Unit tests for schemas, integration tests for service + API, E2E tests for smoke coverage; 90% threshold maintained |
| IV. Twelve-Factor Configuration | PASS | No new configuration needed — all settings use existing Pydantic Settings |
| V. Developer Experience | PASS | `uv` for all operations; migrations apply automatically; no new setup steps |
| VI. API Documentation | PASS | Pydantic schemas auto-generate OpenAPI; Swagger UI documents new endpoints |
| VII. Security by Design | PASS | Pydantic input validation, admin RBAC on all write endpoints, SQLAlchemy ORM (no raw SQL) |
| VIII. CI/CD & Version Control | PASS | Feature branch, conventional commits, existing CI workflows cover new tests |

**Library-First justification**: Candidate CRUD is straightforward service-layer logic (list, get, create, update, delete) without complex algorithms, external integrations, or reusable business rules. Placing it in `services/candidate_service.py` follows the established pattern for similar CRUD features (e.g., `election_service.py`). A `lib/` module would add abstraction without benefit.

## Project Structure

### Documentation (this feature)

```text
specs/010-election-info/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Database schema design
├── quickstart.md        # Setup and usage guide
├── contracts/
│   └── openapi.yaml     # API contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Task breakdown (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/voter_api/
├── models/
│   ├── candidate.py           # NEW: Candidate + CandidateLink ORM models
│   └── election.py            # MODIFIED: new metadata columns + candidates relationship
├── schemas/
│   ├── candidate.py           # NEW: request/response Pydantic schemas
│   └── election.py            # MODIFIED: extended update request + response schemas
├── services/
│   └── candidate_service.py   # NEW: candidate CRUD + list logic
├── api/v1/
│   ├── candidates.py          # NEW: candidate route handlers
│   └── elections.py           # MODIFIED: new filter parameters
└── main.py                    # MODIFIED: register candidates router

alembic/versions/
├── 037_add_candidates.py                  # NEW: candidates + candidate_links tables
└── 038_add_election_metadata.py           # NEW: metadata columns on elections

tests/
├── unit/
│   └── test_candidate_schemas.py          # NEW: schema validation
├── integration/
│   ├── test_candidate_service.py          # NEW: service layer tests
│   ├── test_candidate_api.py             # NEW: candidate API route tests
│   └── test_election_metadata_api.py     # NEW: election metadata + filter tests
└── e2e/
    └── test_smoke.py                      # MODIFIED: new TestCandidates class
```

**Structure Decision**: Single project, extending existing patterns. New files follow established naming conventions (`models/candidate.py` parallels `models/elected_official.py`, `services/candidate_service.py` parallels `services/elected_official_service.py`). No new `lib/` module — CRUD-only logic stays in the service layer.

## Implementation Phases

### Phase 1: Database Schema (migrations)

1. Create `alembic/versions/037_add_candidates.py`:
   - `candidates` table: UUID PK, election_id FK (CASCADE), full_name, party, bio, photo_url, ballot_order, filing_status, is_incumbent, sos_ballot_option_id, timestamps
   - `candidate_links` table: UUID PK, candidate_id FK (CASCADE), link_type, url, label, created_at
   - Constraints: `uq_candidate_election_name`, `ck_candidate_filing_status`, `ck_candidate_link_type`
   - Indexes: `ix_candidates_election_id`, `ix_candidates_filing_status`, `ix_candidates_sos_ballot_option_id`, `ix_candidate_links_candidate_id`

2. Create `alembic/versions/038_add_election_metadata.py`:
   - Add 9 nullable columns to `elections`: description, purpose, eligibility_description, registration_deadline, early_voting_start, early_voting_end, absentee_request_deadline, qualifying_start, qualifying_end

### Phase 2: ORM Models

1. Create `src/voter_api/models/candidate.py`:
   - `Candidate(Base, UUIDMixin, TimestampMixin)` with all columns from data-model
   - `CandidateLink(Base, UUIDMixin)` with candidate_id FK, link_type, url, label, created_at
   - Relationship: `Candidate.links` → `CandidateLink` with `lazy="selectin"`, `cascade="all, delete-orphan"`

2. Modify `src/voter_api/models/election.py`:
   - Add 9 new nullable columns to `Election`
   - Add `candidates` relationship → `Candidate` with `cascade="all, delete-orphan"`

3. Register model in `src/voter_api/models/__init__.py`

### Phase 3: Pydantic Schemas

1. Create `src/voter_api/schemas/candidate.py`:
   - `CandidateLinkResponse`, `CandidateLinkCreateRequest`
   - `CandidateSummaryResponse` (for list endpoints)
   - `CandidateDetailResponse(CandidateSummaryResponse)` (adds bio, links, sos_ballot_option_id, updated_at)
   - `PaginatedCandidateResponse` (items + pagination)
   - `CandidateCreateRequest` (full_name required, rest optional, includes optional `links` array)
   - `CandidateUpdateRequest` (all fields optional for PATCH)
   - Field validator for `filing_status` and `link_type` enums

2. Modify `src/voter_api/schemas/election.py`:
   - Add 9 new optional fields to `ElectionUpdateRequest`
   - Add 9 new nullable fields to `ElectionSummary` and `ElectionDetailResponse`

### Phase 4: Service Layer

1. Create `src/voter_api/services/candidate_service.py`:
   - `list_candidates(session, election_id, *, status, page, page_size) -> tuple[list[Candidate], int]`
   - `get_candidate(session, candidate_id) -> Candidate | None`
   - `create_candidate(session, election_id, body) -> Candidate` — validates election exists, creates candidate + initial links, handles IntegrityError → ValueError
   - `update_candidate(session, candidate, updates) -> Candidate` — `_UPDATABLE_FIELDS` allowlist pattern
   - `delete_candidate(session, candidate) -> None`
   - `add_candidate_link(session, candidate_id, body) -> CandidateLink`
   - `delete_candidate_link(session, candidate_id, link_id) -> None`

### Phase 5: API Routes

1. Create `src/voter_api/api/v1/candidates.py`:
   - `GET /elections/{election_id}/candidates` — public, paginated, status filter
   - `POST /elections/{election_id}/candidates` — admin, returns 201
   - `GET /candidates/{candidate_id}` — public
   - `PATCH /candidates/{candidate_id}` — admin
   - `DELETE /candidates/{candidate_id}` — admin, returns 204
   - `POST /candidates/{candidate_id}/links` — admin, returns 201
   - `DELETE /candidates/{candidate_id}/links/{link_id}` — admin, returns 204

2. Modify `src/voter_api/api/v1/elections.py`:
   - Add `registration_open`, `early_voting_active`, `district_type`, `district_identifier` query parameters to list endpoint

3. Register router in `src/voter_api/main.py`

### Phase 6: Tests

1. Unit tests (`tests/unit/test_candidate_schemas.py`):
   - Schema validation: required fields, optional fields, enum constraints, link types
   - Create request with/without links
   - Update request partial validation

2. Integration tests (`tests/integration/test_candidate_service.py`):
   - CRUD operations with in-memory SQLite
   - Duplicate name detection (409)
   - Cascade delete behavior
   - Pagination and status filtering

3. Integration tests (`tests/integration/test_candidate_api.py`):
   - All 7 endpoints: happy paths + error cases
   - RBAC enforcement (401/403)
   - Election 404 when creating candidate for nonexistent election
   - Election metadata update via existing PATCH

4. E2E tests (`tests/e2e/test_smoke.py`):
   - Add `TestCandidates` class: list, create, detail, update, delete, link add/remove
   - Update `TestElections`: verify new metadata fields in detail response
   - Seed data: add candidate + link rows to `seed_database` fixture

5. Lint and coverage check:
   - `uv run ruff check . && uv run ruff format --check .`
   - `uv run pytest --cov=voter_api --cov-report=term-missing` (90% threshold)

## Complexity Tracking

No constitution violations to justify. All design choices follow established patterns.
