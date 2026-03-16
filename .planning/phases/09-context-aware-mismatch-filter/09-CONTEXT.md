# Phase 9: Context-Aware Mismatch Filter - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Scope `has_district_mismatch` on `GET /elections/{id}/participation` to the election's own `district_type` by querying `analysis_results.mismatch_details` JSONB instead of the voter's blanket boolean. Also add a context-aware `mismatch_count` to the participation stats endpoint. No new DB columns or migrations.

</domain>

<decisions>
## Implementation Decisions

### Filter Semantics
- **Exact type match only**: When `has_district_mismatch=true` is passed on a `state_senate` election, only match voters whose `mismatch_details` JSONB contains `boundary_type == "state_senate"`. No type family grouping.
- **Hybrid approach for unanalyzed voters**: Check existing `analysis_results` JSONB. Voters without analysis data are excluded from mismatch filtering (both `=true` and `=false`) and flagged as unanalyzed in the response.
- **Null district_type returns 422**: If `election.district_type` is NULL and `has_district_mismatch` is specified, return a 422 validation error explaining context-aware filtering is unavailable for this election.
- **Validate district_type against known set**: Check that `election.district_type` is in `BOUNDARY_TYPE_TO_VOTER_FIELD` keys before querying. Return 422 if unknown type.

### Backward Compatibility
- **Silent switch on participation endpoint**: Replace blanket `Voter.has_district_mismatch` filter logic with context-aware JSONB lookup on the participation endpoint. Same parameter name, smarter behavior.
- **Voters list unchanged**: `GET /voters` keeps using the blanket `Voter.has_district_mismatch` flag — it has no election context.
- **Default path unchanged**: When `has_district_mismatch` is omitted (not specified), the participation endpoint continues using `Voter.has_district_mismatch` for the response field. The expensive JSONB JOIN only happens when the filter is actively used.

### Response Enrichment
- **Nullable boolean for unanalyzed indicator**: `has_district_mismatch` stays `bool | null` on `ElectionParticipationRecord`. When null, it means "no analysis data available." True/false mean context-aware result.
- **Add `mismatch_district_type` to response metadata**: Include the district_type used for the mismatch check in the response metadata (alongside pagination). Helpful for debugging.
- **No mismatch details in response**: Per REQUIREMENTS.md out-of-scope decision — mismatch details are not exposed in the participation response.

### Stats Enrichment
- **Add context-aware `mismatch_count` to stats**: Include in the `ParticipationStatsResponse`. Reuses the same JSONB query logic. Included in Phase 9 scope since the JOIN logic is already being built.

### Claude's Discretion
- Exact JSONB query approach (PostgreSQL `jsonb_array_elements` vs `@>` containment operator vs lateral join)
- Whether to extract the mismatch JSONB check into a reusable utility function in the service layer
- Index strategy for the JSONB query if needed for performance
- Error message wording for 422 responses

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Mismatch data model
- `src/voter_api/models/analysis_result.py` — `AnalysisResult` model with `mismatch_details` JSONB column (list of `{boundary_type, registered, determined}` dicts)
- `src/voter_api/lib/analyzer/comparator.py` — `compare_boundaries()` produces the `mismatch_details` structure; `BOUNDARY_TYPE_TO_VOTER_FIELD` defines valid boundary types
- `specs/001-voter-data-management/data-model.md` — Database schema design including analysis_results table

### Participation endpoint (modify)
- `src/voter_api/api/v1/voter_history.py` — Route handlers for participation endpoints; `list_election_participants` at line 90, `get_election_participation_stats` at line 185
- `src/voter_api/services/voter_history_service.py` — Service layer; `_apply_voter_filters` at line 610 is where `Voter.has_district_mismatch` is currently applied (lines 655-657); `get_participation_stats` at line 695
- `src/voter_api/schemas/voter_history.py` — `ParticipationFilters`, `ElectionParticipationRecord`, `ParticipationStatsResponse` schemas

### Election model
- `src/voter_api/models/election.py` — `Election.district_type` field (line 72)

### Requirements
- `.planning/REQUIREMENTS.md` — MISMATCH-01 requirement; out-of-scope section explicitly excludes exposing mismatch details in participation response

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BOUNDARY_TYPE_TO_VOTER_FIELD` dict in `comparator.py`: Defines valid boundary types — use for district_type validation
- `_apply_voter_filters()` in `voter_history_service.py`: Current filter application point — modify to swap blanket flag for JSONB query
- `_get_election_or_raise()`: Already loads election with boundary via selectinload — has `district_type` available

### Established Patterns
- **Voter JOIN path**: `list_election_participants` already has a JOIN path vs default path split based on `voter_filters_active`. Context-aware mismatch will activate the JOIN path (or extend it with analysis_results)
- **Filter bundle pattern**: `ParticipationFilters` Pydantic model bundles all filter params — no schema change needed for the filter itself
- **JSONB usage**: `analysis_results.mismatch_details` is already typed as `JSONB` with `list | None`

### Integration Points
- `voter_history_service.py:655-657`: Replace `Voter.has_district_mismatch == filters.has_district_mismatch` with JSONB lookup against `AnalysisResult.mismatch_details`
- `voter_history_service.py:552-563`: `voter_filters_active` detection — `has_district_mismatch` currently triggers voter JOIN; will now trigger analysis_results JOIN instead/additionally
- `ParticipationStatsResponse`: Add `mismatch_count: int | None` field
- `PaginatedElectionParticipationResponse`: Add `mismatch_district_type: str | None` metadata field

</code_context>

<specifics>
## Specific Ideas

- "Just in time analyze" — user's instinct was to analyze on-the-fly, which led to the hybrid approach: check existing JSONB data, exclude unanalyzed voters, flag them with null
- Both `=true` and `=false` should exclude unanalyzed voters — strict interpretation for both directions

</specifics>

<deferred>
## Deferred Ideas

- Context-aware mismatch on the voters list endpoint (`GET /voters`) — would need an election_id parameter to provide context
- Mismatch details exposed in participation response — explicitly out of scope per REQUIREMENTS.md
- New mismatch aggregation/stats beyond simple count — out of scope per REQUIREMENTS.md

</deferred>

---

*Phase: 09-context-aware-mismatch-filter*
*Context gathered: 2026-03-16*
