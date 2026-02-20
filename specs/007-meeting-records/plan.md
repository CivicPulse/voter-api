# Implementation Plan: Meeting Records API

**Branch**: `007-meeting-records` | **Date**: 2026-02-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-meeting-records/spec.md`

## Summary

Build the core API for storing, retrieving, and searching local government meeting records. This adds 6 new database tables (governing body types, governing bodies, meetings, agenda items, attachments, video embeds), ~35 REST endpoints under `/api/v1/`, a standalone `lib/meetings/` library for file storage and validation, PostgreSQL full-text search via `tsvector`/GIN, a contributor role with meeting-level approval workflow, and local filesystem file upload/download.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), Pydantic v2, Alembic, Typer, Loguru, aiofiles (new — async file I/O)
**Storage**: PostgreSQL 15+ / PostGIS 3.x (existing) + local filesystem for attachments (new)
**Testing**: pytest with pytest-asyncio, pytest-cov (90% coverage threshold)
**Target Platform**: Linux server (piku deployment)
**Project Type**: Single project (API + CLI)
**Performance Goals**: All list/search endpoints < 2s response with 100K meetings
**Constraints**: 50 MB max file upload, JWT auth with role-based access
**Scale/Scope**: 100K+ meetings, 5+ years historical data per governing body

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Library-First Architecture | PASS | `lib/meetings/` with validators and file storage abstraction |
| II. Code Quality (NON-NEGOTIABLE) | PASS | Type hints, Google-style docstrings, ruff compliance on all new code |
| III. Testing Discipline (NON-NEGOTIABLE) | PASS | Unit tests for lib/schemas/services, integration tests for API, contract tests for OpenAPI |
| IV. Twelve-Factor Configuration | PASS | `MEETING_UPLOAD_DIR`, `MEETING_MAX_FILE_SIZE_MB` via Pydantic Settings |
| V. Developer Experience | PASS | CLI commands via Typer for type seeding; `uv` for all operations |
| VI. API Documentation | PASS | All endpoints via FastAPI + Pydantic schemas; OpenAPI contract in `contracts/openapi.yaml` |
| VII. Security by Design | PASS | Pydantic validation on all inputs, role-based auth on all endpoints, no raw SQL |
| VIII. CI/CD & Version Control | PASS | Conventional Commits, feature branch, GitHub Actions CI |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/007-meeting-records/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research decisions
├── data-model.md        # Phase 1 data model design
├── quickstart.md        # Phase 1 API reference and setup
├── contracts/
│   └── openapi.yaml     # Phase 1 OpenAPI 3.1 contract
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/voter_api/
├── models/
│   ├── base.py                    # Add SoftDeleteMixin
│   ├── governing_body_type.py     # NEW — GoverningBodyType model
│   ├── governing_body.py          # NEW — GoverningBody model
│   ├── meeting.py                 # NEW — Meeting model with approval fields
│   ├── agenda_item.py             # NEW — AgendaItem model with tsvector
│   ├── meeting_attachment.py      # NEW — MeetingAttachment model
│   ├── meeting_video_embed.py     # NEW — MeetingVideoEmbed model
│   └── __init__.py                # Update with new model imports
├── schemas/
│   ├── governing_body_type.py     # NEW — Type CRUD schemas
│   ├── governing_body.py          # NEW — Body CRUD + paginated schemas
│   ├── meeting.py                 # NEW — Meeting CRUD + approval + paginated schemas
│   ├── agenda_item.py             # NEW — AgendaItem CRUD + reorder schemas
│   ├── meeting_attachment.py      # NEW — Attachment response schema
│   ├── meeting_video_embed.py     # NEW — VideoEmbed CRUD schemas
│   └── meeting_search.py          # NEW — Search result + paginated schemas
├── services/
│   ├── governing_body_type_service.py  # NEW
│   ├── governing_body_service.py       # NEW
│   ├── meeting_service.py              # NEW — includes approval logic
│   ├── agenda_item_service.py          # NEW — includes reorder logic
│   ├── meeting_attachment_service.py   # NEW — includes file storage calls
│   ├── meeting_video_embed_service.py  # NEW
│   └── meeting_search_service.py       # NEW — full-text search queries
├── api/
│   ├── router.py                  # Update with new router registrations
│   └── v1/
│       ├── governing_body_types.py    # NEW — 2 endpoints
│       ├── governing_bodies.py        # NEW — 5 endpoints
│       ├── meetings.py                # NEW — 8 endpoints (CRUD + approve/reject + search)
│       ├── agenda_items.py            # NEW — 6 endpoints (CRUD + reorder)
│       ├── attachments.py             # NEW — 7 endpoints (upload/download/list/delete)
│       └── video_embeds.py            # NEW — 7 endpoints (CRUD per parent type)
├── lib/
│   └── meetings/                  # NEW library
│       ├── __init__.py            # Public API: validators, storage
│       ├── validators.py          # File format, video URL, meeting type validation
│       └── storage.py             # FileStorage Protocol + LocalFileStorage impl
├── core/
│   └── config.py                  # Add MEETING_UPLOAD_DIR, MEETING_MAX_FILE_SIZE_MB
└── cli/
    └── meetings.py                # NEW — seed-types CLI command

alembic/versions/
└── 023_create_meeting_records_tables.py  # NEW migration

tests/
├── unit/
│   ├── lib/test_meetings/
│   │   ├── test_validators.py     # File format, video URL validation
│   │   └── test_storage.py        # Local file storage
│   ├── schemas/
│   │   ├── test_governing_body_type_schemas.py
│   │   ├── test_governing_body_schemas.py
│   │   ├── test_meeting_schemas.py
│   │   ├── test_agenda_item_schemas.py
│   │   ├── test_attachment_schemas.py
│   │   └── test_video_embed_schemas.py
│   └── services/
│       ├── test_governing_body_type_service.py
│       ├── test_governing_body_service.py
│       ├── test_meeting_service.py
│       ├── test_agenda_item_service.py
│       ├── test_attachment_service.py
│       ├── test_video_embed_service.py
│       └── test_search_service.py
├── integration/
│   └── api/
│       ├── test_governing_body_types_api.py
│       ├── test_governing_bodies_api.py
│       ├── test_meetings_api.py
│       ├── test_agenda_items_api.py
│       ├── test_attachments_api.py
│       ├── test_video_embeds_api.py
│       └── test_search_api.py
└── contract/
    └── test_meeting_records_contract.py
```

**Structure Decision**: Single project layout following the existing `src/voter_api/` convention. New code follows the established layer pattern: models → schemas → services → API routes, with standalone library in `lib/meetings/`.

## Key Design Decisions

### D1: SoftDeleteMixin

Add a reusable `SoftDeleteMixin` to `models/base.py` with `deleted_at: Mapped[datetime | None]`. 5 of 6 new tables use this mixin (all except `governing_body_types`, which is a lookup table not subject to soft delete). Service-layer queries filter `WHERE deleted_at IS NULL` by default.

### D2: PostgreSQL Full-Text Search

Use a generated `tsvector` column on `agenda_items` with weighted fields (title=A, description=B) and a GIN index. Search across attachment filenames via `ILIKE` join. Results unified and ranked by `ts_rank` in the search service.

### D3: Local Filesystem File Storage

Files stored at `{MEETING_UPLOAD_DIR}/{year}/{month}/{uuid}.{ext}`. Abstracted behind a `FileStorage` Protocol in `lib/meetings/storage.py` for future S3/R2 migration. New dependency: `aiofiles` for async file I/O.

### D4: Exclusive Belongs-To for Attachments/Video Embeds

Two nullable FK columns (`meeting_id`, `agenda_item_id`) with a CHECK constraint enforcing exactly one is NOT NULL. Preserves database-level referential integrity without generic FK complexity.

### D5: Meeting-Level Approval Workflow

Approval fields (`approval_status`, `submitted_by`, `approved_by`, `approved_at`, `rejection_reason`) live on the `meetings` table only. Child records inherit meeting approval status. Admin-created meetings default to `approved`; contributor-created meetings default to `pending`.

### D6: Admin-Extensible Governing Body Types

Dedicated `governing_body_types` lookup table with `is_default` flag. Default types seeded in migration. Admin-only CRUD endpoint. Slug column for stable URL-safe filtering.

### D7: Gap-Based Agenda Item Ordering

Integer `display_order` with gaps of 10 for new items. Bulk reorder endpoint accepts ordered list of item IDs and sets sequential positions atomically.

## Implementation Phases

### Phase 1: Foundation (Library + Models + Migration)

1. Add `SoftDeleteMixin` to `models/base.py`
2. Create `lib/meetings/` library (validators, storage)
3. Create all 6 new model files
4. Update `models/__init__.py` with new imports
5. Add config settings (`MEETING_UPLOAD_DIR`, `MEETING_MAX_FILE_SIZE_MB`)
6. Write Alembic migration `023_create_meeting_records_tables.py`
7. Unit tests for library and model enums

### Phase 2: Schemas + Services (Governing Bodies)

1. Create Pydantic schemas for governing body types and governing bodies
2. Create service functions for governing body type CRUD
3. Create service functions for governing body CRUD (with soft delete)
4. Unit tests for schemas and services

### Phase 3: Schemas + Services (Meetings + Agenda Items)

1. Create Pydantic schemas for meetings and agenda items
2. Create meeting service (CRUD, approval workflow, visibility filtering)
3. Create agenda item service (CRUD, reorder logic)
4. Unit tests for schemas and services

### Phase 4: Schemas + Services (Attachments + Video Embeds)

1. Create Pydantic schemas for attachments and video embeds
2. Create attachment service (upload, download, list, delete)
3. Create video embed service (CRUD, URL validation)
4. Unit tests for schemas and services

### Phase 5: Search Service

1. Create search schemas (result items, paginated response)
2. Create search service (tsvector query + attachment filename join)
3. Unit tests for search service

### Phase 6: API Routes

1. Create route files for all 6 resource groups
2. Register routes in `api/router.py`
3. Integration tests for all endpoints (auth, CRUD, filtering, pagination)

### Phase 7: CLI + Contract Tests + Polish

1. Add `meetings seed-types` CLI command
2. Contract tests against `openapi.yaml`
3. Update `models/__init__.py` imports for Alembic
4. Update `.env.example` with new settings
5. Run full test suite, lint, coverage check

## References

- [spec.md](./spec.md) — Feature specification with clarifications
- [research.md](./research.md) — Technical research decisions
- [data-model.md](./data-model.md) — Database schema design
- [contracts/openapi.yaml](./contracts/openapi.yaml) — OpenAPI 3.1 contract
- [quickstart.md](./quickstart.md) — Setup and API reference
- [checklists/requirements.md](./checklists/requirements.md) — Spec quality checklist
