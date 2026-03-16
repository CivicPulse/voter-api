# Requirements: CivPulse Voter API

**Defined:** 2026-03-16
**Core Value:** Georgia election and voter data is accurately maintained and queryable — from raw SOS sources through human-reviewable pipelines into a searchable, filterable API that powers civic engagement tools.

## v1.1 Requirements

Requirements for Election Search milestone. Each maps to roadmap phases.

### Discovery

- [x] **DISC-01**: API consumer can discover which filter parameters are currently supported via a capabilities endpoint (`GET /elections/capabilities`)
- [x] **DISC-02**: API consumer can fetch valid values for race category, county, and election date dropdown filters via a filter-options endpoint (`GET /elections/filter-options`)

### Search

- [x] **SRCH-01**: User can search elections by free text across name and district fields (case-insensitive, partial match, min 2 characters, max 200)
- [x] **SRCH-02**: Special characters in search input are treated as literal text (ILIKE wildcards `%` and `_` escaped)

### Filtering

- [x] **FILT-01**: User can filter elections by race category (federal, state_senate, state_house, local) mapped to existing `district_type` values via a constant mapping dict
- [x] **FILT-02**: User can filter elections by county name matching the `eligible_county` field (case-insensitive exact match)
- [x] **FILT-03**: User can filter elections by exact date (`election_date` param), complementing existing `date_from`/`date_to` range filters (exact date takes precedence if both provided)
- [x] **FILT-04**: All new filters combine with existing filters using AND logic, preserving current filter behavior

### Integration

- [x] **INTG-01**: New endpoints (`/capabilities`, `/filter-options`) use correct FastAPI route ordering (registered before `/{election_id}` catch-all)
- [x] **INTG-02**: Existing election list endpoint behavior is unchanged for current consumers (backward compatible, no breaking changes to `district` partial match)
- [ ] **INTG-03**: E2E tests cover all new endpoints and filter parameters with seed data that exercises `eligible_county` and `district_type`

## Future Requirements

Deferred to backlog. Tracked but not in current roadmap.

### Geographic Enhancement

- **GEO-01**: County filter includes statewide elections (requires boundary-based geospatial logic)
- **GEO-02**: Filter options are scoped by current filter selections (context-sensitive dropdowns)

### Search Enhancement

- **SRCH-03**: Full-text search upgrade via PostgreSQL `tsvector`/`pg_trgm` if ILIKE performance degrades at scale

## Out of Scope

| Feature | Reason |
|---------|--------|
| New database columns or migrations | All features use existing indexed columns (`district_type`, `eligible_county`, `election_date`, `name`, `district`) |
| Full-text search (tsvector) | Premature optimization at ~34 elections; ILIKE sufficient |
| Statewide-in-county inclusion | Geospatial boundary logic adds significant complexity; deferred to backlog |
| Scoped filter options | Combinatorial query complexity; unscoped values acceptable for current dataset size |
| New dependencies or libraries | Zero new deps; everything achievable with existing stack |
| `district` exact match | Breaking change to existing partial match behavior; frontend spec deviation documented |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DISC-01 | Phase 6 | Complete |
| DISC-02 | Phase 8 | Complete |
| SRCH-01 | Phase 7 | Complete |
| SRCH-02 | Phase 7 | Complete |
| FILT-01 | Phase 7 | Complete |
| FILT-02 | Phase 7 | Complete |
| FILT-03 | Phase 7 | Complete |
| FILT-04 | Phase 7 | Complete |
| INTG-01 | Phase 6 | Complete |
| INTG-02 | Phase 7 | Complete |
| INTG-03 | Phase 8 | Pending |

**Coverage:**
- v1.1 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0

---
*Requirements defined: 2026-03-16*
*Last updated: 2026-03-16 after roadmap creation*
