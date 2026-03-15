# Requirements: Better Imports

**Defined:** 2026-03-13
**Core Value:** Election and candidate data flows reliably from raw SOS sources into the database through a pipeline where every intermediate step is human-reviewable, version-controlled, and reproducible.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Format & Schema

- [x] **FMT-01**: Enhanced markdown format spec includes district linkage fields (boundary_type + district_identifier) for every contest
- [x] **FMT-02**: Enhanced markdown format spec includes election metadata (early voting start/end, registration deadline, absentee deadline) per election
- [x] **FMT-03**: Enhanced markdown format spec includes candidate details (party, photo URL, bio, contact info, external IDs) per candidate
- [x] **FMT-04**: JSONL schema for elections mirrors the Election DB model with all required and optional fields documented
- [x] **FMT-05**: JSONL schema for candidates mirrors the Candidate DB model with all required and optional fields documented
- [x] **FMT-06**: JSONL files include a `schema_version` field for forward compatibility

### Converter (MD → JSONL)

- [x] **CNV-01**: Deterministic markdown parser using mistune AST converts election markdown files to JSONL without AI
- [x] **CNV-02**: Parsed output is validated against Pydantic models matching the JSONL schema before writing
- [x] **CNV-03**: Batch conversion processes an entire election directory (all contests, all counties) in a single command
- [x] **CNV-04**: Conversion produces a validation report summarizing what parsed successfully, what failed, and what fields are missing

### Import Pipeline

- [x] **IMP-01**: CLI command `voter-api import elections <file.jsonl>` loads election records into the database
- [x] **IMP-02**: CLI command `voter-api import candidates <file.jsonl>` loads candidate records into the database
- [x] **IMP-03**: Import is idempotent — re-importing the same JSONL file produces no duplicate records or data changes
- [x] **IMP-04**: Import supports dry-run mode that validates the JSONL against the database without writing any records

### Claude Code Skills

- [x] **SKL-01**: Skill processes a GA SOS qualified candidates CSV into per-election structured markdown files following the enhanced format spec
- [x] **SKL-02**: Deterministic Python normalizer post-processes AI-generated markdown to enforce title case, URL normalization, occupation formatting, and field consistency
- [x] **SKL-03**: Skill processes a GA SOS election calendar PDF into election metadata (dates, deadlines) in the markdown format
- [x] **SKL-04**: Skill enriches candidate markdown with bios, photo URLs, and contact info from web research

### Pipeline Demo

- [ ] **DEM-01**: End-to-end demo: May 19 SOS CSV → run skill → review markdown → convert to JSONL → import → query elections and candidates via API

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Infrastructure

- **INF-01**: Procrastinate PostgreSQL job queue replaces InProcessTaskRunner for import processing
- **INF-02**: R2 signed URL upload endpoint for large file imports (voter registration, voter history)
- **INF-03**: API import endpoints (`POST /api/v1/imports/elections`, `POST /api/v1/imports/candidates`) wrap CLI in HTTP
- **INF-04**: Import progress reporting via WebSocket or polling endpoint

### Extended Import

- **EXT-01**: JSONL schema and import pipeline for voter registration data
- **EXT-02**: JSONL schema and import pipeline for voter history data
- **EXT-03**: JSONL schema and import pipeline for boundary/shapefile data
- **EXT-04**: Round-trip validation (MD → JSONL → DB → export matches original)

### Data Quality

- **DQ-01**: Historical election backfill (2024-2025) to resolve orphaned voter history
- **DQ-02**: Automated SOS format change detection and alerting

## Out of Scope

| Feature | Reason |
|---------|--------|
| Frontend/UI for reviewing markdown | Git diffs serve this purpose; not worth building UI |
| Real-time SOS feed integration | Existing auto-refresh covers this; import pipeline is for batch data |
| Multi-state support | Georgia only for this milestone; architecture should not preclude it |
| Voter registration import | Future milestone after election/candidate pipeline is proven |
| Voter history import | Future milestone; existing ZIP import still works |
| Boundary import via JSONL | Future milestone; existing shapefile import still works |
| Direct SOS → DB import (skip markdown) | Defeats the human-review purpose of the pipeline |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FMT-01 | Phase 1 | Complete |
| FMT-02 | Phase 1 | Complete |
| FMT-03 | Phase 1 | Complete |
| FMT-04 | Phase 1 | Complete |
| FMT-05 | Phase 1 | Complete |
| FMT-06 | Phase 1 | Complete |
| CNV-01 | Phase 2 | Complete |
| CNV-02 | Phase 2 | Complete |
| CNV-03 | Phase 2 | Complete |
| CNV-04 | Phase 2 | Complete |
| IMP-01 | Phase 2 | Complete |
| IMP-02 | Phase 2 | Complete |
| IMP-03 | Phase 2 | Complete |
| IMP-04 | Phase 2 | Complete |
| SKL-01 | Phase 3 | Complete |
| SKL-02 | Phase 3 | Complete |
| SKL-03 | Phase 3 | Complete |
| SKL-04 | Phase 3 | Complete |
| DEM-01 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0

---
*Requirements defined: 2026-03-13*
*Last updated: 2026-03-13 after roadmap creation*
