# Tasks: Meeting Records API

**Input**: Design documents from `/specs/007-meeting-records/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/openapi.yaml, research.md

**Tests**: Included per constitution Principle III (Testing Discipline — NON-NEGOTIABLE, 90% coverage).

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: New dependency, shared mixin, standalone library, and configuration

- [x] T001 Add `aiofiles` dependency via `uv add aiofiles` and `uv add --dev types-aiofiles`
- [x] T002 Add `SoftDeleteMixin` with `deleted_at: Mapped[datetime | None]` column to `src/voter_api/models/base.py`
- [x] T003 [P] Create file format and video URL validators in `src/voter_api/lib/meetings/validators.py` — validate allowed MIME types (pdf, doc/docx, xls/xlsx, csv, png, jpg/jpeg, gif, tiff), YouTube/Vimeo domain check, and timestamp validation
- [x] T004 [P] Create `FileStorage` Protocol and `LocalFileStorage` implementation in `src/voter_api/lib/meetings/storage.py` — async save/load/delete with `{year}/{month}/{uuid}.{ext}` path structure using `aiofiles`
- [x] T005 [P] Create public API exports in `src/voter_api/lib/meetings/__init__.py` — export validators and storage classes via `__all__`
- [x] T006 [P] Add `MEETING_UPLOAD_DIR` (default `./uploads/meetings`) and `MEETING_MAX_FILE_SIZE_MB` (default 50) settings to `src/voter_api/core/config.py`
- [x] T007 [P] Unit tests for validators in `tests/unit/lib/test_meetings/test_validators.py` — file format acceptance/rejection, video URL validation for YouTube/Vimeo/invalid domains, timestamp validation
- [x] T008 [P] Unit tests for local file storage in `tests/unit/lib/test_meetings/test_storage.py` — save/load/delete operations, directory creation, path structure verification

**Checkpoint**: Library, mixin, and config ready. Models can now be created.

---

## Phase 2: Foundation (Models + Migration)

**Purpose**: All 6 database models and the Alembic migration. MUST complete before any user story.

**CRITICAL**: No user story work can begin until this phase is complete.

- [x] T009 [P] Create `GoverningBodyType` model in `src/voter_api/models/governing_body_type.py` — UUID PK, name (unique), slug (unique), description, is_default flag, created_at. Uses `Base`, `UUIDMixin` (no `SoftDeleteMixin` — types are not soft-deleted)
- [x] T010 [P] Create `GoverningBody` model in `src/voter_api/models/governing_body.py` — UUID PK, name, type_id FK, jurisdiction, description, website_url. Uses `Base`, `UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`. Partial unique on `(name, jurisdiction) WHERE deleted_at IS NULL`. Relationship to GoverningBodyType
- [x] T011 [P] Create `Meeting` model in `src/voter_api/models/meeting.py` — UUID PK, governing_body_id FK, meeting_date, location, meeting_type (StrEnum), status (StrEnum), external_source_url, approval_status (StrEnum: pending/approved/rejected), submitted_by/approved_by FKs to users, approved_at, rejection_reason. Uses `SoftDeleteMixin`, `TimestampMixin`. CHECK constraints for enums
- [x] T012 [P] Create `AgendaItem` model in `src/voter_api/models/agenda_item.py` — UUID PK, meeting_id FK, title, description, action_taken, disposition (StrEnum), display_order, search_vector (tsvector generated column). Uses `SoftDeleteMixin`, `TimestampMixin`. Partial unique on `(meeting_id, display_order) WHERE deleted_at IS NULL`
- [x] T013 [P] Create `MeetingAttachment` model in `src/voter_api/models/meeting_attachment.py` — UUID PK, meeting_id FK (nullable), agenda_item_id FK (nullable), original_filename, stored_path, file_size, content_type, created_at. Uses `SoftDeleteMixin`. CHECK constraint for exclusive belongs-to
- [x] T014 [P] Create `MeetingVideoEmbed` model in `src/voter_api/models/meeting_video_embed.py` — UUID PK, meeting_id FK (nullable), agenda_item_id FK (nullable), video_url, platform (StrEnum: youtube/vimeo), start_seconds, end_seconds, created_at. Uses `SoftDeleteMixin`. CHECK constraints for exclusive belongs-to and timestamp ordering
- [x] T015 Update `src/voter_api/models/__init__.py` — import all 6 new models and add to `__all__` for Alembic autogenerate discovery
- [x] T016 Write Alembic migration `alembic/versions/023_create_meeting_records_tables.py` — create all 6 tables per data-model.md, seed 7 default governing body types, update users CHECK constraint to include 'contributor' role. Revision 023, down_revision 022
- [x] T017 Update `alembic/env.py` — add imports for all 6 new models

**Checkpoint**: Foundation ready — all tables exist, models importable. User story implementation can begin.

---

## Phase 3: User Story 1 — Manage Governing Bodies (Priority: P1) MVP

**Goal**: Admins can create, list, update, and soft-delete governing bodies with extensible type system.

**Independent Test**: Create a governing body with type and jurisdiction, list with filters, update, soft-delete. Verify deletion prevention when meetings exist.

### Implementation for User Story 1

- [ ] T018 [P] [US1] Create governing body type schemas in `src/voter_api/schemas/governing_body_type.py` — `GoverningBodyTypeResponse` (from_attributes), `GoverningBodyTypeCreateRequest` (name required, description optional; auto-generate slug)
- [ ] T019 [P] [US1] Create governing body schemas in `src/voter_api/schemas/governing_body.py` — `GoverningBodySummaryResponse`, `GoverningBodyDetailResponse` (extends Summary with description, meeting_count, updated_at), `GoverningBodyCreateRequest`, `GoverningBodyUpdateRequest` (all fields optional), `PaginatedGoverningBodyResponse`
- [ ] T020 [P] [US1] Create governing body type service in `src/voter_api/services/governing_body_type_service.py` — `list_types()`, `create_type(session, *, name, description)` with slug generation and uniqueness check
- [ ] T021 [US1] Create governing body service in `src/voter_api/services/governing_body_service.py` — `list_bodies(session, *, type_id, jurisdiction, page, page_size)` with soft-delete filter, `get_body(session, body_id)`, `create_body(session, *, data)`, `update_body(session, body_id, *, data)`, `delete_body(session, body_id)` with active-meeting check. `_UPDATABLE_FIELDS` guard
- [ ] T022 [US1] Create governing body types API routes in `src/voter_api/api/v1/governing_body_types.py` — `GET /governing-body-types` (any role), `POST /governing-body-types` (admin only)
- [ ] T023 [US1] Create governing bodies API routes in `src/voter_api/api/v1/governing_bodies.py` — `GET /governing-bodies` (paginated, filter by type_id, jurisdiction), `POST /governing-bodies` (admin), `GET /governing-bodies/{id}`, `PATCH /governing-bodies/{id}` (admin), `DELETE /governing-bodies/{id}` (admin, soft delete)
- [ ] T024 [US1] Register governing body type and governing body routers in `src/voter_api/api/router.py`

### Tests for User Story 1

- [ ] T025 [P] [US1] Unit tests for governing body type schemas in `tests/unit/schemas/test_governing_body_type_schemas.py`
- [ ] T026 [P] [US1] Unit tests for governing body schemas in `tests/unit/schemas/test_governing_body_schemas.py` — validation, from_attributes, optional fields on update
- [ ] T027 [P] [US1] Unit tests for governing body type service in `tests/unit/services/test_governing_body_type_service.py` — list, create, duplicate name rejection
- [ ] T028 [P] [US1] Unit tests for governing body service in `tests/unit/services/test_governing_body_service.py` — CRUD, soft-delete filter, deletion prevention with active meetings, pagination
- [ ] T029 [P] [US1] Integration tests for governing body types API in `tests/integration/api/test_governing_body_types_api.py` — list types, create type (admin only), 403 for non-admin
- [ ] T030 [P] [US1] Integration tests for governing bodies API in `tests/integration/api/test_governing_bodies_api.py` — CRUD lifecycle, pagination, filtering, soft-delete, deletion prevention, 403 for non-admin writes

**Checkpoint**: Governing bodies fully functional. Admins can manage body types and bodies with all acceptance scenarios passing.

---

## Phase 4: User Story 2 — Record and Browse Meetings (Priority: P1)

**Goal**: Create meeting records under governing bodies with date/time, type, status, approval workflow. Browse with filters and pagination.

**Independent Test**: Create meetings under a governing body, filter by date/body/type/status, verify pagination, test admin approve/reject of contributor submissions.

**Depends on**: US1 (governing bodies must exist)

### Implementation for User Story 2

- [ ] T031 [P] [US2] Create meeting schemas in `src/voter_api/schemas/meeting.py` — `MeetingSummaryResponse` (with governing_body_name), `MeetingDetailResponse` (extends Summary with child counts, approval fields), `MeetingCreateRequest`, `MeetingUpdateRequest`, `MeetingRejectRequest` (reason required), `PaginatedMeetingResponse`. Include `MeetingTypeEnum`, `MeetingStatusEnum`, `ApprovalStatusEnum`
- [ ] T032 [US2] Create meeting service in `src/voter_api/services/meeting_service.py` — `list_meetings(session, *, governing_body_id, date_from, date_to, meeting_type, status, page, page_size, current_user)` with approval-based visibility (non-admin sees only approved + own pending), `get_meeting(session, meeting_id, current_user)` with child counts, `create_meeting(session, *, data, current_user)` (admin→approved, contributor→pending), `update_meeting()`, `delete_meeting()` with cascade soft-delete, `approve_meeting(session, meeting_id, admin_user)`, `reject_meeting(session, meeting_id, admin_user, reason)`
- [ ] T033 [US2] Create meetings API routes in `src/voter_api/api/v1/meetings.py` — `GET /meetings` (paginated+filtered), `POST /meetings` (admin/contributor), `GET /meetings/{id}` (detail with counts), `PATCH /meetings/{id}`, `DELETE /meetings/{id}` (admin), `POST /meetings/{id}/approve` (admin), `POST /meetings/{id}/reject` (admin). Note: search endpoint placeholder — implemented in US6
- [ ] T034 [US2] Register meetings router in `src/voter_api/api/router.py`

### Tests for User Story 2

- [ ] T035 [P] [US2] Unit tests for meeting schemas in `tests/unit/schemas/test_meeting_schemas.py` — enum validation, required fields, optional fields on update, reject reason required
- [ ] T036 [P] [US2] Unit tests for meeting service in `tests/unit/services/test_meeting_service.py` — CRUD, filter combinations, approval workflow (admin auto-approved, contributor pending), visibility filtering (non-admin sees only approved + own pending), cascade soft-delete, approve/reject logic
- [ ] T037 [US2] Integration tests for meetings API in `tests/integration/api/test_meetings_api.py` — full CRUD lifecycle, all filter combinations, pagination, approval workflow (admin create→approved, contributor create→pending, admin approve, admin reject with reason), cascade soft-delete, 403 for unauthorized operations

**Checkpoint**: Meetings fully functional with approval workflow. Admins and contributors can create meetings; admins can approve/reject.

---

## Phase 5: User Story 3 — Manage Agenda Items (Priority: P1)

**Goal**: Add ordered agenda items to meetings with title, description, disposition. Support reordering.

**Independent Test**: Add agenda items to a meeting, verify display order, reorder items, update disposition, soft-delete with order preservation.

**Depends on**: US2 (meetings must exist)

### Implementation for User Story 3

- [ ] T038 [P] [US3] Create agenda item schemas in `src/voter_api/schemas/agenda_item.py` — `AgendaItemResponse` (with attachment_count, video_embed_count), `AgendaItemCreateRequest` (title required, display_order optional — auto-append if omitted), `AgendaItemUpdateRequest`, `AgendaItemReorderRequest` (ordered list of item UUIDs), `DispositionEnum`
- [ ] T039 [US3] Create agenda item service in `src/voter_api/services/agenda_item_service.py` — `list_items(session, meeting_id)` ordered by display_order with soft-delete filter, `get_item(session, item_id)`, `create_item(session, *, meeting_id, data)` with gap-based ordering (gaps of 10, auto-append if no position), `update_item()`, `delete_item()` with order preservation, `reorder_items(session, meeting_id, item_ids)` atomic position reassignment
- [ ] T040 [US3] Create agenda items API routes in `src/voter_api/api/v1/agenda_items.py` — `GET /meetings/{mid}/agenda-items`, `POST /meetings/{mid}/agenda-items` (admin/contributor), `GET /meetings/{mid}/agenda-items/{id}`, `PATCH /meetings/{mid}/agenda-items/{id}`, `DELETE /meetings/{mid}/agenda-items/{id}` (admin), `PUT /meetings/{mid}/agenda-items/reorder` (admin/contributor). Fixed route `/reorder` BEFORE parameterized `/{id}`
- [ ] T041 [US3] Register agenda items router in `src/voter_api/api/router.py`

### Tests for User Story 3

- [ ] T042 [P] [US3] Unit tests for agenda item schemas in `tests/unit/schemas/test_agenda_item_schemas.py` — disposition enum, optional display_order, reorder request validation
- [ ] T043 [P] [US3] Unit tests for agenda item service in `tests/unit/services/test_agenda_item_service.py` — CRUD, gap-based ordering, auto-append, reorder logic, soft-delete order preservation
- [ ] T044 [US3] Integration tests for agenda items API in `tests/integration/api/test_agenda_items_api.py` — CRUD lifecycle, ordering verification, reorder endpoint, soft-delete, 403 for non-admin deletes

**Checkpoint**: All P1 stories complete. Core meeting data structure (bodies → meetings → agenda items) is fully functional.

---

## Phase 6: User Story 4 — Upload and Download File Attachments (Priority: P2)

**Goal**: Upload documents to meetings or agenda items. List, download, and soft-delete attachments.

**Independent Test**: Upload a PDF to a meeting, upload a DOCX to an agenda item, list both, download with correct content type, reject `.exe` upload, verify 50 MB limit.

**Depends on**: US2 (meetings), US3 (agenda items)

### Implementation for User Story 4

- [ ] T045 [P] [US4] Create attachment schemas in `src/voter_api/schemas/meeting_attachment.py` — `AttachmentResponse` (with download_url computed field), upload is multipart/form-data (no request schema — uses `UploadFile`)
- [ ] T046 [US4] Create attachment service in `src/voter_api/services/meeting_attachment_service.py` — `list_attachments(session, *, meeting_id, agenda_item_id)` with soft-delete filter, `get_attachment(session, attachment_id)`, `upload_attachment(session, *, file_content, filename, content_type, meeting_id, agenda_item_id, storage)` with format validation and size check via lib/meetings validators, `download_attachment(session, attachment_id, storage)` returns bytes + metadata, `delete_attachment(session, attachment_id)` soft-delete only (file preserved)
- [ ] T047 [US4] Create attachments API routes in `src/voter_api/api/v1/attachments.py` — `POST /meetings/{mid}/attachments`, `GET /meetings/{mid}/attachments`, `POST /meetings/{mid}/agenda-items/{aid}/attachments`, `GET /meetings/{mid}/agenda-items/{aid}/attachments`, `GET /attachments/{id}`, `GET /attachments/{id}/download` (StreamingResponse with Content-Disposition), `DELETE /attachments/{id}` (admin). Inject `LocalFileStorage` via dependency
- [ ] T048 [US4] Register attachments router in `src/voter_api/api/router.py`

### Tests for User Story 4

- [ ] T049 [P] [US4] Unit tests for attachment schemas in `tests/unit/schemas/test_attachment_schemas.py`
- [ ] T050 [P] [US4] Unit tests for attachment service in `tests/unit/services/test_attachment_service.py` — upload with valid/invalid formats, size limit enforcement, list by meeting/agenda item, download, soft-delete
- [ ] T051 [US4] Integration tests for attachments API in `tests/integration/api/test_attachments_api.py` — upload to meeting and agenda item, list (includes item-level attachments when listing meeting), download with correct headers, reject unsupported format (422), reject oversized file (413), soft-delete

**Checkpoint**: File attachments working. Documents can be uploaded, listed, downloaded, and soft-deleted.

---

## Phase 7: User Story 5 — Add Video Embeds (Priority: P2)

**Goal**: Associate YouTube/Vimeo video URLs with meetings or agenda items, with optional timestamps.

**Independent Test**: Add a YouTube URL to a meeting, add a Vimeo URL with timestamps to an agenda item, reject invalid URL, verify retrieval.

**Depends on**: US2 (meetings), US3 (agenda items). Can run in parallel with US4.

### Implementation for User Story 5

- [ ] T052 [P] [US5] Create video embed schemas in `src/voter_api/schemas/meeting_video_embed.py` — `VideoEmbedResponse`, `VideoEmbedCreateRequest` (video_url required, start_seconds/end_seconds optional), `VideoEmbedUpdateRequest`, `VideoPlatformEnum`
- [ ] T053 [US5] Create video embed service in `src/voter_api/services/meeting_video_embed_service.py` — `list_embeds(session, *, meeting_id, agenda_item_id)` with soft-delete filter, `get_embed(session, embed_id)`, `create_embed(session, *, data, meeting_id, agenda_item_id)` with URL validation via lib/meetings validators (detect platform from URL), `update_embed()`, `delete_embed()` soft-delete
- [ ] T054 [US5] Create video embeds API routes in `src/voter_api/api/v1/video_embeds.py` — `POST /meetings/{mid}/video-embeds`, `GET /meetings/{mid}/video-embeds`, `POST /meetings/{mid}/agenda-items/{aid}/video-embeds`, `GET /meetings/{mid}/agenda-items/{aid}/video-embeds`, `GET /video-embeds/{id}`, `PATCH /video-embeds/{id}`, `DELETE /video-embeds/{id}` (admin)
- [ ] T055 [US5] Register video embeds router in `src/voter_api/api/router.py`

### Tests for User Story 5

- [ ] T056 [P] [US5] Unit tests for video embed schemas in `tests/unit/schemas/test_video_embed_schemas.py` — URL format, platform enum, optional timestamps
- [ ] T057 [P] [US5] Unit tests for video embed service in `tests/unit/services/test_video_embed_service.py` — CRUD, URL validation (YouTube accepted, Vimeo accepted, other rejected), platform auto-detection, timestamp validation
- [ ] T058 [US5] Integration tests for video embeds API in `tests/integration/api/test_video_embeds_api.py` — CRUD lifecycle for meeting-level and item-level embeds, invalid URL rejection (422), timestamp handling

**Checkpoint**: Video embeds working. Recordings can be linked to meetings and agenda items with optional timestamps.

---

## Phase 8: User Story 6 — Search Across Meeting Records (Priority: P2)

**Goal**: Full-text search across agenda item titles/descriptions and attachment filenames with relevance ranking.

**Independent Test**: Create meetings with agenda items and attachments, search for known terms, verify relevance ranking, pagination, and contextual results.

**Depends on**: US3 (agenda items with tsvector), US4 (attachments with filenames)

### Implementation for User Story 6

- [ ] T059 [P] [US6] Create search schemas in `src/voter_api/schemas/meeting_search.py` — `SearchResultItem` (agenda_item_id, title, description_excerpt, meeting_id, meeting_date, meeting_type, governing_body_id, governing_body_name, match_source enum, relevance_score), `PaginatedSearchResultResponse`
- [ ] T060 [US6] Create search service in `src/voter_api/services/meeting_search_service.py` — `search_meetings(session, *, query, page, page_size, current_user)` using `plainto_tsquery('english', query)` against `agenda_items.search_vector` with `ts_rank` for relevance, UNION with attachment filename ILIKE match, JOIN to meetings and governing_bodies for context, respect approval visibility (non-admin sees only approved), minimum 2-char query enforcement
- [ ] T061 [US6] Add search endpoint `GET /meetings/search` to `src/voter_api/api/v1/meetings.py` — query param `q` (min 2 chars), standard pagination. Must be defined BEFORE `/{id}` route to avoid path conflict

### Tests for User Story 6

- [ ] T062 [P] [US6] Unit tests for search schemas in `tests/unit/schemas/test_meeting_search_schemas.py`
- [ ] T063 [P] [US6] Unit tests for search service in `tests/unit/services/test_search_service.py` — query building, relevance ranking, approval filtering, minimum query length validation, empty results
- [ ] T064 [US6] Integration tests for search API in `tests/integration/api/test_search_api.py` — search by agenda item text, search by attachment filename, relevance ranking, pagination, empty results, short query rejection (422)

**Checkpoint**: Full-text search working. Users can discover meeting topics across the entire archive.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: CLI, contract tests, and final validation

- [ ] T065 Create `meetings seed-types` CLI command in `src/voter_api/cli/meetings.py` — seeds default governing body types (idempotent, skips existing)
- [ ] T066 Register meetings CLI group in the main Typer app
- [ ] T067 Contract tests against `specs/007-meeting-records/contracts/openapi.yaml` in `tests/contract/test_meeting_records_contract.py` — verify all endpoints match the OpenAPI spec (response schemas, status codes, required fields)
- [ ] T068 Update `.env.example` with `MEETING_UPLOAD_DIR` and `MEETING_MAX_FILE_SIZE_MB` settings
- [ ] T069 Add `uploads/` to `.gitignore` if not already present
- [ ] T070 Run `uv run ruff check .` and `uv run ruff format --check .` — fix any violations
- [ ] T071 Run `uv run pytest --cov=voter_api --cov-report=term-missing` — verify 90%+ coverage, fix gaps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundation (Phase 2)**: Depends on Phase 1 (SoftDeleteMixin, lib) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — No dependencies on other stories
- **US2 (Phase 4)**: Depends on Phase 2 + US1 (needs governing bodies)
- **US3 (Phase 5)**: Depends on US2 (needs meetings)
- **US4 (Phase 6)**: Depends on US2 + US3 (needs meetings and agenda items)
- **US5 (Phase 7)**: Depends on US2 + US3 (needs meetings and agenda items) — **can run in parallel with US4**
- **US6 (Phase 8)**: Depends on US3 + US4 (needs agenda items with tsvector and attachments)
- **Polish (Phase 9)**: Depends on all user stories complete

### User Story Dependencies

```
Phase 1 (Setup)
    │
Phase 2 (Foundation)
    │
Phase 3 (US1: Governing Bodies)
    │
Phase 4 (US2: Meetings)
    │
Phase 5 (US3: Agenda Items)
    ├──────────────┐
Phase 6 (US4)  Phase 7 (US5)   ← parallel
    │              │
    └──────┬───────┘
           │
Phase 8 (US6: Search)
    │
Phase 9 (Polish)
```

### Within Each User Story

1. Schemas (parallelizable within story)
2. Services (depend on schemas)
3. API routes (depend on services)
4. Route registration (depend on routes)
5. Tests (can parallel after implementation)

### Parallel Opportunities

**Phase 1**: T003, T004, T005, T006, T007, T008 are all independent files — run in parallel
**Phase 2**: T009–T014 are all independent model files — run in parallel; T015–T017 depend on models
**Phase 3**: T018+T019 parallel (schemas), T025–T030 parallel (tests)
**Phase 4**: T035+T036 parallel (tests)
**Phase 5**: T042+T043 parallel (tests)
**Phase 6+7**: US4 and US5 can run as fully parallel stories
**Phase 8**: T062+T063 parallel (tests)

---

## Parallel Example: User Story 1

```bash
# Launch schemas in parallel:
Task: "Create governing body type schemas in src/voter_api/schemas/governing_body_type.py"
Task: "Create governing body schemas in src/voter_api/schemas/governing_body.py"

# After schemas, launch services:
Task: "Create governing body type service in src/voter_api/services/governing_body_type_service.py"
# governing_body_service depends on type_service patterns, so sequential

# After implementation, launch all tests in parallel:
Task: "Unit tests for governing body type schemas"
Task: "Unit tests for governing body schemas"
Task: "Unit tests for governing body type service"
Task: "Unit tests for governing body service"
Task: "Integration tests for governing body types API"
Task: "Integration tests for governing bodies API"
```

---

## Parallel Example: User Stories 4 & 5

```bash
# After US3 completes, launch US4 and US5 simultaneously:

# Developer A (US4 — Attachments):
Task: "Create attachment schemas in src/voter_api/schemas/meeting_attachment.py"
Task: "Create attachment service in src/voter_api/services/meeting_attachment_service.py"
Task: "Create attachments API routes in src/voter_api/api/v1/attachments.py"

# Developer B (US5 — Video Embeds):
Task: "Create video embed schemas in src/voter_api/schemas/meeting_video_embed.py"
Task: "Create video embed service in src/voter_api/services/meeting_video_embed_service.py"
Task: "Create video embeds API routes in src/voter_api/api/v1/video_embeds.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1–3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundation (CRITICAL — blocks all stories)
3. Complete Phase 3: US1 — Governing Bodies
4. Complete Phase 4: US2 — Meetings with Approval
5. Complete Phase 5: US3 — Agenda Items
6. **STOP and VALIDATE**: Core data structure (bodies → meetings → agenda items) is fully functional
7. Deploy/demo if ready — this is the MVP

### Incremental Delivery

1. Setup + Foundation → Infrastructure ready
2. Add US1 → Governing bodies manageable → Testable increment
3. Add US2 → Meetings with approval workflow → Testable increment
4. Add US3 → Agenda items with ordering → **MVP complete**
5. Add US4 + US5 (parallel) → Documents and video → Testable increment
6. Add US6 → Full-text search → **Feature complete**
7. Polish → CLI, contracts, coverage → **Release ready**

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable (after its dependencies)
- Constitution requires: type hints, docstrings, ruff check, 90% test coverage
- Commit after each task or logical group per constitution Principle VIII
- Stop at any checkpoint to validate story independently
- Route ordering: fixed-prefix routes (e.g., `/search`, `/reorder`) BEFORE parameterized routes (`/{id}`)
