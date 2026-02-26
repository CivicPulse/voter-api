# Election Information Data Model

## Overview

This document defines the database schema additions for the election information feature. The data model is designed to:

- Store candidate records independently of SOS election results, enabling forward-looking election information
- Support rich candidate profiles with typed external links
- Enrich existing election records with descriptive metadata and milestone dates
- Maintain full backward compatibility with existing election data

## Entities

### candidates

A person running for office in a specific election. Candidates are admin-managed records created from local Board of Elections publications, qualifying lists, or sample ballots. They exist independently of SOS results and can be entered weeks or months before election day.

**Key Design Choices**:
- FK to `elections.id` with `ON DELETE CASCADE` — candidates are deleted when their election is deleted
- Four-state filing status lifecycle: `qualified` (default), `withdrawn`, `disqualified`, `write_in`
- Party affiliation is nullable to support nonpartisan races (judicial, school board, water authority)
- `sos_ballot_option_id` enables optional cross-reference to SOS results JSONB entries
- Bio is plain text only; consuming frontends handle display formatting
- Photo stored as external URL reference, not binary

### candidate_links

Typed external URL entries associated with a candidate. Supports multiple links per candidate with predefined types for common social media and web properties.

**Key Design Choices**:
- FK to `candidates.id` with `ON DELETE CASCADE` — links are deleted with their candidate
- `link_type` constrained to: `website`, `campaign`, `facebook`, `twitter`, `instagram`, `youtube`, `linkedin`, `other`
- `label` is optional display text (e.g., "Campaign Website", "Official Facebook Page")

### elections (enriched)

The existing `elections` table extended with optional metadata fields. All new columns are nullable to maintain backward compatibility — existing election records require no data backfill.

**Key Design Choices**:
- `description` and `purpose` are separate fields: description is detailed context, purpose is a short statement of what the election decides
- `eligibility_description` stores human-readable text about who can vote (e.g., "Registered voters in Commission District 5")
- Date fields use `Date` type for deadlines (registration, early voting, absentee) and `DateTime(timezone=True)` for qualifying start/end (which have specific times like "9:00 AM" or "noon")
- No new indexes on metadata fields — they are primarily read via election detail, not filtered independently (except milestone date filters on the list endpoint)

## Schema

### candidates

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Primary key |
| election_id | UUID | FK -> elections.id (ON DELETE CASCADE), NOT NULL, indexed | The election this candidate is running in |
| full_name | VARCHAR(200) | NOT NULL | Candidate's full name as it appears on the ballot |
| party | VARCHAR(50) | NULL | Party affiliation (null for nonpartisan races) |
| bio | TEXT | NULL | Plain-text biographical summary |
| photo_url | TEXT | NULL | URL to candidate's photo (external hosted) |
| ballot_order | INTEGER | NULL | Display order on the ballot within this election |
| filing_status | VARCHAR(20) | NOT NULL, default 'qualified' | Filing lifecycle: qualified, withdrawn, disqualified, write_in |
| is_incumbent | BOOLEAN | NOT NULL, default false | Whether candidate currently holds this office |
| sos_ballot_option_id | VARCHAR(50) | NULL | SOS ballot option ID for cross-referencing results |
| created_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record last modified timestamp |

**Constraints**:
- `UNIQUE (election_id, full_name)` — prevents duplicate candidates per election (`uq_candidate_election_name`)
- `CHECK (filing_status IN ('qualified', 'withdrawn', 'disqualified', 'write_in'))` — enforce valid status values (`ck_candidate_filing_status`)

**Indexes**:
- `ix_candidates_election_id` on `(election_id)` — list candidates for an election
- `ix_candidates_filing_status` on `(filing_status)` — filter by status
- `ix_candidates_sos_ballot_option_id` on `(sos_ballot_option_id)` WHERE NOT NULL — cross-reference with SOS results

### candidate_links

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, default gen_random_uuid() | Primary key |
| candidate_id | UUID | FK -> candidates.id (ON DELETE CASCADE), NOT NULL, indexed | The candidate this link belongs to |
| link_type | VARCHAR(20) | NOT NULL | Type of link: website, campaign, facebook, twitter, instagram, youtube, linkedin, other |
| url | TEXT | NOT NULL | The URL |
| label | VARCHAR(200) | NULL | Optional display label for the link |
| created_at | TIMESTAMPTZ | NOT NULL, server_default now() | Record creation timestamp |

**Constraints**:
- `CHECK (link_type IN ('website', 'campaign', 'facebook', 'twitter', 'instagram', 'youtube', 'linkedin', 'other'))` — enforce valid link types (`ck_candidate_link_type`)

**Indexes**:
- `ix_candidate_links_candidate_id` on `(candidate_id)` — find links for a candidate

### elections (new columns)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| description | TEXT | NULL | Detailed description of the election |
| purpose | TEXT | NULL | Short statement of what this election decides |
| eligibility_description | TEXT | NULL | Human-readable text about voter eligibility |
| registration_deadline | DATE | NULL | Voter registration deadline |
| early_voting_start | DATE | NULL | First day of early voting |
| early_voting_end | DATE | NULL | Last day of early voting |
| absentee_request_deadline | DATE | NULL | Deadline to request an absentee ballot |
| qualifying_start | TIMESTAMPTZ | NULL | Candidate qualifying period opens (date + time) |
| qualifying_end | TIMESTAMPTZ | NULL | Candidate qualifying period closes (date + time) |

No additional constraints or indexes on these columns. Milestone date filtering (FR-013) uses WHERE clauses on the existing `elections` query without dedicated indexes — the `election_date` index already narrows the result set sufficiently for expected query volumes.

## Relationships

```
elections (1) ──< (*) candidates ──< (*) candidate_links
    │
    │ existing relationships preserved:
    │ elections (1) ──< (1) election_results
    │ elections (1) ──< (*) election_county_results
    │ elections (*) ──> (1) boundaries (FK)
```

**Foreign Keys**:
- `candidates.election_id` -> `elections.id` (ON DELETE CASCADE)
- `candidate_links.candidate_id` -> `candidates.id` (ON DELETE CASCADE)

## Entity-Relationship Diagram

```
┌─────────────────────────────────────────┐
│ elections (existing + new columns)       │
├─────────────────────────────────────────┤
│ id (PK)                        UUID     │
│ name                           VARCHAR  │
│ election_date                  DATE     │
│ election_type                  VARCHAR  │
│ district                       VARCHAR  │
│ ... (existing columns)                  │
│ ─── new columns ───                     │
│ description                    TEXT     │
│ purpose                        TEXT     │
│ eligibility_description        TEXT     │
│ registration_deadline          DATE     │
│ early_voting_start             DATE     │
│ early_voting_end               DATE     │
│ absentee_request_deadline      DATE     │
│ qualifying_start               TIMESTAMPTZ │
│ qualifying_end                 TIMESTAMPTZ │
│ created_at                     TIMESTAMPTZ │
│ updated_at                     TIMESTAMPTZ │
└────────────┬────────────────────────────┘
             │
             │ 1
             │
             │ * (ON DELETE CASCADE)
             │
┌────────────▼────────────────────────────┐
│ candidates                              │
├─────────────────────────────────────────┤
│ id (PK)                        UUID     │
│ election_id (FK)               UUID     │
│ full_name                      VARCHAR  │
│ party                          VARCHAR  │
│ bio                            TEXT     │
│ photo_url                      TEXT     │
│ ballot_order                   INTEGER  │
│ filing_status                  VARCHAR  │
│ is_incumbent                   BOOLEAN  │
│ sos_ballot_option_id           VARCHAR  │
│ created_at                     TIMESTAMPTZ │
│ updated_at                     TIMESTAMPTZ │
└────────────┬────────────────────────────┘
             │
             │ 1
             │
             │ * (ON DELETE CASCADE)
             │
┌────────────▼────────────────────────────┐
│ candidate_links                         │
├─────────────────────────────────────────┤
│ id (PK)                        UUID     │
│ candidate_id (FK)              UUID     │
│ link_type                      VARCHAR  │
│ url                            TEXT     │
│ label                          VARCHAR  │
│ created_at                     TIMESTAMPTZ │
└─────────────────────────────────────────┘
```

## Design Decisions

### 1. CASCADE delete for candidates

**Decision**: When an election is deleted, all its candidates are automatically deleted.

**Rationale**:
- Candidates have no independent meaning outside their election context.
- Unlike `ElectedOfficialSource` (SET NULL), candidate data is not sourced from external providers with independent caching value.
- Simplifies cleanup — no orphaned candidate records to manage.

### 2. No separate Contest/Race entity

**Decision**: Candidates associate directly to Elections without an intermediate Contest table.

**Rationale**:
- Each `Election` row already represents a single race (enforced by `ballot_item_id` semantics).
- Adding a Contest entity would require migrating existing data, changing all election endpoints, and adding complexity for no functional benefit.
- If a future feature needs to distinguish "election events" from "races," that can be a separate refactoring.

### 3. Plain text bio

**Decision**: Bio field is plain text only, not markdown or HTML.

**Rationale**:
- Avoids sanitization/XSS concerns in the API layer.
- Consuming frontends can apply their own formatting.
- Matches the project pattern of storing clean data and letting the presentation layer handle display.

### 4. DateTime for qualifying start/end

**Decision**: `qualifying_start` and `qualifying_end` use `TIMESTAMPTZ` while other milestone dates use `DATE`.

**Rationale**:
- Real-world qualifying periods have specific times (e.g., "9:00 AM Monday" to "noon Friday" per Macon-Bibb data).
- Registration and early voting deadlines are day-level only.
- The type distinction accurately models the data.

### 5. Link types as check constraint

**Decision**: Use a `CHECK` constraint on `link_type` rather than a separate lookup table.

**Rationale**:
- The set of link types is small and rarely changes.
- A lookup table adds a join with no practical benefit.
- New link types can be added via a simple migration (modify the CHECK constraint).

## Migration Notes

### Prerequisites

Requires:
- PostgreSQL 12+ with JSONB support
- `gen_random_uuid()` function (available in PostgreSQL 13+ natively or via `pgcrypto` extension)
- Existing `elections` table

### Migration 037: Add candidates tables

1. **Create `candidates` table** with UUIDMixin, TimestampMixin, all columns
2. **Create indexes**: `ix_candidates_election_id`, `ix_candidates_filing_status`, `ix_candidates_sos_ballot_option_id`
3. **Create unique constraint**: `uq_candidate_election_name` on `(election_id, full_name)`
4. **Create check constraint**: `ck_candidate_filing_status`
5. **Create `candidate_links` table** with UUIDMixin, all columns
6. **Create index**: `ix_candidate_links_candidate_id`
7. **Create check constraint**: `ck_candidate_link_type`

### Migration 038: Add election metadata columns

1. **Add columns** to `elections` table: `description`, `purpose`, `eligibility_description`, `registration_deadline`, `early_voting_start`, `early_voting_end`, `absentee_request_deadline`, `qualifying_start`, `qualifying_end`
2. All columns nullable — no data backfill needed

### Downgrade

- Migration 038: Drop the 9 new columns from `elections`
- Migration 037: Drop `candidate_links` table, then `candidates` table

## References

- **Feature Spec**: `specs/010-election-info/spec.md`
- **API Contract**: `specs/010-election-info/contracts/openapi.yaml`
- **Existing Election Model**: `src/voter_api/models/election.py`
- **Existing Elected Officials Model**: `src/voter_api/models/elected_official.py` (pattern reference)
- **SQLAlchemy Base**: `src/voter_api/models/base.py` (UUIDMixin, TimestampMixin, Base)
