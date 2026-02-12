# Requirements Quality Checklist: Static Dataset Publishing

**Purpose**: Validate the completeness, clarity, consistency, and measurability of requirements in the feature specification before implementation
**Created**: 2026-02-12
**Feature**: [spec.md](../spec.md)
**Depth**: Standard
**Audience**: Reviewer (PR / pre-implementation gate)

## Requirement Completeness

- [ ] CHK001 Are error response formats specified for the publish CLI (exit codes, message structure) when uploads fail, config is invalid, or no boundaries exist? [Gap, Spec §FR-010, §FR-011]
- [ ] CHK002 Are logging/observability requirements defined for publish operations beyond CLI progress output (e.g., structured log events for upload success/failure, durations)? [Gap, Spec §FR-010]
- [ ] CHK003 Is the behavior of the discovery endpoint (FR-022) specified when R2 is configured but no manifest has been published yet? [Completeness, Spec §FR-022]
- [ ] CHK004 Are requirements defined for registering the discovery endpoint router in the FastAPI application (how `/api/v1/datasets` is mounted)? [Gap]
- [ ] CHK005 Are requirements specified for the `R2_PREFIX` behavior — how the configurable prefix interacts with the key structure in manifest entries and public URLs? [Completeness, Spec §Assumptions]
- [ ] CHK006 Is the publisher library version string (used in manifest `publisher_version` field) specified — where it comes from and how it's maintained? [Gap, Spec §FR-019]

## Requirement Clarity

- [ ] CHK007 Is "publicly readable" in FR-008 clarified given that R2 does not support per-object ACLs? The requirement says "System MUST set uploaded files as publicly readable" but public access is a bucket-level configuration, not a per-upload action. [Ambiguity, Spec §FR-008]
- [ ] CHK008 Is "same feature structure" in FR-009 defined with an explicit field list (id, geometry, properties.name, properties.boundary_type, etc.) rather than relying on implicit reference to the existing endpoint? [Clarity, Spec §FR-009]
- [ ] CHK009 Is the multipart threshold in FR-014 ("files exceeding 100 MB") consistent with the implementation decision to use a 25 MB TransferConfig threshold? Are these the same concept or different? [Ambiguity, Spec §FR-014]
- [ ] CHK010 Is "under 5 minutes" in SC-001 defined with conditions — wall-clock time, expected network bandwidth, dataset size range, hardware baseline? [Clarity, Spec §SC-001]
- [ ] CHK011 Is "clear error message" in the edge cases section quantified — what information must an error include (e.g., endpoint URL, HTTP status, bucket name)? [Clarity, Spec §Edge Cases]
- [ ] CHK012 Does FR-022 specify the HTTP response behavior when R2 is not configured — should the discovery endpoint return an empty response, a 503, or omit itself from routing entirely? [Ambiguity, Spec §FR-022]

## Requirement Consistency

- [ ] CHK013 Does FR-008 ("MUST set uploaded files as publicly readable") align with Research Decision 5 ("R2 does not support per-object ACLs; public access is bucket-level only")? The spec requirement cannot be satisfied as written on R2. [Conflict, Spec §FR-008]
- [ ] CHK014 Are the redirect lookup rules in data-model.md §Redirect Lookup Rules consistent with FR-015 through FR-018? Do all five rules map to a corresponding FR? [Consistency, Spec §FR-015–018]
- [ ] CHK015 Is the combined `all-boundaries` file requirement (FR-003) consistent with the assumption that "the combined file can be removed in a future iteration"? Does the spec need a conditional (generate only if below a size threshold)? [Consistency, Spec §FR-003, §Assumptions]
- [ ] CHK016 Are the filter semantics in US2 (county/source scope which types to regenerate, not what data goes in them) consistent with the redirect behavior in US4 (county/source filters always fall back to DB)? [Consistency, Spec §US2, §US4]

## Acceptance Criteria Quality

- [ ] CHK017 Is US3 acceptance scenario 3 ("the system shows the last-published timestamp, alerting the admin to republish") objectively measurable? The parenthetical describes an expected inference, not a testable system behavior. [Measurability, Spec §US3]
- [ ] CHK018 Is SC-003 ("identical feature structures") defined with a measurable comparison method — field-by-field schema match, JSON structural equivalence, or byte-level identity? [Measurability, Spec §SC-003]
- [ ] CHK019 Are US1 acceptance scenarios missing a scenario for partial boundary type availability (e.g., boundaries exist for only 2 of 31 types)? [Acceptance Criteria, Spec §US1]
- [ ] CHK020 Is there an acceptance scenario for the discovery endpoint returning data after a publish — specifically, that the dataset list reflects the most recent publish within 5 minutes? [Gap, Spec §FR-022]

## Scenario Coverage

- [ ] CHK021 Are requirements defined for the API redirect when mixed filters are provided (e.g., `?boundary_type=congressional&county=Fulton`) — does boundary_type match trigger redirect, or does the presence of county force DB fallback? [Coverage, Spec §FR-015–017]
- [ ] CHK022 Is a scenario defined for the discovery endpoint when the manifest cache is stale and R2 is temporarily unreachable? Should it return the stale cached data or an error? [Coverage, Gap]
- [ ] CHK023 Are requirements defined for what happens when a new boundary type is added to the database after a previous full publish — does `publish datasets` generate a file for the new type and update the manifest? [Coverage, Gap]
- [ ] CHK024 Is there a scenario for publishing when the temp directory has insufficient disk space to generate GeoJSON files locally before upload? [Coverage, Gap]

## Edge Case Coverage

- [ ] CHK025 Is the manifest corruption scenario addressed — what happens when `manifest.json` on R2 contains invalid JSON? Does the API fall back to DB, and does the CLI report the error? [Edge Case, Gap]
- [ ] CHK026 Is the concurrent publish edge case ("last-write-wins is acceptable") specific enough — is a warning or log message required when a publish detects an existing manifest with a newer timestamp? [Clarity, Spec §Edge Cases]
- [ ] CHK027 Are requirements defined for boundary data with extremely large geometries (e.g., a single MultiPolygon with thousands of coordinates) that could cause memory issues during GeoJSON generation? [Edge Case, Gap]
- [ ] CHK028 Is the stale file detection edge case ("fall back to database serving") implementable as specified? The current design redirects based on manifest — the API has no mechanism to detect that a referenced R2 file was deleted. [Ambiguity, Spec §Edge Cases]

## Non-Functional Requirements

- [ ] CHK029 Are latency requirements defined for the redirect decision in the GeoJSON endpoint — how much additional latency does the manifest cache check add to the request path? [Gap, Non-Functional]
- [ ] CHK030 Are requirements defined for maximum file size of the combined `all-boundaries.geojson` file? The assumption says "manageable" but provides no upper bound or action if exceeded. [Clarity, Spec §Assumptions]
- [ ] CHK031 Are retry/backoff requirements specified for the manifest cache refresh when R2 is temporarily unreachable? Should the API retry, serve stale, or skip the check? [Gap, Non-Functional]

## Dependencies & Assumptions

- [ ] CHK032 Is the boto3 checksum workaround (Research Decision 2) documented as a fragile dependency — what happens if a future boto3 version changes the config parameter names? [Assumption]
- [ ] CHK033 Is the assumption "boundary data is already imported" validated with a spec-level precondition, or could an admin accidentally run `publish datasets` before importing? [Assumption, Spec §Assumptions]

## Notes

- Check items off as completed: `[x]`
- Items referencing `[Gap]` indicate missing requirements that may need spec updates
- Items referencing `[Ambiguity]` or `[Conflict]` indicate existing text that needs clarification
- Items referencing `[Assumption]` indicate implicit dependencies that should be made explicit
- Cross-reference with `/speckit.analyze` findings (C1–C3, F1–F3, U1) for related issues
