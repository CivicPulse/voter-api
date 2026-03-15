# Multi-Contest Format Specification

This document defines the format for multi-contest county files. A multi-contest file groups all local races for a single county on a single election date into one file.

**Replaces:** `data/elections/formats/COUNTY-FORMAT.md`

## File Location

```
data/elections/{election-date}/counties/{election-date}-{county}.md
```

Examples:
- `data/elections/2026-05-19/counties/2026-05-19-bibb.md`
- `data/elections/2026-05-19/counties/2026-05-19-fulton.md`

County names are lowercase in filenames.

## Structure

```markdown
# {County Name} County -- Local Elections

## Metadata

| Field | Value |
|-------|-------|
| ID | {uuid} |
| Format Version | 1 |
| Election | [{Election Display Name}]({overview-file}.md) |
| Type | {election_type value} |
| Contests | {number} |
| Candidates | {number} |

## Statewide & District Races

Voters in {County Name} County will also see the following statewide and district races on the ballot.

| Race | Election |
|------|----------|
| {Contest Name} | [{Election Type}]({contest-file}.md) |

## Contests

### {Contest Name in Title Case}

**Body:** {body-id} | **Seat:** {seat-id}

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| [{Name}]({candidate-file}.md) | Qualified | Yes/No | {Occupation} | MM/DD/YYYY |

### {Next Contest Name}

**Body:** {body-id} | **Seat:** {seat-id}

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| [{Name}]({candidate-file}.md) | Qualified | Yes/No | {Occupation} | MM/DD/YYYY |

## Data Source

- Candidate list: `data/new/{CSV_FILENAME}`
```

## Field Reference

### File-Level Metadata Table

| Field | Required | Description |
|-------|----------|-------------|
| ID | Yes | UUID for this county's local elections grouping. Source of truth for identity. Converter error if missing. |
| Format Version | Yes | Integer version of this format specification. Starts at `1`. |
| Election | Yes | Markdown link to the parent election overview file. |
| Type | Yes | Election type from the [election-types vocabulary](../vocabularies/election-types.md). Typically matches the event type. |
| Contests | Yes | Numeric count of distinct contest headings in the file. |
| Candidates | Yes | Numeric count of all candidate rows across all contests. |

### Per-Contest Metadata

Each contest section has a **Body/Seat metadata line** immediately below the `### Contest Name` heading and before the candidate table:

```markdown
### Board of Education At Large-Post 7

**Body:** bibb-boe | **Seat:** post-7
```

This line provides the district linkage for each individual contest. The converter parses it to resolve `boundary_type` and `district_identifier` via the county reference file.

| Component | Description |
|-----------|-------------|
| Body | Body ID from the [seat-ids vocabulary](../vocabularies/seat-ids.md). Identifies the governing body. |
| Seat | Seat ID from the [seat-ids vocabulary](../vocabularies/seat-ids.md). Identifies the specific seat within that body. |

### Candidate Table Columns

The enhanced format uses 5 columns (reduced from the previous 7):

| Column | Description |
|--------|-------------|
| Candidate | Full name, linked to the global candidate file: `[{Name}]({candidate-file}.md)` |
| Status | Human-readable status: `Qualified`, `Withdrawn`, `Disqualified`, `Write-In` |
| Incumbent | `Yes` or `No` |
| Occupation | Title Case with uppercase acronyms (CEO, CPA, LLC) |
| Qualified Date | Date in `MM/DD/YYYY` format |

**Dropped columns:** Email and Website are no longer in contest tables. They live in the global candidate file (person-level data).

## Statewide & District Races Section

This section cross-references statewide and district contest files that voters in this county will also see on their ballot. It helps provide a complete picture of what a voter in this county can expect.

```markdown
## Statewide & District Races

Voters in Bibb County will also see the following statewide and district races on the ballot.

| Race | Election |
|------|----------|
| Governor | [Partisan Primary](../2026-05-19-governor.md) |
| U.S. House -- District 2 | [Partisan Primary](../2026-05-19-us-house-district-02.md) |
```

## Content Rules

### Contest Names

- **Title Case** for all contest names
- Lowercase articles and prepositions: "of", "at", "for", "in", "to", "the", "and", "or", "a" (unless at the start)
- Keep acronyms capitalized: BOE, PSC, PUD, EMC
- Parenthetical suffixes preserved as written (e.g., "State Court Judge (Hanson)")

Examples:
- `Board of Education At Large-Post 7`
- `Civil/Magistrate Court Judge`
- `State Court Judge (Hanson)`
- `Macon Water Authority-At Large`
- `Judge of Superior Court, Macon Judicial Circuit - Mincey`

### Empty Values

- Use `--` (em-dash, U+2014) for missing field values
- Never use `(none)`, `N/A`, `-`, or `--` (double hyphen)

### Occupations

- Title Case with uppercase acronyms: CEO, CFO, CPA, LLC, LLP
- Expand abbreviations: "Ret Educator" becomes "Retired Educator"

### Candidate Name Links

- Every candidate name in the table should link to the candidate's global file
- Format: `[{Full Name}](../../../candidates/{name-slug}-{8-char-hash}.md)`
- If no candidate file exists yet, use the unlinked name

### Metadata Counts

- **Contests**: Count the number of `### Contest` headings in the file
- **Candidates**: Count all candidate rows across all contests
- Update both counts whenever contests or candidates are added/removed

## Validation Checklist

- [ ] ID is a valid UUID
- [ ] Format Version is present and set to `1`
- [ ] Election links to the correct overview file
- [ ] Type is a valid election_type value
- [ ] Contest and Candidate counts match actual content
- [ ] Every contest heading is in Title Case
- [ ] Every contest has a `**Body:** ... | **Seat:** ...` metadata line
- [ ] Candidate tables have exactly 5 columns (Candidate, Status, Incumbent, Occupation, Qualified Date)
- [ ] No Email or Website columns in candidate tables
- [ ] All empty values use em-dash (U+2014)
- [ ] Occupations use proper Title Case with uppercase acronyms
- [ ] No trailing whitespace
