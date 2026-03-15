# Phase 1: Data Contracts - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Define all intermediate data formats (enhanced markdown specs, JSONL schemas, controlled vocabularies, and process specs) so that the converter, importer, and Claude Code skills can be built against stable contracts. No runtime code beyond Pydantic schema models. Phase 1 delivers specifications; Phase 2 delivers implementation.

</domain>

<decisions>
## Implementation Decisions

### District Linkage

- **Metadata table rows** for boundary info in election files (not YAML frontmatter or separate sections)
- **Body/Seat reference system** for all levels (state, county, municipal) — the converter resolves boundary_type from county reference files
- **Body IDs use hierarchical naming**: `{scope}-{body}` (e.g., `ga-governor`, `bibb-boe`, `macon-water-authority`)
- **Body/Seat everywhere** for consistency — even statewide/federal contests use Body/Seat references, not direct boundary_type
- **Seat IDs**: Claude's discretion on exact format (type-based slugs: `post-7`, `district-3`, `at-large`, `sole`)
- **At-large vs district seats**: each contest declares its own boundary independently — at-large BOE seats point to the parent county boundary, district BOE seats point to school_district boundary
- **Boundary_type values** use exact DB values (`us_house`, `state_senate`, `county`, etc.) — no human-friendly mapping layer
- **Unresolved boundaries** = converter validation error (strict) — if reference file isn't populated or boundary doesn't exist, converter fails with clear error
- **Per-contest metadata line** in county files: `**Body:** bibb-boe | **Seat:** post-7` below each `### Contest` heading
- **File-level metadata** in statewide files: Body/Seat in the `## Metadata` table
- **County reference file format spec** is part of Phase 1 (define the spec + populate Bibb as example; populating all 159 counties is a separate effort)

### File Scope and Structure

- **Keep current file grouping**: statewide = one file per office (all parties together), county = one file per county (all contests), special = one file per contest
- **Internal structure adapts by election type**: partisan primaries use party sections (`## Republican Primary`, `## Democrat Primary`); jungle primaries, generals, and non-partisan use a single `## Candidates` section with a Party column
- **Party row in metadata** is optional — present only for partisan primaries, omitted for non-partisan/general/jungle races
- **File-level metadata + per-section contest metadata**: top `## Metadata` table has shared fields (Election, Type, Boundary Type, District ID); each party section adds `**Contest Name (SOS):**` line
- **Unified overview format** — one flexible format with optional sections (Statewide Races, Federal Races, Local Elections) included based on what contests exist, not election type. Replaces the current two-variant split.
- **Two contest file formats**: single-contest (statewide, federal, individual special election contests) and multi-contest (county-grouped local races). Replaces the current three-format split (statewide, county, special election).

### Candidate Enrichment

- **Global `data/candidates/` directory** — one file per person, not per contest
- **Filename format**: `{name-slug}-{8-char-hash}.md` (e.g., `jane-doe-a3f2e1b4.md`)
- **Person section at top** with stable data: name, photo, email, external IDs, bio, links
- **Election-keyed sections below** with contest-specific data: party, occupation, filing status, status — with cross-links to the specific contest files
- **Contest table keeps core fields inline**: Candidate (linked to candidate file), Status, Incumbent, Occupation, Qualified Date
- **Email and Website dropped from contest table** — moved to candidate file (person-level data)
- **External IDs in candidate file**: Ballotpedia, Open States, VPAP, etc. as a `## External IDs` table
- **Link types match DB vocabulary**: website, campaign, facebook, twitter, instagram, youtube, linkedin, other
- **Candidate deduplication** handled by Claude skill in Phase 3, not by Phase 1 rules — Phase 1 just defines the "one person, one file, one ID" contract

### JSONL Structure

- **Four separate JSONL files**: `election_events.jsonl`, `elections.jsonl`, `candidates.jsonl`, `candidacies.jsonl`
- **Import order**: events -> elections -> candidates -> candidacies
- **Candidacy is a junction table** — links candidates (people) to elections (contests) with contest-specific fields (party, occupation, filing_status, ballot_order, qualified_date, is_incumbent)
- **UUIDs embedded in markdown metadata** — the markdown file is the source of truth for identity. Converter reads UUIDs from metadata tables; if missing, it's a validation error.
- **Candidacies reference UUIDs** from both candidate and election markdown files directly
- **Pydantic v2 models as schema source of truth** — defined in `src/voter_api/schemas/jsonl/`
- **JSONL includes all DB columns as optional** — import-relevant fields are populated from markdown; feed-related fields (data_source_url, refresh settings) are optional and populated from overview Data Sources when available
- **Results feed URL** lives in the election overview's `## Data Sources` section. The converter propagates it to every election JSONL record. Marked as "TBD" until available.

### Candidate Model Change (contract only, migration in Phase 2)

- **Candidate becomes a person entity** — decoupled from a single election
- **New candidacy junction table** — links candidates to elections with contest-specific fields
- Phase 1 defines the JSONL schemas assuming the new model
- Phase 2 delivers the Alembic migration, API updates, and CLI changes

### Election Event Grouping

- **Overview file = ElectionEvent** — gets its own UUID and JSONL schema (ElectionEventJSONL)
- **Calendar dates move to ElectionEvent** — registration_deadline, early_voting_start/end, absentee_request_deadline, qualifying_start/end migrate from Election to ElectionEvent (contract in Phase 1, migration in Phase 2)
- **Feed URL and refresh fields move to ElectionEvent** — data_source_url, last_refreshed_at, refresh_interval_seconds belong on the event, not duplicated across contests
- **Event type uses same vocabulary as contests** — broadest applicable type wins for mixed events

### Election Type Vocabulary

- **Two-field approach**: `election_type` (base type) + `election_stage` (resolution mechanism)
- **Election types**: `general_primary`, `general`, `special`, `special_primary`, `municipal`
- **Election stages**: `election` (default), `runoff`, `recount`
- **Free-form `name` field preserved** — matches SOS naming exactly for voter recognition (e.g., "January 20, 2026 - Special Election")
- **H1 heading is display name, `Name (SOS)` in metadata** preserves the exact SOS string
- **Event type priority for mixed events** (highest wins): general_primary > general > municipal > special_primary > special
- **Same vocabulary for events and contests**, different semantics — event type is broadest applicable, contest type is specific

### UUID Strategy

- **UUIDs in markdown metadata table** — `| ID | 550e8400-e29b-... |` as a row in the metadata table
- **Converter reads UUIDs from markdown** — never generates them. If missing, it's a validation error.
- **Backfill process** matches existing DB records to markdown files by natural key (name+date for elections, TBD for candidates) and writes the DB's UUID back into the markdown
- Phase 1 specs the backfill matching rules; Phase 2 implements the CLI command

### Schema Versioning

- **Simple integer versions** — start at 1, increment on breaking changes
- **Both markdown format and JSONL schemas versioned** — `| Format Version | 1 |` in markdown metadata; `"_schema_version": 1` in JSONL records
- **All file types versioned independently** — candidate format can be v2 while election format is v1
- **All markdown file types get a format version**: election overviews, contest files, candidate files, county reference files
- **Migrate forward** — importer supports current version only. Old JSONL files must be migrated via script before re-import.

### Existing File Migration

- **Automated migration script** — reads existing ~200 files, adds missing fields (Format Version, UUID, Body/Seat), rewrites in enhanced format, creates candidate stubs
- **Phase 1 specs the migration rules** (what gets added, how Body/Seat is inferred from contest names, how candidate stubs are created); Phase 2 implements the script
- **Unified overview format** replaces the two current variants

### Format Spec Organization

- **Centralized in `docs/formats/`** with subdirectories: `markdown/`, `jsonl/`, `vocabularies/`
- **Existing `data/elections/formats/` replaced** — old specs superseded by new enhanced specs
- **Old-to-new mapping**: STATEWIDE + SPECIAL -> single-contest.md; COUNTY -> multi-contest.md; OVERVIEW -> election-overview.md
- **JSONL docs auto-generated from Pydantic models** via a generation script (reads `model_json_schema()`, renders markdown)
- **Pydantic models live in code**: `src/voter_api/schemas/jsonl/`

### Claude's Discretion

- Seat ID exact format and patterns (type-based slugs)
- Loading skeleton and error state designs in markdown
- Exact field ordering within metadata tables
- Auto-generation script implementation details

</decisions>

<specifics>
## Specific Ideas

- "Districts don't have a party" — party is a contest attribute, not a district attribute. Contests in the same district can have different party primaries.
- Jungle primaries (all candidates regardless of party) stress-tested the format design — the format must handle partisan primaries, jungle primaries, generals, and non-partisan races without structural changes.
- Bibb County BOE has at-large posts (7 & 8, county-wide) and district posts (1-6) on the same body — the Body/Seat reference system handles this by letting each contest declare its own boundary independently.
- Macon Water Authority has a similar at-large + district structure.
- SOS results feed URL isn't available until days before the election — it covers all contests in an event. The markdown pipeline creates election records weeks/months before, and the feed URL is attached later when discovered (by human or automated scraper).
- The `data/states/GA/` directory is being built as a reference dataset for governing body structures — this feeds into the Body/Seat resolution system.
- Candidate-as-person model enables tracking candidates across elections over time, which the current per-election candidate model can't do.
- SOS CSV has candidate names in ALL CAPS — the Claude skill handles case normalization and deduplication.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Election` model (`src/voter_api/models/election.py`): Has district resolution fields (district_type, district_identifier, boundary_id), calendar fields, and election_event_id FK — all relevant to the JSONL schema
- `Candidate` model (`src/voter_api/models/candidate.py`): Has bio, photo_url, party, filing_status, occupation, email — needs refactoring to person + candidacy junction
- `CandidateLink` model: Typed URLs with controlled vocabulary (website, campaign, facebook, etc.) — reuse for candidate file Links table
- `ElectionEvent` model (`src/voter_api/models/election_event.py`): Minimal (event_date, event_name, event_type) — needs enhancement with calendar dates and feed URL
- `Boundary` model: Has boundary types used as controlled vocabulary — `county`, `state_house`, `state_senate`, `us_house`, `us_senate`, `city`, `school_district`, `commission`
- Existing Pydantic schemas in `src/voter_api/schemas/` — patterns for defining JSONL schemas
- 4 existing format specs in `data/elections/formats/` — content basis for new enhanced specs
- ~200 existing election markdown files — need migration to enhanced format
- `data/states/GA/counties/` — 159 county reference file stubs (metadata only, no governing bodies yet)
- `data/results/` — 14 SOS results JSON files showing all election type patterns

### Established Patterns
- Pydantic v2 for all schemas — JSONL schemas follow this convention
- SQLAlchemy 2.x async + GeoAlchemy2 for models — junction table follows this pattern
- UUID primary keys throughout — consistent with UUID-in-markdown strategy
- Metadata tables (`| Field | Value |`) already used in existing format specs — extended for new fields

### Integration Points
- `src/voter_api/schemas/jsonl/` — new package for JSONL Pydantic models
- `docs/formats/` — new directory for centralized format specs
- `data/candidates/` — new global directory for candidate files
- Election model refactoring (Phase 2): calendar fields -> ElectionEvent, feed fields -> ElectionEvent, candidate -> person + candidacy
- Boundary types vocabulary feeds from existing `boundaries` table data

</code_context>

<deferred>
## Deferred Ideas

- **Automated SOS results URL scraper** — discover feed URLs automatically when they become available. Future capability beyond Phase 1-4.
- **Populating all 159 county reference files** with governing body data — separate effort after format spec is defined.
- **Historical election backfill** (2024-2025) — separate effort, different data source.
- **Expanding link type vocabulary** (tiktok, threads, bluesky, donate, ballotpedia) — can be added when needed by updating DB constraint and format spec.

</deferred>

## Roadmap Updates Needed

Phase 1's scope has expanded significantly through this discussion. The planner should update ROADMAP.md and REQUIREMENTS.md to reflect:

### Phase 1 Expanded Deliverables
- County reference file format spec (with Bibb example)
- Global candidate file format spec
- Candidacy JSONL schema (new junction concept)
- Election event JSONL schema (enhanced ElectionEvent)
- Election type/stage controlled vocabulary
- Body/Seat reference system and naming convention
- UUID-in-markdown strategy spec
- Backfill matching rules spec
- Migration rules spec (existing files -> enhanced format)
- Format versioning across all file types
- Unified overview format (replacing two variants)
- Two contest file formats (replacing three)
- JSONL doc auto-generation script
- Old format specs replaced and reorganized to docs/formats/

### Phase 2 Scope Growth
- Alembic migration: Candidate -> Person + Candidacy junction table
- Alembic migration: Calendar fields from Election to ElectionEvent
- Alembic migration: Feed URL/refresh fields from Election to ElectionEvent
- Alembic migration: election_stage field added to Election
- Markdown migration script (existing ~200 files to enhanced format)
- UUID backfill CLI command
- Four import commands (events, elections, candidates, candidacies)

---

*Phase: 01-data-contracts*
*Context gathered: 2026-03-14*
