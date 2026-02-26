# Feature Specification: Batch Boundary Check

**Feature Branch**: `013-batch-boundary-check`
**Created**: 2026-02-26
**Status**: Draft
**Input**: User description: "Batch boundary check endpoint — compare all geocoded locations against district assignments"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare All Provider Locations for a Voter (Priority: P1)

An administrator is investigating a district mismatch for a specific voter. Multiple geocoding providers have returned different coordinates for the voter's address, and the admin needs to know which provider's location actually falls within the voter's registered districts. The admin requests a batch comparison that checks every geocoded location on file for that voter against all of the voter's expected district boundaries, and receives a single response showing the inside/outside result for each provider+district combination.

**Why this priority**: This is the core use case. Without this, admins must manually verify each provider coordinate against each district boundary one at a time — the problem this feature directly solves.

**Independent Test**: Can be fully tested by submitting a voter ID with multiple geocoded locations on file and verifying the response lists every provider and each district result correctly.

**Acceptance Scenarios**:

1. **Given** a voter with geocoded locations from two or more providers and two or more district assignments, **When** an admin requests the batch boundary check for that voter, **Then** the response lists every geocoded location by provider and shows, for each district assignment, whether that location falls inside or outside that district boundary.

2. **Given** a voter with geocoded locations where one provider's coordinates fall inside all expected districts and another provider's coordinates fall outside at least one district, **When** an admin requests the batch boundary check, **Then** the response clearly distinguishes the two providers' results so the admin can identify the more accurate one.

3. **Given** a non-admin user (analyst or viewer), **When** they attempt to request the batch boundary check for any voter, **Then** the system returns an authorization error and does not perform the comparison.

---

### User Story 2 - Handle Voter with No Geocoded Locations (Priority: P2)

An administrator requests the batch boundary check for a voter who has never been geocoded (or all geocoding attempts failed). The system must respond gracefully rather than returning an error.

**Why this priority**: Edge case coverage that prevents confusing error responses and guides admins toward the correct remediation (geocode the voter first).

**Independent Test**: Can be fully tested by submitting a voter ID with no geocoded locations and confirming the response indicates no locations are available for comparison.

**Acceptance Scenarios**:

1. **Given** a voter with no geocoded locations on file, **When** an admin requests the batch boundary check, **Then** the system returns a successful response indicating zero locations were compared, rather than an error.

---

### User Story 3 - Handle Voter with No District Assignments (Priority: P3)

An administrator requests the batch boundary check for a voter who has no registered district assignments on file. The system must respond gracefully.

**Why this priority**: Ensures robustness in data-sparse scenarios without breaking the admin workflow.

**Independent Test**: Can be fully tested by submitting a voter ID with geocoded locations but no district assignments and verifying the response indicates no districts were checked.

**Acceptance Scenarios**:

1. **Given** a voter with geocoded locations but no district assignments on file, **When** an admin requests the batch boundary check, **Then** the system returns a successful response listing all locations with an empty district results set, rather than an error.

---

### Edge Cases

- What happens when a voter ID does not exist? The system returns a clear not-found error.
- What happens when a geocoded location's coordinates are outside the coverage area of all loaded boundaries? Each affected district result is returned as "outside" (the spatial check returns false, not an error).
- What happens when a boundary geometry for a district assignment is not loaded in the system? The district entry is included in the response but flagged as having no boundary data available.
- What happens when a voter has dozens of district assignments and many provider locations? The system completes the full cross-product check without timing out under normal data volumes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Only users with the administrator role MUST be permitted to trigger the batch boundary check for any voter.
- **FR-002**: The system MUST accept a single voter identifier as the input for the comparison.
- **FR-003**: The system MUST retrieve the most recent successful geocoded location per provider for the specified voter — one location per provider, not historical retries or failed attempts.
- **FR-004**: The system MUST retrieve all expected district assignments registered for the specified voter (e.g., county, state house, state senate, congressional, precinct).
- **FR-005**: For each geocoded location, the system MUST evaluate whether that location's coordinates fall inside or outside each district boundary using the existing spatial geometry data — no new geometry must be stored to satisfy this check.
- **FR-006**: The response MUST identify each geocoded location by the provider that produced it, along with the location's coordinates and geocoding confidence or quality metadata if available.
- **FR-007**: The response MUST be structured by district — each district entry lists the district type, district identifier, and for each geocoded location, the provider name and whether that location falls inside or outside that district.
- **FR-012**: The response MUST include a per-provider summary section listing each provider's name, coordinates, and the number of districts where its location fell inside versus the total districts checked (e.g., "3 of 5 districts matched").
- **FR-008**: If a district assignment references a boundary that has no geometry loaded in the system, the response MUST indicate that the district check was skipped due to missing boundary data rather than returning an error.
- **FR-009**: If the specified voter has no geocoded locations, the system MUST return a successful response with an empty locations list.
- **FR-010**: If the specified voter does not exist, the system MUST return a not-found error.
- **FR-011**: The system MUST use existing spatial indexes for all point-in-polygon evaluations; no full-table geometry scans are permitted.

### Key Entities

- **Voter**: The subject of the comparison. Identified by a unique system ID. Has one or more district assignments registered at the time of voter registration.
- **Geocoded Location**: The most recent successful coordinate pair (latitude/longitude) produced by a specific geocoding provider for the voter's registered address. One location per provider is used in the comparison; historical retries and failed attempts are excluded.
- **District Assignment**: A record linking a voter to an expected district (e.g., "State House District 42"). Defined by district type and identifier.
- **Boundary**: An existing geographic polygon record in the system representing a district's physical area. Matched to a district assignment by type and identifier.
- **Boundary Check Result**: A computed (not stored) determination of whether a given geocoded location's coordinates fall inside a given district boundary.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator can retrieve the full boundary check comparison for a voter with multiple geocoded locations and multiple district assignments in a single request, without needing to issue separate requests per provider or per district.
- **SC-002**: The comparison result for a voter with up to 10 geocoded locations and up to 10 district assignments is returned in under 2 seconds under normal system load.
- **SC-003**: The response includes a per-provider summary (districts matched out of total checked) so an administrator can identify at a glance which provider's location is most consistent with all expected district assignments, without reading the full district-level detail.
- **SC-004**: Non-admin users receive an authorization error on every attempt to access this endpoint, with no partial data returned.
- **SC-005**: All edge cases (no locations, no districts, missing boundary geometry, voter not found) produce a clear, informative response rather than an unhandled error.

## Clarifications

### Session 2026-02-26

- Q: How should the response be grouped — by provider or by district? → A: Group by district — each entry is a district with a list of provider results (inside/outside per provider).
- Q: Which geocoded locations should be included in the comparison? → A: Most recent successful geocode per provider only.
- Q: Should the response include a per-provider summary alongside the district-grouped detail? → A: Yes — include a summary showing each provider and its district match count (e.g., 3/5 matched).

## Assumptions

- District assignments for a voter are already stored in the system and do not need to be computed as part of this feature.
- Geocoded locations from all providers are already stored and associated with the voter record; this feature performs no new geocoding.
- "Inside" means the geocoded coordinate is spatially contained within the district boundary polygon using the same point-in-polygon method used elsewhere in the system.
- The endpoint is read-only — it does not modify any voter data, geocoded locations, or district assignments.
- Boundary geometry data is loaded separately (via the boundary loader); this feature only reads it.
- A voter's district assignments are matched to boundary records by district type and district identifier; the matching logic follows the same convention already used by the analysis library.
