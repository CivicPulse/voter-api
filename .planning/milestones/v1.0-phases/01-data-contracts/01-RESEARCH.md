# Phase 1: Data Contracts - Research

**Researched:** 2026-03-14 (refreshed 2026-03-14)
**Domain:** Markdown format specifications, Pydantic v2 JSONL schemas, controlled vocabularies, data contract design
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### District Linkage
- Metadata table rows for boundary info in election files (not YAML frontmatter or separate sections)
- Body/Seat reference system for all levels (state, county, municipal) -- the converter resolves boundary_type from county reference files
- Body IDs use hierarchical naming: `{scope}-{body}` (e.g., `ga-governor`, `bibb-boe`, `macon-water-authority`)
- Body/Seat everywhere for consistency -- even statewide/federal contests use Body/Seat references, not direct boundary_type
- Seat IDs: Claude's discretion on exact format (type-based slugs: `post-7`, `district-3`, `at-large`, `sole`)
- At-large vs district seats: each contest declares its own boundary independently
- Boundary_type values use exact DB values (`us_house`, `state_senate`, `county`, etc.) -- no human-friendly mapping layer
- Unresolved boundaries = converter validation error (strict)
- Per-contest metadata line in county files: `**Body:** bibb-boe | **Seat:** post-7` below each `### Contest` heading
- File-level metadata in statewide files: Body/Seat in the `## Metadata` table
- County reference file format spec is part of Phase 1 (define the spec + populate Bibb as example)

#### File Scope and Structure
- Keep current file grouping: statewide = one file per office, county = one file per county, special = one file per contest
- Internal structure adapts by election type: partisan primaries use party sections; jungle primaries/generals/non-partisan use single `## Candidates` section
- Party row in metadata is optional -- present only for partisan primaries
- File-level metadata + per-section contest metadata
- Unified overview format -- one flexible format with optional sections, replaces two-variant split
- Two contest file formats: single-contest and multi-contest (replaces three-format split)

#### Candidate Enrichment
- Global `data/candidates/` directory -- one file per person, not per contest
- Filename format: `{name-slug}-{8-char-hash}.md`
- Person section at top with stable data: name, photo, email, external IDs, bio, links
- Election-keyed sections below with contest-specific data with cross-links
- Contest table keeps core fields inline: Candidate (linked), Status, Incumbent, Occupation, Qualified Date
- Email and Website dropped from contest table -- moved to candidate file
- External IDs in candidate file: Ballotpedia, Open States, VPAP, etc. as `## External IDs` table
- Link types match DB vocabulary: website, campaign, facebook, twitter, instagram, youtube, linkedin, other
- Candidate deduplication handled by Claude skill in Phase 3

#### JSONL Structure
- Four separate JSONL files: `election_events.jsonl`, `elections.jsonl`, `candidates.jsonl`, `candidacies.jsonl`
- Import order: events -> elections -> candidates -> candidacies
- Candidacy is a junction table linking candidates to elections
- UUIDs embedded in markdown metadata -- markdown is source of truth
- Pydantic v2 models as schema source of truth in `src/voter_api/schemas/jsonl/`
- JSONL includes all DB columns as optional
- Results feed URL lives in election overview's `## Data Sources` section; propagated to every election JSONL record

#### Candidate Model Change (contract only, migration in Phase 2)
- Candidate becomes a person entity -- decoupled from a single election
- New candidacy junction table with contest-specific fields
- Phase 1 defines JSONL schemas assuming the new model
- Phase 2 delivers Alembic migration

#### Election Event Grouping
- Overview file = ElectionEvent -- gets its own UUID and JSONL schema
- Calendar dates move to ElectionEvent (contract in Phase 1, migration in Phase 2)
- Feed URL and refresh fields move to ElectionEvent

#### Election Type Vocabulary
- Two-field approach: `election_type` + `election_stage`
- Election types: `general_primary`, `general`, `special`, `special_primary`, `municipal`
- Election stages: `election` (default), `runoff`, `recount`
- Free-form `name` field preserved matching SOS naming exactly
- Event type priority for mixed events: general_primary > general > municipal > special_primary > special

#### UUID Strategy
- UUIDs in markdown metadata table as a row `| ID | 550e8400-e29b-... |`
- Converter reads UUIDs from markdown -- never generates them
- Backfill process matches existing DB records by natural key
- Phase 1 specs the backfill matching rules; Phase 2 implements the CLI command

#### Schema Versioning
- Simple integer versions -- start at 1
- Both markdown format and JSONL schemas versioned independently
- `| Format Version | 1 |` in markdown metadata; `"schema_version": 1` in JSONL records
- All file types versioned independently
- Importer supports current version only; old JSONL must be migrated via script

#### Existing File Migration
- Automated migration script -- reads ~200 files, adds missing fields, rewrites in enhanced format
- Phase 1 specs the migration rules; Phase 2 implements the script

#### Format Spec Organization
- Centralized in `docs/formats/` with subdirectories: `markdown/`, `jsonl/`, `vocabularies/`
- Existing `data/elections/formats/` replaced
- JSONL docs auto-generated from Pydantic models via a generation script

### Claude's Discretion
- Seat ID exact format and patterns (type-based slugs)
- Loading skeleton and error state designs in markdown
- Exact field ordering within metadata tables
- Auto-generation script implementation details

### Deferred Ideas (OUT OF SCOPE)
- Automated SOS results URL scraper
- Populating all 159 county reference files with governing body data
- Historical election backfill (2024-2025)
- Expanding link type vocabulary (tiktok, threads, bluesky, donate, ballotpedia)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FMT-01 | Enhanced markdown format spec includes district linkage fields (boundary_type + district_identifier) for every contest | Body/Seat reference system; county reference file spec; `per-contest metadata line` pattern for multi-contest files, metadata table for single-contest files |
| FMT-02 | Enhanced markdown format spec includes election metadata (early voting start/end, registration deadline, absentee deadline) per election | Calendar fields map 1:1 to `ElectionEvent` model; move from `Election` model per CONTEXT decisions; overview file = ElectionEvent |
| FMT-03 | Enhanced markdown format spec includes candidate details (party, photo URL, bio, contact info, external IDs) per candidate | Global `data/candidates/` directory; person-level candidate files with election-keyed sections; `CandidateLink` link type vocabulary already defined in DB |
| FMT-04 | JSONL schema for elections mirrors the Election DB model with all required and optional fields documented | `Election` model fully mapped; new `election_stage` field needed; calendar fields migrate to `ElectionEvent` JSONL per CONTEXT |
| FMT-05 | JSONL schema for candidates mirrors the Candidate DB model with all required and optional fields documented | Post-refactor: `candidates.jsonl` = person entity, `candidacies.jsonl` = junction; all current `Candidate` fields distributed across the two schemas |
| FMT-06 | JSONL files include a `schema_version` field for forward compatibility | Simple integer version; Pydantic regular field (not underscore-prefixed); documented in `docs/formats/jsonl/` |
</phase_requirements>

## Summary

Phase 1 is a **specification-only phase** -- no runtime application code beyond Pydantic v2 model definitions. The deliverables are: enhanced markdown format specs (3 file types + county reference format + candidate file format), JSONL schema Pydantic models (4 schemas), controlled vocabulary documentation, Body/Seat reference system definition, UUID strategy spec, backfill matching rules, migration rules for existing ~200 files, and a schema doc auto-generation script.

The existing codebase provides all the raw material needed. Four active ORM models (`Election`, `Candidate`, `CandidateLink`, `ElectionEvent`, `Boundary`) define the target DB schema. Four existing format specs in `data/elections/formats/` provide the content basis and reveal what fields are missing (district linkage, UUIDs, format versions, Body/Seat, candidate person identity). The existing election files (15 statewide + 159 county stubs + 4 special election files) demonstrate the concrete editing scope.

**Primary recommendation:** Define all specs in `docs/formats/` first, then write Pydantic models in `src/voter_api/schemas/jsonl/`, then write the auto-generation script. Everything downstream (Phase 2 converter, Phase 3 skills) can start as soon as format specs + Pydantic models exist. The Bibb county reference file should be the worked example that validates the Body/Seat system is complete.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pydantic v2 | `>=2.0.0` (pinned in pyproject.toml) | JSONL schema models, validation, `model_json_schema()` for doc generation | Already the project standard for all schemas |
| Python standard library `uuid` | stdlib | UUID generation for schema doc generation script | Already used throughout project |
| Python standard library `json` | stdlib | JSONL file I/O | No external dependency needed for spec/schema work |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic.BaseModel` with `model_json_schema()` | Pydantic v2 | Auto-generate JSONL documentation from models | Used in the doc generation script |
| `pydantic.Field` with `description=` | Pydantic v2 | Field-level documentation embedded in schema | Every JSONL schema field needs a `description` |
| `enum.StrEnum` | Python 3.11+ stdlib | Controlled vocabularies as enums | Already used in `candidate.py` schemas (`FilingStatus`, `LinkType`) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pydantic v2 for JSONL schemas | JSON Schema files | Pydantic models are code -- they can be imported and used for validation in Phase 2 without translation |
| `StrEnum` for vocabularies | `Literal[...]` types | StrEnum is reusable across models; Literal is fine for single-use. The project already uses StrEnum (see `FilingStatus` in `schemas/candidate.py`) |

**Installation:** No new dependencies required. All tools are in the existing stack.

## Architecture Patterns

### Recommended Project Structure

```
docs/formats/
|-- markdown/
|   |-- election-overview.md          # Unified overview format spec
|   |-- single-contest.md             # Statewide + special election contest spec
|   |-- multi-contest.md              # County-grouped local races spec
|   |-- candidate-file.md             # Global candidate file spec
|   +-- county-reference.md           # County reference file spec
|-- jsonl/
|   |-- election-events.md            # Auto-generated from ElectionEventJSONL model
|   |-- elections.md                   # Auto-generated from ElectionJSONL model
|   |-- candidates.md                  # Auto-generated from CandidateJSONL model
|   +-- candidacies.md                 # Auto-generated from CandidacyJSONL model
|-- vocabularies/
|   |-- election-types.md             # election_type + election_stage controlled vocabulary
|   |-- boundary-types.md             # boundary_type values from DB + Body/Seat system
|   |-- filing-status.md              # qualified, withdrawn, disqualified, write_in
|   +-- link-types.md                 # website, campaign, facebook, twitter, etc.
+-- specs/
    |-- uuid-strategy.md              # UUID embedding and management rules
    |-- backfill-rules.md             # Rules for matching DB records to markdown
    +-- migration-rules.md            # Rules for migrating existing ~200 files

src/voter_api/schemas/jsonl/
|-- __init__.py                       # Public exports
|-- enums.py                          # StrEnum definitions (ElectionType, ElectionStage, etc.)
|-- election_event.py                 # ElectionEventJSONL (Pydantic BaseModel)
|-- election.py                       # ElectionJSONL (Pydantic BaseModel)
|-- candidate.py                      # CandidateJSONL (Pydantic BaseModel)
+-- candidacy.py                      # CandidacyJSONL (Pydantic BaseModel)

data/states/GA/counties/
+-- bibb.md                           # Enhanced with governing bodies (Bibb example)

data/candidates/
+-- (empty -- new global candidate directory, created in Phase 1)

tools/
+-- generate_jsonl_docs.py            # Reads model_json_schema(), renders markdown
```

### Pattern 1: Pydantic JSONL Schema Model

**What:** Each JSONL file type has one Pydantic BaseModel in `src/voter_api/schemas/jsonl/`. The model contains every DB column as an optional field with a `description` string. A `schema_version` field is required (not optional).

**When to use:** Defining `election_events.jsonl`, `elections.jsonl`, `candidates.jsonl`, `candidacies.jsonl` schemas.

**CRITICAL: Pydantic v2 underscore prefix behavior.** In Pydantic v2, fields with a leading underscore (e.g., `_schema_version`) are treated as **private attributes** and are excluded from serialization, JSON Schema output (`model_json_schema()`), and `model_dump()`. The field MUST be named `schema_version` (no underscore prefix) in both the Python attribute and the JSONL output. The CONTEXT.md references `"_schema_version": 1` in JSONL records, but the actual Pydantic implementation uses `schema_version` to ensure the field appears in serialized output.

**Example:**
```python
# Source: existing project pattern from src/voter_api/schemas/candidate.py
import uuid
from datetime import date
from pydantic import BaseModel, Field


class ElectionJSONL(BaseModel):
    """JSONL record for a single election contest.

    Maps 1:1 to the elections DB table. Import-relevant fields are
    populated from markdown; feed-related fields are optional.
    """

    schema_version: int = Field(default=1, description="Schema version. Increment on breaking changes.")
    id: uuid.UUID = Field(description="UUID from markdown metadata table. Required -- converter error if missing.")
    election_event_id: uuid.UUID = Field(description="UUID of the parent ElectionEvent (overview file).")
    name: str = Field(description="Display name matching the H1 heading in the contest markdown file.")
    name_sos: str | None = Field(default=None, description="Exact SOS contest name from **Contest Name (SOS):** line.")
    election_date: date = Field(description="Election day date (YYYY-MM-DD).")
    election_type: str = Field(description="Base election type. One of: general_primary, general, special, special_primary, municipal.")
    election_stage: str = Field(default="election", description="Resolution mechanism. One of: election, runoff, recount.")
    boundary_type: str | None = Field(default=None, description="Exact DB boundary type value resolved from Body/Seat reference.")
    district_identifier: str | None = Field(default=None, description="Boundary identifier resolved from Body/Seat reference.")
    # ... all other Election model columns
```

### Pattern 2: Markdown Metadata Table with UUID and Format Version

**What:** Every markdown file type includes `| ID | <uuid> |` and `| Format Version | 1 |` rows in the `## Metadata` table. The converter reads the UUID; if missing it's a validation error.

**When to use:** All enhanced markdown files -- election overviews, contest files (single/multi), candidate files, county reference files.

**Example:**
```markdown
## Metadata

| Field | Value |
|-------|-------|
| ID | 550e8400-e29b-41d4-a716-446655440000 |
| Format Version | 1 |
| Election | [May 19, 2026 -- General and Primary Election](../2026-05-19-general-primary.md) |
| Type | Partisan Primary |
| Body | ga-governor |
| Seat | sole |
```

### Pattern 3: Body/Seat Reference in Multi-Contest Files

**What:** County files (multi-contest format) include a per-contest metadata line immediately below the `### Contest Name` heading, before the candidate table.

**When to use:** Every `### Contest` section in county-grouped files.

**Example:**
```markdown
### Board of Education At Large-Post 7

**Body:** bibb-boe | **Seat:** post-7

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|---------------|
| Amy Hamrick Morton | Qualified | No | CEO | 03/02/2026 |
```

### Pattern 4: County Reference File with Governing Bodies

**What:** `data/states/GA/counties/{county}.md` gains a `## Governing Bodies` section with a table mapping Body IDs to their boundary_type and district_identifier lookup rules.

**When to use:** County reference files. Bibb is the worked example; pattern applies to all 159 counties.

**Example:**
```markdown
# Bibb County

| Field | Value |
|-------|-------|
| County | Bibb |
| State | [Georgia](../georgia.md) |
| County Seat | Macon |
| Official Website | [maconbibb.us](https://www.maconbibb.us/) |

## Governing Bodies

| Body ID | Name | boundary_type | Seat Pattern | Notes |
|---------|------|---------------|--------------|-------|
| bibb-boe | Bibb County Board of Education | school_board | at-large (posts 7-8), district-N (1-6) | At-large seats use county boundary |
| bibb-commission | Bibb County Commission | county_commission | district-N | |
| bibb-superior-court | Superior Court, Macon Judicial Circuit | judicial | judge-{surname} | Multi-judge court; seat = incumbent surname |
| bibb-state-court | State Court of Bibb County | judicial | judge-{surname} | |
| macon-water-authority | Macon Water Authority | water_board | at-large, district-N | |
```

### Pattern 5: Global Candidate File

**What:** One markdown file per person in `data/candidates/`. Person-level data at the top, election-keyed sections below.

**When to use:** Every candidate referenced across the pipeline.

**Example:**
```markdown
# Kerry Warren Hatcher

| Field | Value |
|-------|-------|
| ID | 7f3e1a2b-4c5d-... |
| Format Version | 1 |
| Name | Kerry Warren Hatcher |
| Photo URL | -- |
| Email | kerry@votehatcher.com |

## External IDs

| Source | ID |
|--------|----|
| Ballotpedia | -- |
| Open States | -- |

## Links

| Type | URL | Label |
|------|-----|-------|
| website | https://votehatcher.com | votehatcher.com |

## Elections

### May 19, 2026 -- Board of Education At Large-Post 7

| Field | Value |
|-------|-------|
| Election ID | 550e8400-... |
| Contest File | [data/elections/2026-05-19/counties/2026-05-19-bibb.md](../../../data/elections/2026-05-19/counties/2026-05-19-bibb.md) |
| Party | Non-Partisan |
| Occupation | Software Engineer |
| Filing Status | qualified |
| Qualified Date | 03/06/2026 |
| Is Incumbent | No |
```

### Pattern 6: Pydantic StrEnum for Controlled Vocabularies

**What:** Use `enum.StrEnum` for election type, election stage, boundary type, filing status, and link type. These become the single source of truth for vocabulary validation.

**When to use:** Any field with a fixed value set that must match DB constraints.

**Example:**
```python
# Source: existing pattern in src/voter_api/schemas/candidate.py
import enum

class ElectionType(enum.StrEnum):
    GENERAL_PRIMARY = "general_primary"
    GENERAL = "general"
    SPECIAL = "special"
    SPECIAL_PRIMARY = "special_primary"
    MUNICIPAL = "municipal"

class ElectionStage(enum.StrEnum):
    ELECTION = "election"
    RUNOFF = "runoff"
    RECOUNT = "recount"
```

### Anti-Patterns to Avoid

- **Free-text boundary_type in markdown**: Boundary_type must be the exact DB value (`school_board`, not "Board of Education"). No mapping layer -- use the Body/Seat system to resolve to DB values via county reference files.
- **UUID generation in the converter**: The converter must read UUIDs from markdown. If missing = validation error. Never auto-generate UUIDs during conversion.
- **Calendar fields on Election JSONL**: The context decision moves calendar fields (registration_deadline, early_voting dates, etc.) to ElectionEvent. The Election JSONL schema must NOT include them.
- **Email/Website columns in enhanced contest tables**: These fields move to the candidate file. Contest tables only contain: Candidate (link), Status, Incumbent, Occupation, Qualified Date.
- **Party as a metadata table field on multi-contest files**: Party is per-contest for partisan primaries, not a file-level field in county files.
- **Underscore-prefixed schema_version field**: Pydantic v2 treats `_field_name` as a private attribute, excluding it from `model_dump()`, `model_json_schema()`, and serialization. The field MUST be named `schema_version` (no leading underscore).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema documentation generation | Manual markdown maintenance | `model.model_json_schema()` + generation script | Pydantic v2 exposes full JSON Schema from model; descriptions on fields become field docs automatically |
| Vocabulary validation in specs | Regex patterns in prose | `StrEnum` definitions in code | Enums are importable, testable, and auto-documented; inconsistency between spec prose and code is a common drift pattern |
| UUID format validation | Custom UUID regex | `uuid.UUID` type in Pydantic field | Pydantic validates UUID format automatically |
| Field presence requirements in JSONL | Prose rules | Pydantic `Field(...)` (required) vs `Field(default=None)` (optional) | Required vs optional is code, not documentation |

**Key insight:** The format specs are prose for humans; the Pydantic models are the machine-readable contract. Keep them in sync by generating the prose from the models, not the other way around.

## Common Pitfalls

### Pitfall 1: Schema vs. Migration Confusion
**What goes wrong:** The JSONL schemas describe a data model that doesn't match the current DB -- because the candidate-to-person+candidacy refactor and the election-to-ElectionEvent calendar field migration are Phase 2 work. Writing JSONL schemas that match the current DB instead of the Phase 2 target model causes the Phase 2 importer to write data incorrectly.
**Why it happens:** The current `Candidate` model has `election_id` as a direct FK. The JSONL schema must assume the new model (person + candidacy junction).
**How to avoid:** The JSONL schemas define the _target_ data model that Phase 2 will implement. Document prominently that `candidates.jsonl` maps to a new `candidates` table (person entity, no `election_id`) and `candidacies.jsonl` maps to a new `candidacies` table.
**Warning signs:** If `CandidateJSONL` has an `election_id` field, that's the old model bleeding in.

### Pitfall 2: Boundary Type Vocabulary Drift
**What goes wrong:** The boundary type list in `docs/formats/vocabularies/boundary-types.md` drifts from the `BOUNDARY_TYPES` list in `src/voter_api/models/boundary.py`.
**Why it happens:** Specs are written once; models may be updated later.
**How to avoid:** In the vocabulary doc, state the authoritative source: "These values are defined in `src/voter_api/models/boundary.py::BOUNDARY_TYPES`. The vocabulary doc reflects the list at the time of Phase 1. Always check the model for the current list."
**Warning signs:** A boundary type appears in a county reference file but isn't in `BOUNDARY_TYPES`.

### Pitfall 3: CONTEXT.md Decision says "Phase 2 implements" but Phase 1 must spec it
**What goes wrong:** "Migration script" and "backfill CLI command" are Phase 2 implementations -- but Phase 1 must write the rules those tools follow. If the spec is vague (e.g., "add missing fields"), the Phase 2 implementer must make decisions that should have been locked in Phase 1.
**Why it happens:** Easy to confuse "spec the rule" vs "implement the tool".
**How to avoid:** Every migration rule must be concrete enough that an implementer doesn't need to make judgment calls. E.g., "If a county contest has no Body/Seat line, the migration script infers it from the contest name using the governing body table in the county reference file. If no match, the migration script emits a warning and leaves the Body/Seat line blank."
**Warning signs:** Migration rules with words like "as appropriate" or "if possible" -- these are under-specified.

### Pitfall 4: Format Version Not On All File Types
**What goes wrong:** The `| Format Version | 1 |` row is added to contest files but forgotten on overview files, candidate files, or county reference files.
**Why it happens:** Each file type is specced in a separate doc; easy to miss one.
**How to avoid:** The CONTEXT decision is explicit: "All markdown file types get a format version." Checklist in each format spec must include a Format Version row requirement.

### Pitfall 5: Seat ID Format Inconsistency
**What goes wrong:** Some county reference files use `post-7`, others use `Post-7`, others `at-large-post-7`. The converter can't map these reliably.
**Why it happens:** This is "Claude's Discretion" -- which means it needs to be decided once and documented as the canonical format.
**How to avoid:** Establish the seat slug rules in Phase 1: lowercase, hyphens, no spaces. Patterns: `sole` (single-seat office), `at-large` (at-large without number), `post-N` (numbered post/position), `district-N` (district seat), `judge-{surname}` (judicial). Document in `docs/formats/vocabularies/`.

### Pitfall 6: Circular Dependency Between Specs
**What goes wrong:** The election-overview spec references the single-contest spec for Body/Seat fields, the single-contest spec references the county reference spec for Body IDs, and the county reference spec references the boundary-types vocabulary. If any one is under-specified, all downstream specs are blocked.
**Why it happens:** The specs have a dependency chain: vocabularies -> county reference -> contest files -> overview file.
**How to avoid:** Write specs in dependency order: vocabularies first, then county reference, then contest file formats, then overview. Each spec can reference finished specs without circularity.

### Pitfall 7: Pydantic v2 Private Field Trap
**What goes wrong:** Using `_schema_version` as a field name causes the field to be treated as a Pydantic v2 private attribute. It is excluded from `model_dump()`, `model_json_schema()`, serialization to JSON, and validation. The JSONL output silently omits the version field.
**Why it happens:** Pydantic v2 interprets any attribute starting with `_` as a `PrivateAttr`, not a model field. This is different from Pydantic v1 behavior.
**How to avoid:** Name the field `schema_version` (no leading underscore). The CONTEXT.md mentions `"_schema_version": 1` but the Pydantic implementation must use `schema_version` for the field to function correctly.
**Warning signs:** `model_json_schema()` output does not include `schema_version` in the `properties` dict. `model_dump()` output is missing the version field.

## Code Examples

Verified patterns from existing project code:

### StrEnum Pattern (from src/voter_api/schemas/candidate.py)
```python
import enum

class FilingStatus(enum.StrEnum):
    QUALIFIED = "qualified"
    WITHDRAWN = "withdrawn"
    DISQUALIFIED = "disqualified"
    WRITE_IN = "write_in"
```

### Pydantic v2 BaseModel with Field descriptions (from existing schemas)
```python
from pydantic import BaseModel, Field
import uuid
from datetime import date

class CandidacyJSONL(BaseModel):
    """JSONL record for a candidacy (candidate-election junction).

    Links a candidate (person entity) to a specific election contest.
    Contest-specific fields live here; person-level fields live in CandidateJSONL.
    """

    schema_version: int = Field(default=1, description="Schema version integer.")
    id: uuid.UUID = Field(description="UUID of this candidacy record. From markdown metadata.")
    candidate_id: uuid.UUID = Field(description="UUID of the candidate (person). From candidate file metadata.")
    election_id: uuid.UUID = Field(description="UUID of the election contest. From contest file metadata.")
    party: str | None = Field(default=None, description="Party affiliation for this contest. Null for non-partisan.")
    filing_status: str = Field(default="qualified", description="One of: qualified, withdrawn, disqualified, write_in.")
    is_incumbent: bool = Field(default=False, description="Whether the candidate is the incumbent for this seat.")
    occupation: str | None = Field(default=None, description="Occupation as listed in SOS data. Title case.")
    qualified_date: date | None = Field(default=None, description="Date candidate qualified. ISO 8601.")
    ballot_order: int | None = Field(default=None, description="Position on ballot. Set post-election.")
    sos_ballot_option_id: str | None = Field(default=None, description="SOS ballot option ID from results feed.")
```

### model_json_schema() for doc generation
```python
# Used in tools/generate_jsonl_docs.py
from voter_api.schemas.jsonl import ElectionJSONL

schema = ElectionJSONL.model_json_schema()
# schema["properties"] contains all fields with their "description" values
# schema["required"] lists required fields
# Render to markdown table for docs/formats/jsonl/elections.md
```

### Existing Boundary Types (from src/voter_api/models/boundary.py)
```python
BOUNDARY_TYPES = [
    "congressional", "state_senate", "state_house", "judicial", "psc",
    "county", "county_commission", "school_board", "city_council",
    "municipal_school_board", "water_board", "super_council",
    "super_commissioner", "super_school_board", "fire_district",
    "county_precinct", "municipal_precinct", "us_senate",
]
```

### Existing CandidateLink Types (from src/voter_api/models/candidate.py)
```python
# DB constraint -- these are the valid link_type values
"link_type IN ('website', 'campaign', 'facebook', 'twitter', 'instagram', 'youtube', 'linkedin', 'other')"
```

### Existing Election Type (from src/voter_api/lib/election_tracker/ingester.py)
```python
# Current definition -- will be replaced with StrEnum in JSONL schemas
ElectionType = Literal["special", "general", "primary", "runoff"]
# New JSONL vocabulary splits into election_type + election_stage:
# election_type: general_primary, general, special, special_primary, municipal
# election_stage: election, runoff, recount
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| STATEWIDE-FORMAT.md + SPECIAL-ELECTION-FORMAT.md + COUNTY-FORMAT.md (3 contest formats) | single-contest.md + multi-contest.md (2 formats) | Phase 1 | Simpler; special elections and statewide use the same single-contest format |
| Two overview variants (General/Primary, Special Election) | Unified overview with optional sections | Phase 1 | One spec to maintain; sections present/absent based on content |
| Candidate tied to single election via `election_id` | Candidate = person entity; Candidacy = junction table | Phase 1 (contract), Phase 2 (migration) | Enables cross-election candidate tracking |
| Calendar fields on Election model | Calendar fields on ElectionEvent model | Phase 1 (contract), Phase 2 (migration) | One set of dates per event, not duplicated across all contests |
| Free-text district field on Election | boundary_type + district_identifier from Body/Seat reference | Phase 1 (contract), Phase 2 (importer) | Deterministic district resolution; no AI needed in converter |
| Ad-hoc email/website in contest tables | Email/website in global candidate file only | Phase 1 | Person-level data in one place; contest table is smaller |
| Four separate format specs in data/elections/formats/ | Centralized in docs/formats/ with markdown/, jsonl/, vocabularies/, specs/ | Phase 1 | Single source of truth; auto-generated JSONL docs from Pydantic models |
| `ElectionType = Literal["special", "general", "primary", "runoff"]` | Two-field approach: `election_type` (5 values) + `election_stage` (3 values) | Phase 1 | Cleanly separates election category from resolution mechanism |

**Deprecated/outdated:**
- `data/elections/formats/STATEWIDE-CONTEST-FORMAT.md`: Superseded by `docs/formats/markdown/single-contest.md`
- `data/elections/formats/SPECIAL-ELECTION-CONTEST-FORMAT.md`: Merged into `docs/formats/markdown/single-contest.md`
- `data/elections/formats/COUNTY-FORMAT.md`: Superseded by `docs/formats/markdown/multi-contest.md`
- `data/elections/formats/ELECTION-OVERVIEW-FORMAT.md`: Superseded by `docs/formats/markdown/election-overview.md`

## Open Questions

1. **Seat ID for judicial contests**
   - What we know: Bibb has 4 Superior Court judges and 2 State Court judges; contests are named by incumbent surname (e.g., "State Court Judge (Hanson)")
   - What's unclear: Should seat ID be `judge-hanson` (surname-based, changes when judge changes) or `seat-1` (numeric, stable but arbitrary)?
   - Recommendation: Use `judge-{slug}` for judicial where the seat is defined by the seat holder's name (consistent with SOS naming). Document that judicial seat IDs change when a new judge takes the seat, and that's expected behavior.

2. **Backfill matching rules for elections with the same name on different dates**
   - What we know: The natural key for elections is `(name, election_date)` per the DB unique constraint.
   - What's unclear: Some SOS names are very similar across years (e.g., "Governor" appears every 4 years). Is `(name_sos, election_date)` sufficient, or do we need `(contest_file_path, election_date)`?
   - Recommendation: Use `(name_sos, election_date)` as the backfill matching key. Document that if multiple DB records match (shouldn't happen given the unique constraint), the backfill emits an error and requires manual resolution.

3. **County reference file Body/Seat coverage for Phase 1**
   - What we know: Phase 1 specs the format and populates Bibb as the worked example. Populating all 159 counties is deferred.
   - What's unclear: The Bibb example needs to cover the entire Bibb County file (12 contests across BOE, commission, judicial, water authority) to validate the spec is complete.
   - Recommendation: Populate Bibb completely -- all governing bodies with all seat patterns. This stress-tests the format against at-large, district, and judicial seat types.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py -x` |
| Full suite command | `uv run pytest tests/unit/test_schemas/ -v` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FMT-04 | `ElectionJSONL` validates a complete election record | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_election_jsonl_valid -x` | Wave 0 |
| FMT-05 | `CandidateJSONL` validates a person record; `CandidacyJSONL` validates a junction record | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_candidate_and_candidacy_jsonl -x` | Wave 0 |
| FMT-06 | `schema_version` field is required and defaults to 1 in all four JSONL models | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_schema_version_present -x` | Wave 0 |
| FMT-04 | `ElectionJSONL` rejects records with unknown `election_type` or `election_stage` values | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_election_type_validation -x` | Wave 0 |
| FMT-05 | `CandidacyJSONL` rejects records with unknown `filing_status` values | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_candidacy_filing_status_validation -x` | Wave 0 |
| FMT-01, FMT-02, FMT-03 | Markdown format specs validated by inspection (no automated test for prose docs) | manual | N/A | N/A |

Note: FMT-01, FMT-02, FMT-03 are prose format specifications. Correctness is verified by human review of the spec docs and the worked Bibb example file.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py -x`
- **Per wave merge:** `uv run pytest tests/unit/test_schemas/ -v`
- **Phase gate:** Full unit test suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_schemas/test_jsonl_schemas.py` -- covers FMT-04, FMT-05, FMT-06; test the four JSONL Pydantic models
- [ ] `src/voter_api/schemas/jsonl/__init__.py` -- new package, doesn't exist yet
- [ ] `src/voter_api/schemas/jsonl/enums.py` -- shared StrEnum definitions
- [ ] `src/voter_api/schemas/jsonl/election_event.py` -- `ElectionEventJSONL` model
- [ ] `src/voter_api/schemas/jsonl/election.py` -- `ElectionJSONL` model
- [ ] `src/voter_api/schemas/jsonl/candidate.py` -- `CandidateJSONL` model
- [ ] `src/voter_api/schemas/jsonl/candidacy.py` -- `CandidacyJSONL` model

## Sources

### Primary (HIGH confidence)
- Existing `src/voter_api/models/candidate.py` -- current Candidate + CandidateLink ORM fields and constraints
- Existing `src/voter_api/models/election.py` -- current Election ORM fields, indexes, and constraints
- Existing `src/voter_api/models/election_event.py` -- current ElectionEvent ORM (minimal: event_date, event_name, event_type)
- Existing `src/voter_api/models/boundary.py` -- canonical `BOUNDARY_TYPES` list and Boundary model
- Existing `src/voter_api/models/base.py` -- UUIDMixin, TimestampMixin, SoftDeleteMixin patterns
- Existing `src/voter_api/schemas/candidate.py` -- `FilingStatus` StrEnum and `LinkType` StrEnum patterns
- Existing `src/voter_api/schemas/election.py` -- `ElectionCreateRequest` / `ElectionSummary` Pydantic patterns
- Existing `src/voter_api/lib/election_tracker/ingester.py` -- current `ElectionType` Literal definition
- Existing `data/elections/formats/` -- 4 current format specs (content basis for enhanced specs)
- Existing `data/elections/2026-05-19/` and `2026-03-17/` -- 15 statewide + 159 county stubs + 4 special election files (concrete editing scope)
- Existing `data/states/GA/counties/bibb.md` -- current county reference file format (metadata-only, no governing bodies yet)
- `data/elections/2026-05-19/counties/2026-05-19-bibb.md` -- concrete Bibb County file showing all 12 contests
- `data/elections/2026-05-19/2026-05-19-general-primary.md` -- overview file showing unified format structure
- `data/elections/2026-05-19/2026-05-19-governor.md` -- statewide contest file showing partisan primary structure
- `.planning/milestones/v1.0-phases/01-data-contracts/01-CONTEXT.md` -- all implementation decisions (locked)

### Secondary (MEDIUM confidence)
- SOS results JSON files in `data/results/` -- 14 files showing all election type patterns (special, runoff, recount, PSC primary, municipal)
- Existing `tests/unit/test_schemas/` -- test pattern for Pydantic schema tests
- `pyproject.toml` -- confirmed no JSONL library or markdown parser dependency (none needed for Phase 1)

### Tertiary (LOW confidence)
- None -- all findings derived from codebase inspection

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all tools already in project
- Architecture: HIGH -- derived from CONTEXT.md locked decisions + codebase inspection
- Pitfalls: HIGH -- derived from specific model mismatches (current vs. target schema) and verified Pydantic v2 behavior (underscore prefix trap confirmed in plan 01-02 fix)
- JSONL schema field mapping: HIGH -- ORM models are the authoritative source, read directly

**Research date:** 2026-03-14
**Valid until:** 2026-06-14 (stable spec domain; no external APIs)
