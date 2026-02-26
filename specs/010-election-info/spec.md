# Feature Specification: Election Information

**Feature Branch**: `010-election-info`
**Created**: 2026-02-25
**Status**: Draft
**Input**: User description: "Extend the election data model to track candidate information (name, bio, photo, party affiliation, links) and election metadata (eligibility requirements, geographic area/district, election purpose, description). Create API endpoints to retrieve election information, candidate lists, and eligibility details. Support storing candidate data independently of SOS results feed to enable forward-looking election information before official results are posted."

## Clarifications

### Session 2026-02-25

- Q: Should candidate party affiliation be required or optional? → A: Optional — party field can be null/empty for nonpartisan races (judicial, school board, water authority, etc.).
- Q: Should the public candidate list include or exclude withdrawn/disqualified candidates by default? → A: Include all by default — all statuses returned, with optional `status` filter parameter. Matches existing API patterns.
- Q: Should the candidate bio field support rich-text formatting or plain text only? → A: Plain text only — no formatting markup; consuming frontends handle display.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse Candidates Before Election Day (Priority: P1)

A voter visits the platform to learn who is running in an upcoming election. They select an election and see a list of all qualified candidates with their names, party affiliations, and brief biographies. They click on a candidate to read more detail including the candidate's website and social media links. This information is available weeks or months before election day, well before any official results exist.

**Why this priority**: The core value proposition of this feature. Voters need to know who is on their ballot before they vote. The Macon-Bibb data report confirms this is the highest-value gap: six candidates are running for Commission District 5 on March 17, 2026, but the API has no way to surface this information until results are published. Forward-looking candidate data is what differentiates an election information platform from a results-only dashboard.

**Independent Test**: Can be fully tested by creating an election, adding candidates with profile data, and retrieving the candidate list via the API. Delivers value even without election metadata enrichment.

**Acceptance Scenarios**:

1. **Given** an upcoming election with three candidates entered, **When** a user requests the candidate list, **Then** they see all three candidates with name, party, and summary bio.
2. **Given** a candidate with a photo URL, website, and social media links, **When** a user views candidate detail, **Then** all profile information is displayed.
3. **Given** an election in the future with no SOS results yet, **When** a user requests the election, **Then** they see the candidate list populated from manually entered data.
4. **Given** a candidate who has withdrawn from the race, **When** a user views the candidate list, **Then** the withdrawn candidate is clearly marked with their status.

---

### User Story 2 - View Election Details and Purpose (Priority: P2)

A voter or civic organization wants to understand what an election is about. They view an election and see a human-readable description of its purpose, geographic scope, eligibility information (who can vote, registration deadline), and key milestone dates (early voting period, absentee request deadline). This context helps voters understand whether an election is relevant to them and what deadlines they face.

**Why this priority**: Election descriptions and milestone dates are the second-most impactful gap. The Macon-Bibb report shows that dates like voter registration deadlines and early voting periods drive voter engagement. Adding context about what the election is for (e.g., "Special election to fill the unexpired term of Seth Clark, resigned, for Macon-Bibb County Commission District 5") transforms raw election records into actionable voter information.

**Independent Test**: Can be tested by creating an election with metadata fields populated and verifying the enriched detail is returned via the API. Delivers value even without candidate data.

**Acceptance Scenarios**:

1. **Given** an election with a description and purpose, **When** a user views election detail, **Then** they see the purpose and description alongside existing fields.
2. **Given** an election with a voter registration deadline set, **When** a user views election detail, **Then** they see the registration deadline prominently.
3. **Given** an election with early voting start and end dates, **When** a user views election detail, **Then** the early voting window is displayed.
4. **Given** an election with no metadata enrichment, **When** a user views election detail, **Then** existing fields are shown and new metadata fields are absent or null (backward compatible).

---

### User Story 3 - Administer Candidate and Election Data (Priority: P2)

An admin user enters candidate information for an upcoming election. They create candidate records with names, party affiliations, bios, photo URLs, and links. They also enrich election records with descriptions, purpose statements, milestone dates, and eligibility information. They can update candidate filing status as qualifying unfolds (e.g., marking a candidate as withdrawn or disqualified).

**Why this priority**: Equal to P2 because enriched voter-facing data depends on admin data entry. The system must be manageable before it is useful. The Macon-Bibb data report shows that candidate information, qualifying dates, and election context all come from local Board of Elections publications (PDFs, website) that require manual or semi-automated entry.

**Independent Test**: Can be tested by authenticating as an admin, performing full CRUD operations on candidates and election metadata, and verifying the data persists and validates correctly.

**Acceptance Scenarios**:

1. **Given** an admin is authenticated, **When** they create a candidate for an election with all required fields, **Then** the candidate is created and appears in the election's candidate list.
2. **Given** an existing candidate, **When** an admin updates the candidate's filing status to "withdrawn," **Then** the candidate record reflects the new status.
3. **Given** an existing election, **When** an admin adds a description, purpose, and milestone dates, **Then** the enriched data appears in the election detail response.
4. **Given** a non-admin user, **When** they attempt to create or modify a candidate, **Then** they receive a 403 Forbidden response.

---

### User Story 4 - Find Elections by Eligibility and Geography (Priority: P3)

A voter wants to know which upcoming elections they are eligible to vote in. They search or filter elections by geographic area or district and see only elections relevant to their location. They can also filter to see elections with open registration (deadline not yet passed) or active early voting.

**Why this priority**: Builds on top of existing election listing and boundary data. The geographic filtering already partially exists via `district` and `boundary_id` fields, but milestone date filtering and eligibility awareness are new. This is a P3 because it requires P1 and P2 data to be populated to be useful.

**Independent Test**: Can be tested by creating multiple elections with different districts and milestone dates, then filtering by geography and date criteria to verify correct results.

**Acceptance Scenarios**:

1. **Given** three elections in different districts, **When** a user filters by district type and identifier, **Then** only matching elections are returned.
2. **Given** two elections where one has a registration deadline in the future and one in the past, **When** a user filters for elections with open registration, **Then** only the future-deadline election is returned.
3. **Given** an election with early voting dates, **When** a user filters for elections currently in early voting, **Then** only elections whose early voting window includes today are returned.

---

### User Story 5 - Cross-Reference Candidates with Election Results (Priority: P3)

After results are published via the SOS feed, the system can associate pre-entered candidate profiles with their results. An admin or the system links a candidate record to the corresponding result entry, so voters see a unified view: the candidate's bio, photo, and links alongside their vote totals.

**Why this priority**: A nice-to-have enhancement that unifies the pre-election and post-election data. The SOS feed stores candidate results in JSONB with an `id` and `name`. Matching pre-entered candidates to result entries creates a richer experience but is not required for the core feature to deliver value.

**Independent Test**: Can be tested by entering a candidate, then importing SOS results, and verifying the candidate detail includes result data (or vice versa).

**Acceptance Scenarios**:

1. **Given** a candidate with a stored SOS ballot option ID, **When** results are fetched for the election, **Then** the candidate detail includes their vote count from results.
2. **Given** a candidate with no SOS ID match, **When** results are fetched, **Then** the candidate profile is still shown but without result data.

---

### Edge Cases

- What happens when a candidate qualifies for multiple elections in the same cycle (e.g., runs in a primary and then the general)? Each election has its own candidate records; the same person may appear as separate candidate entries per election.
- How does the system handle a candidate whose name in the SOS results differs slightly from the manually entered name (e.g., middle name included vs. excluded)? Cross-referencing uses the SOS ballot option ID, not name matching.
- What happens when an election's description or purpose is updated after voters have already seen it? Updates take effect immediately; no versioning of metadata. The `updated_at` timestamp reflects the change.
- What happens when all candidates withdraw from an election? The election remains with an empty candidate list. The election itself is not automatically removed or finalized.
- What happens when the same candidate photo URL becomes unavailable? The system stores the URL as provided. It does not validate URL reachability or cache external images.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support creating candidate records independently of SOS election results, allowing candidate data to exist before results are published.
- **FR-002**: System MUST store candidate profile information including full name, optional party affiliation (null for nonpartisan races), plain-text biographical text, photo URL, and external links (website, social media, campaign site).
- **FR-003**: System MUST track candidate filing status through a defined lifecycle: `qualified`, `withdrawn`, `disqualified`, `write_in`.
- **FR-004**: System MUST associate each candidate with exactly one election. A person running in multiple elections has separate candidate records per election.
- **FR-005**: System MUST support storing a ballot display order for each candidate within an election.
- **FR-006**: System MUST allow storing an optional SOS ballot option ID on a candidate record to enable cross-referencing with SOS results data.
- **FR-007**: System MUST support enriching election records with: description (free text), purpose statement, and eligibility description (who can vote).
- **FR-008**: System MUST support storing election milestone dates: voter registration deadline, early voting start date, early voting end date, absentee ballot request deadline, candidate qualifying start, and candidate qualifying end.
- **FR-009**: System MUST provide a public endpoint to list candidates for a given election, returning all candidates regardless of filing status by default, with an optional `status` filter parameter to narrow results (e.g., `?status=qualified`).
- **FR-010**: System MUST provide a public endpoint to retrieve a single candidate's full detail including all profile fields and links.
- **FR-011**: System MUST provide enriched election detail that includes new metadata fields (description, purpose, eligibility, milestone dates) alongside existing election fields, maintaining full backward compatibility.
- **FR-012**: System MUST restrict candidate and election metadata creation/modification to admin users via role-based access control.
- **FR-013**: System MUST support filtering the election list by upcoming milestone dates (e.g., `registration_open=true` returns elections with registration_deadline >= today, `early_voting_active=true` returns elections currently in their early voting window). When these filter parameters are false or omitted, no milestone date filter is applied.
- **FR-014**: System MUST support pagination on the candidate list endpoint.
- **FR-017**: System MUST support filtering the election list by geography using `district_type` and `district_identifier` query parameters, returning only elections matching the specified district.
- **FR-015**: System MUST store candidate external links as a structured collection of typed entries (e.g., type: "website", URL: "...") to support multiple links per candidate.
- **FR-016**: System MUST support optional incumbency tracking on a candidate record, indicating whether the candidate currently holds the office they are seeking.

### Key Entities

- **Candidate**: A person running for office in a specific election. Key attributes: full name, optional party affiliation (null for nonpartisan races), bio, photo URL, ballot order, filing status, incumbency flag, SOS ballot option ID (for results cross-reference). Belongs to exactly one election. Has zero or more external links.
- **Candidate Link**: A typed URL associated with a candidate (e.g., official website, campaign site, Facebook, Twitter/X). Key attributes: link type, URL, display label. Belongs to exactly one candidate.
- **Election (enriched)**: The existing election entity extended with: description, purpose, eligibility description, voter registration deadline, early voting start/end dates, absentee request deadline, qualifying start/end datetimes. All new fields are optional to maintain backward compatibility with existing elections.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Candidate information for an upcoming election can be entered and retrieved at least 30 days before election day, enabling forward-looking voter information.
- **SC-002**: A voter can view the complete candidate list for any election within 2 seconds of requesting it.
- **SC-003**: Election detail responses include all enriched metadata fields without breaking existing integrations that consume the current response shape.
- **SC-004**: 100% of candidate CRUD operations enforce role-based access control, with non-admin users receiving appropriate denial responses.
- **SC-005**: Candidate data entry for a typical election (6-10 candidates) can be completed by an admin in under 15 minutes through the API.
- **SC-006**: Elections with milestone dates populated can be filtered by date-based criteria (registration open, early voting active) with correct results.

## Assumptions

- **Photo storage**: Candidate photos are stored as external URLs, not uploaded binary files. The system does not host or proxy images.
- **Links flexibility**: Candidate links are stored as typed entries with a predefined set of common types (website, campaign, facebook, twitter, instagram, youtube, linkedin, other) but the URL field accepts any valid URL.
- **Admin-only data entry**: All candidate and election metadata management is admin-only. There is no public submission or candidate self-service portal.
- **No automatic candidate discovery**: Candidates are entered manually by admins based on local Board of Elections publications, qualifying lists, or sample ballots. There is no automated feed or scraper for candidate data.
- **One-to-many election-to-candidates**: Each Election row already represents a single race/contest in the current model (via `ballot_item_id`). Candidates are associated directly to elections without a separate contest/race entity.
- **Backward compatibility**: All new fields on the Election model are optional (nullable). Existing election records continue to work without modification. Existing API response shapes are extended, not replaced.
- **SOS results cross-reference is optional**: The SOS ballot option ID on a candidate is informational. Query-time display enrichment (US5 — showing vote counts alongside candidate profiles) is in scope, but persistent data reconciliation (merging or modifying candidate records based on SOS results) is not. That reconciliation can be a future enhancement.
- **No ballot measure support**: This feature covers candidate races only. Ballot measures, referenda, and party questions are out of scope and would be a separate feature.
