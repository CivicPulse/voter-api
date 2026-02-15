# Feature Specification: Election Result Tracking

**Feature Branch**: `004-election-tracking`
**Created**: 2026-02-14
**Status**: Draft
**Input**: User description: "Election tracking system for GA races with live result ingestion from Secretary of State data feeds, JSON and GeoJSON output, and admin management of elections."

## Clarifications

### Session 2026-02-14

- Q: What cache TTL should Cloudflare use for election result responses? → A: 60 seconds — balances data freshness with server protection.
- Q: Should the system actively invalidate CDN cache after ingesting new results? → A: No — rely on TTL expiration only; no active Cloudflare API purging.
- Q: Should admins be able to trigger an immediate manual refresh? → A: Yes — admin-only endpoint to force-fetch results for a specific election on demand.
- Q: How should the last-refresh timestamp be exposed for client-side freshness awareness? → A: In the response body as a `last_refreshed_at` field in JSON/GeoJSON payloads.
- Q: Should finalized elections use a longer cache TTL? → A: Yes — 24 hours for finalized elections, 60 seconds for active elections.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Live Election Results (Priority: P1)

A public user visits the web interface on election night to see the current status of the GA Senate District 18 special election. They want to see which candidates are running, how many votes each has received, what percentage of precincts have reported, and vote breakdowns by voting method (Election Day, Advance Voting, Absentee by Mail, Provisional). The data updates automatically as new precinct results are reported to the Secretary of State.

**Why this priority**: Displaying live election results is the core purpose of the feature. Without result retrieval and display, no other functionality delivers value.

**Independent Test**: Can be fully tested by creating an election, ingesting results from the SoS data feed, and retrieving the results via the API. Delivers immediate value by making election data accessible.

**Acceptance Scenarios**:

1. **Given** an election exists with results ingested, **When** a user requests election results, **Then** the system returns candidate names, vote counts, precinct reporting status, and vote method breakdowns.
2. **Given** an election has partial results (some precincts not yet reporting), **When** a user requests results, **Then** the response clearly indicates how many precincts have reported out of the total participating.
3. **Given** results have been refreshed since the user's last request, **When** the user requests results again, **Then** the system returns the latest data with an updated timestamp.
4. **Given** an election exists, **When** a user requests results broken down by county, **Then** the system returns county-level results with per-county precinct reporting status and candidate vote counts.

---

### User Story 2 - View Election Results on a Map (Priority: P2)

A user wants to see election results displayed geographically. They request results in GeoJSON format so the web frontend can render a map showing results by county or precinct, with geometry data that enables choropleth or proportional visualizations.

**Why this priority**: Geographic visualization is a key differentiator for CivicPulse and builds on the platform's existing geospatial capabilities. However, it depends on result data being available first (P1).

**Independent Test**: Can be tested by requesting GeoJSON output for an election with ingested results and verifying the response contains valid GeoJSON FeatureCollections with result properties attached to county boundary geometries.

**Acceptance Scenarios**:

1. **Given** an election with results and county boundaries already loaded in the system, **When** a user requests GeoJSON results for that election, **Then** the system returns a GeoJSON FeatureCollection where each Feature contains a county boundary geometry and result properties (candidate votes, precinct reporting percentage).
2. **Given** an election where some counties have no results yet, **When** a user requests GeoJSON, **Then** counties without results are still included with null/zero result values so the map renders completely.
3. **Given** a request for GeoJSON results, **When** the response is loaded in a standard GeoJSON viewer, **Then** it renders a valid map without errors.

---

### User Story 3 - Automatic Result Refresh (Priority: P2)

The system periodically fetches the latest election results from the Georgia Secretary of State data feed and updates the stored results. On election night, results change frequently as precincts report in, and the system must keep its data current without manual intervention.

**Why this priority**: Automatic refresh is essential for election night usage. Manual data updates would make the system impractical during a live election. Tied with P2 map display as both are critical for the election night experience.

**Independent Test**: Can be tested by configuring an election with a data source URL, triggering a refresh, and verifying the stored results match the source data. Can also verify that stale data is replaced by newer data.

**Acceptance Scenarios**:

1. **Given** an election with a configured data source URL, **When** a refresh cycle runs, **Then** the system fetches the latest data from the source and updates stored results.
2. **Given** the data source is temporarily unavailable, **When** a refresh cycle runs, **Then** the system retains the most recent successful results and logs the failure without crashing.
3. **Given** multiple elections are active on the same night, **When** a refresh cycle runs, **Then** all active elections have their results updated.
4. **Given** an election has been marked as finalized/certified, **When** a refresh cycle runs, **Then** the system skips that election (no unnecessary fetches).

---

### User Story 4 - Admin Creates and Manages Elections (Priority: P3)

An administrator creates a new election entry in the system, specifying the election name, date, type, district, and the URL of the Secretary of State data feed. They can later update these details (e.g., correct a data source URL) or mark an election as finalized once results are certified.

**Why this priority**: Admin management is necessary for ongoing operation but can be handled via direct database operations initially. The API endpoints formalize and secure this workflow.

**Independent Test**: Can be tested by authenticating as an admin, creating an election, updating its details, and verifying the changes persist. Non-admin users should be denied access.

**Acceptance Scenarios**:

1. **Given** an authenticated admin user, **When** they create a new election with name, date, type, district, and data source URL, **Then** the election is created and a unique identifier is returned.
2. **Given** an authenticated admin user, **When** they update an existing election's data source URL, **Then** the next refresh cycle uses the new URL.
3. **Given** an authenticated admin user, **When** they mark an election as finalized, **Then** the system stops automatic refreshes for that election.
4. **Given** an authenticated user without admin privileges, **When** they attempt to create or modify an election, **Then** the system denies the request.
5. **Given** an admin creates an election with the same name and date as an existing one, **When** the request is submitted, **Then** the system rejects it with a clear duplicate error.
6. **Given** an authenticated admin user, **When** they trigger a manual refresh for an election, **Then** the system immediately fetches the latest data from the configured source and updates stored results.

---

### User Story 5 - List and Filter Elections (Priority: P3)

A user browses available elections to find the one they are interested in. They can filter by date, status (active, finalized), election type, or district, and the list returns summary information including whether results are available.

**Why this priority**: Supports discovery when multiple elections exist but is not critical for the initial single-election use case.

**Independent Test**: Can be tested by creating multiple elections with different dates and types, then filtering and verifying correct results are returned.

**Acceptance Scenarios**:

1. **Given** multiple elections exist in the system, **When** a user lists elections without filters, **Then** all elections are returned with summary information (name, date, type, status, precinct reporting percentage).
2. **Given** elections exist with different statuses, **When** a user filters by status "active", **Then** only active elections are returned.
3. **Given** elections exist across different dates, **When** a user filters by date range, **Then** only elections within that range are returned.

---

### Edge Cases

- What happens when the data source URL returns malformed or unexpected JSON? The system must validate the response structure before processing and reject invalid data while preserving existing results.
- What happens when a race has zero precincts reporting? The system should represent this as 0/N precincts reporting with all candidate vote counts at zero.
- What happens when the SoS adds or removes candidates between refreshes? The system replaces the full result set on each refresh (JSONB upsert). If the SoS removes a candidate, their data is no longer in the current snapshot. Historical snapshots are not retained.
- What happens when the same election night has 10+ concurrent races? The refresh mechanism must handle multiple simultaneous data source fetches without timeouts or resource exhaustion.
- What happens when county names in election results don't match county names in the boundary table? The system must use a reliable matching strategy (e.g., normalized names or FIPS codes) to join election results with geographic boundaries.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST store election metadata including name, date, election type, district/race identifier, data source URL, and status (active, finalized).
- **FR-002**: System MUST ingest election result data from the Georgia Secretary of State JSON feed format, parsing candidates, vote counts, precinct reporting status, and vote method breakdowns.
- **FR-003**: System MUST store election results at both the statewide aggregate level and the county level, preserving the hierarchical structure of the source data.
- **FR-004**: System MUST store per-candidate vote breakdowns by voting method (Election Day, Advance Voting, Absentee by Mail, Provisional).
- **FR-005**: System MUST periodically refresh results for all active (non-finalized) elections from their configured data source URLs.
- **FR-006**: System MUST provide election results in JSON format that preserves the structure and fidelity of the source data (candidates, votes, precinct reporting counts, vote method breakdowns).
- **FR-007**: System MUST provide election results in GeoJSON format that joins county-level results with county boundary geometries for map rendering.
- **FR-008**: System MUST allow authenticated admin users to create new elections with required metadata fields.
- **FR-009**: System MUST allow authenticated admin users to update election metadata (name, data source URL, status) for existing elections.
- **FR-010**: System MUST prevent non-admin users from creating or modifying elections.
- **FR-011**: System MUST support multiple simultaneous active elections (same election night scenario).
- **FR-012**: System MUST track the timestamp of the last successful data refresh for each election and include it as a `last_refreshed_at` field in all result response payloads (JSON and GeoJSON) so the frontend can display data freshness to users.
- **FR-013**: System MUST gracefully handle data source failures during refresh (log errors, retain last good data, continue refreshing other elections).
- **FR-014**: System MUST validate incoming data from the SoS feed against expected structure before updating stored results.
- **FR-015**: System MUST support listing elections with filtering by status, date range, election type, and district.
- **FR-016**: System MUST include precinct reporting progress (precincts reporting vs. precincts participating) in result responses at both statewide and county levels.
- **FR-017**: System MUST set cache control headers on election result responses with a maximum age that varies by election status: 60 seconds for active elections (balancing freshness with server protection) and 24 hours for finalized elections (results no longer change).
- **FR-018**: System MUST NOT actively purge CDN cache after data refreshes; cache freshness is governed solely by TTL expiration.
- **FR-019**: System MUST allow authenticated admin users to trigger an immediate manual refresh of results for a specific election, bypassing the periodic schedule.

### Key Entities

- **Election**: Represents a single race/contest. Contains metadata such as name, date, election type (e.g., special, general, primary, runoff), district identifier, data source URL, status (active/finalized), and refresh timestamps. An election is the top-level organizing entity.
- **Election Result (Statewide)**: The aggregate result for an election across all participating jurisdictions. Contains total precinct counts (participating, reporting) and links to candidate results.
- **Election Result (County)**: Results for a single county within an election. Contains county-level precinct counts and links to candidate results for that county. Relates to existing county boundary data for GeoJSON output.
- **Candidate Result**: A single candidate's vote tally within a result context (statewide or county). Contains candidate name, political party, vote count, ballot order, and vote method breakdown (Election Day, Advance Voting, Absentee by Mail, Provisional).

## Assumptions

- The Georgia Secretary of State JSON feed format (as seen in the `export-Feb1726StateSenateDistrict18.json` endpoint) is the standard format for all races and will remain stable for the duration of this feature's use.
- The existing `boundaries` table already contains county-level boundary geometries that can be joined with election result county names to produce GeoJSON output.
- The system's existing JWT authentication and role-based access control (admin/analyst/viewer roles) will be used for admin election management endpoints.
- Refresh intervals will be configurable but a reasonable default (e.g., every 2 minutes during active election periods) will be assumed.
- Precinct-level result granularity (individual precinct results within counties) is not required for the initial release; county-level is the finest geographic granularity needed for map display. Precinct reporting _counts_ are tracked but individual precinct results are not stored.
- The data source provides a single JSON file per race/contest. If future races use a different URL pattern or format, the admin will configure the appropriate URL per election.
- The API is hosted behind Cloudflare, which caches responses at the edge. Cache control headers emitted by the API govern Cloudflare's caching behavior.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view complete election results (candidates, votes, precinct reporting status, vote method breakdowns) within 2 seconds of requesting them.
- **SC-002**: Election results are automatically refreshed from the source within 5 minutes of new data becoming available at the SoS feed during an active election.
- **SC-003**: GeoJSON election result responses render correctly as a county-level map in a standard GeoJSON viewer without additional data transformation.
- **SC-004**: The system supports at least 10 concurrent active elections being refreshed simultaneously without degradation.
- **SC-005**: Admin users can create a new election and have it begin ingesting results within 5 minutes of setup.
- **SC-006**: 100% of data source failures are logged and result in graceful degradation (last good data preserved) rather than data loss or system errors.
- **SC-007**: Non-admin users are unable to create or modify elections (0% unauthorized access).
