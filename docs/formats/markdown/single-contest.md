# Single-Contest Format Specification

This document defines the format for single-contest election files. A single-contest file covers one office -- either a statewide/federal race or an individual special election contest. This unified format replaces the previous split between statewide and special election formats.

**Replaces:** `data/elections/formats/STATEWIDE-CONTEST-FORMAT.md` and `data/elections/formats/SPECIAL-ELECTION-CONTEST-FORMAT.md`

## File Location

```
data/elections/{election-date}/{election-date}-{contest-slug}.md
```

Examples:
- `data/elections/2026-05-19/2026-05-19-governor.md` (statewide)
- `data/elections/2026-05-19/2026-05-19-us-house-district-01.md` (federal)
- `data/elections/2026-03-17/2026-03-17-bibb-commission-district-5.md` (special election)

Contest slugs use lowercase with hyphens. District numbers are zero-padded in filenames (`district-01`) but natural in headings (`District 1`).

## Structure

### Statewide/Federal Partisan Primary

```markdown
# {Contest Display Name}

## Metadata

| Field | Value |
|-------|-------|
| ID | {uuid} |
| Format Version | 1 |
| Election | [{Election Display Name}]({overview-file}.md) |
| Type | {election_type value} |
| Stage | {election_stage value} |
| Body | {body-id} |
| Seat | {seat-id} |
| Name (SOS) | {exact SOS contest name, without party suffix} |

## Republican Primary

**Contest Name (SOS):** {SOS Contest Name} (R)

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| [{Name}]({candidate-file}.md) | Qualified | Yes/No | {Occupation} | MM/DD/YYYY |

## Democrat Primary

**Contest Name (SOS):** {SOS Contest Name} (D)

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| [{Name}]({candidate-file}.md) | Qualified | Yes/No | {Occupation} | MM/DD/YYYY |

## Data Source

- Candidate list: `data/new/{CSV_FILENAME}`
```

### Non-Partisan / General / Jungle Primary

```markdown
# {Contest Display Name}

## Metadata

| Field | Value |
|-------|-------|
| ID | {uuid} |
| Format Version | 1 |
| Election | [{Election Display Name}]({overview-file}.md) |
| Type | {election_type value} |
| Stage | {election_stage value} |
| Body | {body-id} |
| Seat | {seat-id} |
| Name (SOS) | {exact SOS contest name} |

## Candidates

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| [{Name}]({candidate-file}.md) | Qualified | Yes/No | {Occupation} | MM/DD/YYYY |

## Data Source

- Candidate list: `data/new/{CSV_FILENAME}`
```

### Special Election Contest

```markdown
# {Locality} -- {Office Title}

## Metadata

| Field | Value |
|-------|-------|
| ID | {uuid} |
| Format Version | 1 |
| Election | [{Election Display Name}]({overview-file}.md) |
| Type | special |
| Stage | {election_stage value} |
| Body | {body-id} |
| Seat | {seat-id} |
| Name (SOS) | {exact SOS contest name or "N/A -- municipal qualifying"} |
| Purpose | {Brief description of vacancy} |
| Eligibility | {Who may vote} |

## Candidates

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| [{Name}]({candidate-file}.md) | Qualified | Yes/No | {Occupation} | MM/DD/YYYY |

### Candidate Bios

**{Candidate Name}** -- {Brief biographical paragraph}

## Data Source

- Candidate list: `data/new/{CSV_FILENAME}`
- [{Source Title}]({URL}) -- {Publication}
```

## Field Reference

### Metadata Table

| Field | Required | Description |
|-------|----------|-------------|
| ID | Yes | UUID for this contest. Source of truth for the Election identity. Converter error if missing. |
| Format Version | Yes | Integer version of this format specification. Starts at `1`. |
| Election | Yes | Markdown link to the parent election overview file. |
| Type | Yes | Election type from the [election-types vocabulary](../vocabularies/election-types.md). The specific type for this contest (not the event-level broadest type). |
| Stage | Yes | Election stage from the [election-types vocabulary](../vocabularies/election-types.md). Defaults to `election`. |
| Body | Yes | Body ID from the [seat-ids vocabulary](../vocabularies/seat-ids.md). Identifies the governing body (e.g., `ga-governor`, `bibb-boe`). |
| Seat | Yes | Seat ID from the [seat-ids vocabulary](../vocabularies/seat-ids.md). Identifies the specific seat (e.g., `sole`, `post-7`, `district-3`). |
| Name (SOS) | Yes | Exact SOS contest name string. For partisan primaries, this is the base name without party suffix (the party suffix appears on the `**Contest Name (SOS):**` line within each party section). |
| Party | Optional | Present only for partisan primaries. Omitted for non-partisan, general, and jungle races. |
| Purpose | Special elections only | Brief description of why the seat is vacant (resignation, death, etc.). |
| Eligibility | Special elections only | Description of who is eligible to vote (e.g., "Registered voters in Bibb County"). |

### Body/Seat Resolution

The `Body` and `Seat` fields are the mechanism for district linkage. The converter resolves them as follows:

1. Look up the Body ID in the appropriate county reference file (see [county-reference.md](county-reference.md))
2. The county reference file maps the Body ID to a `boundary_type` value from the [boundary-types vocabulary](../vocabularies/boundary-types.md)
3. The Seat ID determines the `district_identifier`

**Important:** `boundary_type` and `district_identifier` do **not** appear directly in the markdown. They are derived by the converter from the Body/Seat reference. This keeps the markdown human-readable while maintaining machine-resolvable district references.

### Candidate Table Columns

The enhanced format uses 5 columns (reduced from the previous 7):

| Column | Description |
|--------|-------------|
| Candidate | Full name, linked to the global candidate file: `[{Name}]({candidate-file}.md)` |
| Status | Human-readable status: `Qualified`, `Withdrawn`, `Disqualified`, `Write-In` |
| Incumbent | `Yes` or `No` |
| Occupation | Title Case with uppercase acronyms (CEO, CPA, LLC) |
| Qualified Date | Date in `MM/DD/YYYY` format |

**Dropped columns:** Email and Website are no longer in contest tables. They live in the global candidate file (person-level data, not contest-level data).

## Internal Structure Rules

### Partisan Primaries

- Each party gets its own H2 section: `## Republican Primary`, `## Democrat Primary`
- Each party section includes `**Contest Name (SOS):** {name} ({party letter})` on its own line before the candidate table
- Candidates are grouped by party under the appropriate section

### Non-Partisan / General / Jungle

- A single `## Candidates` section contains all candidates
- No party sections, no `**Contest Name (SOS):**` lines (the SOS name is in the metadata table)
- If party affiliation is relevant (e.g., general election), add a Party column to the candidate table

### Special Elections

- H1 uses the format `{Locality} -- {Office Title}` (em-dash separator)
- `Purpose` and `Eligibility` fields are required in the metadata table
- `### Candidate Bios` section follows the candidate table (optional for non-special elections)
- Narrative-only contests (municipal qualifying) may use a `## Background` section instead of a candidate table

## Content Rules

### Contest Display Names

- Title Case for all contest names
- Use "U.S." with periods for federal offices (e.g., `U.S. Senate`, `U.S. House -- District 1`)
- Use "PSC" in filenames but spell out "Public Service Commission" in headings
- District numbers: zero-padded in filenames (`district-01`), natural in headings (`District 1`)

### Empty Values

- Use `--` (em-dash, U+2014) for missing field values
- Never use `(none)`, `N/A`, `-`, or `--` (double hyphen)

### Website URLs (in Data Source section)

- Display text `[text]` is lowercase
- URL in parentheses must be lowercase

### Occupations

- Title Case with uppercase acronyms: CEO, CFO, CPA, LLC, LLP
- Expand abbreviations when part of a phrase: "Ret Educator" becomes "Retired Educator"

### Candidate Name Links

- Every candidate name in the table should link to the candidate's global file
- Format: `[{Full Name}](../../candidates/{name-slug}-{8-char-hash}.md)`
- If no candidate file exists yet, use the unlinked name

## Validation Checklist

- [ ] ID is a valid UUID
- [ ] Format Version is present and set to `1`
- [ ] Election links to the correct overview file
- [ ] Type is a valid election_type value
- [ ] Stage is a valid election_stage value
- [ ] Body is a valid Body ID
- [ ] Seat is a valid Seat ID
- [ ] Name (SOS) preserves the exact SOS string
- [ ] Candidate table has exactly 5 columns (Candidate, Status, Incumbent, Occupation, Qualified Date)
- [ ] No Email or Website columns in candidate table
- [ ] Every party section includes `**Contest Name (SOS):**` line (partisan primaries only)
- [ ] All empty values use em-dash (U+2014)
- [ ] Occupations use proper Title Case with uppercase acronyms
- [ ] Special elections include Purpose and Eligibility metadata
