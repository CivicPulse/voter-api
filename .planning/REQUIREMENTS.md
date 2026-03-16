# Requirements: CivPulse Voter API

**Defined:** 2026-03-16
**Core Value:** Georgia election and voter data is accurately maintained and queryable — from raw SOS sources through human-reviewable pipelines into a searchable, filterable API that powers civic engagement tools.

## v1.2 Requirements

Requirements for v1.2 Context-Aware District Mismatch. Each maps to roadmap phases.

### Participation Mismatch

- [ ] **MISMATCH-01**: Participation endpoint `has_district_mismatch=true` only returns voters whose mismatch is on the election's `district_type` (via `analysis_results.mismatch_details` JSONB lookup)

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Infrastructure

- **INFRA-01**: Cloudflare R2 signed URL upload endpoint
- **INFRA-02**: Background job processing via procrastinate or equivalent
- **INFRA-03**: API import endpoints for elections and candidates

### Data Pipeline

- **DATA-01**: JSONL schema and import pipeline for voter registration data
- **DATA-02**: JSONL schema and import pipeline for voter history data
- **DATA-03**: Historical election backfill (2024-2025)

### Search Enhancements

- **SRCH-01**: Statewide election inclusion in county filter (geospatial boundary logic)
- **SRCH-02**: Scoped filter options (context-sensitive dropdown values)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Exposing mismatch details in participation response | Not requested; available via voter detail endpoint |
| New mismatch aggregation/stats | Not requested |
| Changes to denormalized `Voter.has_district_mismatch` flag | Still useful as general flag; participation query adds context-awareness |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MISMATCH-01 | Phase 10 | Pending |

**Coverage:**
- v1.2 requirements: 1 total
- Mapped to phases: 1
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-16*
*Last updated: 2026-03-16 after roadmap creation*
