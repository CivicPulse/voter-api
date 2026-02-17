# Feature Specification: Voter History Ingestion

**Feature Branch**: `006-voter-history`
**Created**: 2026-02-17
**Status**: Draft
**Input**: User description: "We need a way to store and track this data as it relates to a voter (the Voter Registration Number). The election details may also be used to populate an election event that hasn't been imported otherwise."

## Clarifications

### Session 2026-02-17

- Q: How should unmatched voter history records be reconciled when the voter is later imported? → A: Lazy reconciliation — history records are joined to voters at query time; no explicit linking step or background job needed.
- Q: Should the existing voter detail endpoint be enriched with participation history, or only new dedicated endpoints? → A: Enrich existing voter detail — add a lightweight participation summary (election count + last election date) to the existing voter detail response.
- Q: How should bad or updated imports be handled? → A: Full re-import — the same file (e.g., 2026.csv) gets appended to throughout the year as new elections occur. Re-importing the file replaces all records from the previous import of that file with the new file's contents.

## User Scenarios & Testing

### User Story 1 - Import Voter Participation History (Priority: P1)

A data administrator imports a voter participation history file received from the Georgia Secretary of State. The file contains records of which voters participated in which elections, including how they voted (ballot style), whether they voted absentee, provisionally, or supplementally, and which party primary they participated in (if applicable). The system parses the file, stores each participation record linked to the corresponding voter, and reports import results.

**Why this priority**: Without importing voter history data, no other capability in this feature has anything to operate on. The import pipeline is the foundation for all downstream queries and analysis.

**Independent Test**: Import a sample voter history CSV and verify participation records appear correctly linked to voters. Delivers the core data store.

**Acceptance Scenarios**:

1. **Given** a valid voter participation history CSV in GA SoS format, **When** the administrator initiates an import, **Then** all valid records are stored and a summary shows total processed, succeeded, skipped duplicates, unmatched registration numbers, and parsing errors.
2. **Given** a file referencing voter registration numbers that exist in the system, **When** the import completes, **Then** each record is linked to the corresponding voter and retrievable by registration number.
3. **Given** a file referencing voter registration numbers not in the system, **When** the import runs, **Then** records are stored with the registration number as a text reference, flagged as unmatched, and reported in the summary.
4. **Given** a large file (tens of thousands of records), **When** the import runs, **Then** the system processes in batches with progress feedback and without excessive memory use.
5. **Given** the same file is imported a second time (e.g., 2026.csv updated with new election data), **When** the import runs, **Then** all records from the previous import of that file are replaced with the new file's contents, and the summary reports records added, updated, and removed.
6. **Given** a file that was previously imported with 10,000 records and now contains 15,000 records (5,000 new appended), **When** re-imported, **Then** all 15,000 records are stored and the previous import's records are fully replaced.

---

### User Story 2 - Query a Voter's Participation History (Priority: P2)

An analyst or API consumer looks up a specific voter's participation history to see which elections that voter participated in and how they voted. This enables turnout analysis, voter engagement profiling, and constituent outreach planning.

**Why this priority**: Querying voter-specific history is the primary read-path value. It depends on imported data (P1) but is the most common consumer use case.

**Independent Test**: Import voter history records, then request a voter's history by registration number and verify correct elections and details are returned.

**Acceptance Scenarios**:

1. **Given** history records exist for a voter, **When** an authorized user requests that voter's participation history, **Then** the system returns all elections participated in, ordered by date, with full participation details.
2. **Given** a voter with no history records, **When** their history is requested, **Then** the system returns an empty result (not an error).
3. **Given** a voter who participated in multiple elections, **When** their history is requested with a date range filter, **Then** only elections within the range are returned.
4. **Given** a voter exists in the system with participation history records, **When** an authorized user requests the existing voter detail, **Then** the response includes a participation summary showing total elections participated in and the most recent election date.

---

### User Story 3 - Auto-Create Election Events from Voter History (Priority: P3)

When voter history references an election (by date and type) not yet in the system, the system auto-creates a minimal election event record so participation data can be associated with a known election.

**Why this priority**: Eliminates manual data entry for election records discovered through voter history. Depends on import (P1) and enriches the election catalog.

**Independent Test**: Import voter history referencing an unknown election date/type, verify a corresponding election event is auto-created.

**Acceptance Scenarios**:

1. **Given** history records referencing an election date+type not in the system, **When** the import runs, **Then** a new election event is auto-created with the date, type, and a generated name.
2. **Given** history records referencing an election that already exists, **When** the import runs, **Then** no duplicate election is created.
3. **Given** an auto-created election, **When** an administrator views it, **Then** it is clearly marked as auto-created from voter history data.

---

### User Story 4 - Aggregate Participation Statistics (Priority: P3)

An analyst queries participation statistics to understand turnout patterns — totals, breakdowns by county, ballot style, or voting method for a given election.

**Why this priority**: Aggregate statistics are a convenience layer. Significant analytical value but not essential for core import and query workflows.

**Independent Test**: Import voter history, request aggregate counts for a specific election, verify totals match known data.

**Acceptance Scenarios**:

1. **Given** history records for an election, **When** turnout is requested, **Then** the system returns total participating voters.
2. **Given** history records for an election, **When** turnout by county is requested, **Then** per-county participation counts are returned.
3. **Given** history records for an election, **When** turnout by ballot style is requested, **Then** counts per ballot style are returned.

---

### Edge Cases

- **Re-import of updated file**: The same file (e.g., 2026.csv) may be re-imported after new election data is appended. Re-importing replaces all records from the previous import of that file with the new file's contents. No duplicate records are created.
- **Unmatched registration numbers**: Records stored with registration number as text reference. Reconciliation is lazy — when querying voter history, records are joined to voters at query time. If a voter is imported later, their history records are automatically associated on the next query with no explicit linking step.
- **Unparseable dates**: Records with invalid date formats are rejected and logged without halting the import.
- **Same-date different-type elections**: A voter participating in both "SPECIAL ELECTION" and "GENERAL" on the same date creates separate records (different election events).
- **Empty Party field**: Stored as-is (null/empty). Normal for non-primary elections; not an error.
- **Blank Provisional/Supplemental**: Treated as "No". Only explicit "Y" is positive.
- **Unknown counties**: Records imported with county name stored as-is. No requirement for county to pre-exist.

### Out of Scope

- Voter turnout prediction or modeling
- Visualization or charting of participation trends
- Comparison of voter history against registration status changes over time
- Ingestion of voter history from states other than Georgia
- Real-time election-night participation tracking

## Requirements

### Functional Requirements

- **FR-001**: System MUST ingest voter participation history from CSV files in the GA SoS 9-column format: County Name, Voter Registration Number, Election Date, Election Type, Party, Ballot Style, Absentee, Provisional, Supplemental.
- **FR-002**: System MUST store each participation record as a distinct entry linking a voter registration number to a specific election event, preserving all source fields.
- **FR-003**: System MUST link history records to existing voters by registration number. Records referencing unknown registration numbers MUST still be stored as text references and flagged as unmatched.
- **FR-004**: System MUST support re-importing the same file (identified by file name). The system MUST track which import job produced each record to enable clean replacement. See FR-021 for atomicity and replacement semantics.
- **FR-005**: System MUST process files in batches to support 100,000+ records without excessive memory use, with progress tracking.
- **FR-006**: System MUST auto-create election events when the import encounters a date+type combination not present in the election table. Auto-created elections MUST be distinguishable from manually created or feed-imported elections.
- **FR-007**: System MUST provide the ability to query a voter's complete participation history, ordered by election date, with full details.
- **FR-008**: System MUST provide the ability to query all participating voters for a specific election, with filtering by county, ballot style, and voting method flags.
- **FR-009**: System MUST provide aggregate participation counts for an election: total participants, breakdowns by county and by ballot style.
- **FR-010**: System MUST support filtering history queries by date range, election type, county, and ballot style.
- **FR-011**: System MUST paginate all list and query results.
- **FR-012**: System MUST generate an import summary after each import: total processed, succeeded, skipped duplicates, unmatched registration numbers, parsing errors.
- **FR-013**: System MUST support importing voter history from any year (not limited to 2026).
- **FR-014**: System MUST provide a CLI command for administrators to trigger imports from a file path.
- **FR-015**: System MUST provide an authenticated endpoint for administrators to trigger imports.
- **FR-016**: System MUST restrict import operations to administrator-privileged users.
- **FR-017**: System MUST restrict query access to authenticated users. Analyst and admin roles MUST have full access to all voter history endpoints. Viewer role MUST only have access to aggregate participation statistics (`GET /elections/{id}/participation/stats`). Viewer role MUST NOT have access to individual voter history listings (`GET /voters/{reg_num}/history`) or election participant listings (`GET /elections/{id}/participation`).
- **FR-018**: System MUST treat blank/empty Provisional and Supplemental values as "No".
- **FR-019**: System MUST parse Election Date from MM/DD/YYYY format and reject unparseable dates, logging the error without halting the import.
- **FR-020**: System MUST enrich the existing voter detail response with a participation summary containing total elections participated in and the most recent election date. If no history records exist for the voter, the summary fields MUST be null or zero (not omitted).
- **FR-021**: System MUST allow administrators to re-import a file, replacing all records from the previous import of that file. The re-import MUST be atomic — previous records are only removed once the new import succeeds. Auto-created elections from the previous import MUST NOT be deleted (they may be referenced by other data).

### Key Entities

- **Voter History Record** (new): A single voter's participation in a single election. Attributes: voter registration number, county, election date, election type, party, ballot style, absentee flag, provisional flag, supplemental flag, import job reference. Unique on voter registration number + election date + election type. Voter association is lazy — records are joined to voters by registration number at query time rather than storing a direct voter reference. No explicit reconciliation step is needed when voters are imported after their history records.

- **Election** (existing, may be auto-created): When voter history references a date+type not already present, a minimal election record is auto-created with date, type, and generated name. Marked to distinguish from other creation methods.

- **Voter** (existing, referenced): Identified by voter registration number. History records link by registration number. Unmatched numbers are stored for future reconciliation.

- **Import Job** (existing, extended): Gains a new file type value for voter history imports. Tracks standard counters plus skipped duplicates and unmatched registration numbers.

## Assumptions

- The GA SoS voter history CSV format (9 columns, comma-delimited, header row) is stable. Columns are always in order: County Name, Voter Registration Number, Election Date, Election Type, Party, Ballot Style, Absentee, Provisional, Supplemental.
- A voter participates at most once per election event (unique on registration number + date + type). The same voter may appear multiple times per file across different elections.
- The Party field is empty for non-primary elections. For primaries, it indicates which party's ballot was chosen.
- Ballot style values are not strictly validated against a closed set, as the SoS may introduce new styles.
- The Absentee flag is "Y" for non-Election Day voting methods (mail, early in-person, electronic delivery) and "N" for Election Day. In Georgia, early in-person voting is technically "advance in-person absentee."
- Blank Provisional and Supplemental fields mean "N".
- Files may contain records from multiple counties and elections.
- Not all voters in a history file will exist in the voters table; the system stores unmatched records for future reconciliation.
- Voter history files (e.g., 2026.csv) are cumulative — the same file grows throughout the year as new election data is appended. Re-importing a file replaces all records from the previous import of that file. Records from other import jobs are not affected.
- Existing JWT-based auth and role-based access control govern all operations.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Administrators can import a 50,000+ record file and receive a completion summary within 5 minutes.
- **SC-002**: 100% of valid records are stored and retrievable by voter registration number within 1 second of query execution.
- **SC-003**: Re-importing an updated file cleanly replaces previous records with zero duplicates and zero orphaned records.
- **SC-004**: Records referencing unrecognized registration numbers are stored and reported (0% valid-record data loss).
- **SC-005**: Every unique date+type combination in imported history has a corresponding election record after import (100% auto-creation coverage).
- **SC-006**: A voter's complete participation history is retrievable in under 2 seconds.
- **SC-007**: Aggregate participation counts for an election are returned in under 3 seconds for up to 50,000 participant records.
- **SC-008**: Non-admin users cannot trigger imports (0% unauthorized access).
