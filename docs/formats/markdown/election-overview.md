# Election Overview Format Specification

This document defines the format for election overview files. An overview file represents an **ElectionEvent** -- a single election day that may group multiple contests. This unified format replaces the previous two-variant split (General/Primary overview and Special Election overview).

**Replaces:** `data/elections/formats/ELECTION-OVERVIEW-FORMAT.md`

## File Location

```
data/elections/{election-date}/{election-date}-{type-slug}.md
```

Examples:
- `data/elections/2026-05-19/2026-05-19-general-primary.md`
- `data/elections/2026-03-17/2026-03-17-special-election.md`

## Structure

```markdown
# {Month D, YYYY} -- {Election Display Name}

## Metadata

| Field | Value |
|-------|-------|
| ID | {uuid} |
| Format Version | 1 |
| Name (SOS) | {exact SOS election name} |
| Date | {YYYY-MM-DD} |
| Type | {election_type value} |
| Stage | {election_stage value, default: election} |

## Calendar

| Field | Date | Source |
|-------|------|--------|
| Registration Deadline | {YYYY-MM-DD} | {source} |
| Early Voting Start | {YYYY-MM-DD} | {source} |
| Early Voting End | {YYYY-MM-DD} | {source} |
| Absentee Request Deadline | {YYYY-MM-DD} | {source} |
| Qualifying Period Start | {YYYY-MM-DD} | {source} |
| Qualifying Period End | {YYYY-MM-DD} | {source} |
| Election Day | {YYYY-MM-DD} | {source} |

## Data Sources

- SOS Results Feed: {URL or TBD}
- Candidate list: `data/new/{CSV_FILENAME}`
- Election calendar: `data/new/{PDF_FILENAME}`

## Statewide Races

### [{Contest Name}]({contest-file}.md)

| Republican | Democrat |
|------------|----------|
| {count} | {count} |

## Federal Races

### [{Contest Name}]({contest-file}.md)

| Republican | Democrat |
|------------|----------|
| {count} | {count} |

### U.S. House of Representatives

| District | Republican | Democrat |
|----------|------------|----------|
| [{N}]({contest-file}.md) | {count} | {count} |

## State Legislative Races

| Chamber | Contests |
|---------|----------|
| State House | {count} |
| State Senate | {count} |

## Local Elections

| County | Contests | Candidates |
|--------|----------|------------|
| [{County Name}](counties/{county-file}.md) | {count} | {count} |

## Candidate Breakdown

| Party | Candidates |
|-------|------------|
| Republican | {count} |
| Democrat | {count} |
| Non-Partisan | {count} |

## Validation Checklist

- [ ] ID is a valid UUID
- [ ] Format Version is present and set to `1`
- [ ] Name (SOS) matches the exact SOS election name string
- [ ] Date is ISO 8601 format (YYYY-MM-DD)
- [ ] Type is a valid election_type value
- [ ] Stage is a valid election_stage value
- [ ] All Calendar dates are ISO 8601 with sources
- [ ] All contest links resolve to existing files
- [ ] Candidate counts match individual contest files
```

## Field Reference

### Metadata Table

| Field | Required | Description |
|-------|----------|-------------|
| ID | Yes | UUID for this election event. Source of truth for the ElectionEvent identity. Converter error if missing. |
| Format Version | Yes | Integer version of this format specification. Starts at `1`. |
| Name (SOS) | Yes | The exact election name string as it appears in SOS data. Preserved verbatim for voter recognition. |
| Date | Yes | Election day date in ISO 8601 format (`YYYY-MM-DD`). |
| Type | Yes | Election type from the [election-types vocabulary](../vocabularies/election-types.md). One of: `general_primary`, `general`, `special`, `special_primary`, `municipal`. For events grouping multiple contest types, use the broadest applicable type per the priority rule. |
| Stage | Yes | Election stage from the [election-types vocabulary](../vocabularies/election-types.md). One of: `election` (default), `runoff`, `recount`. |

**Note on Body/Seat:** Overview files represent an election event that groups multiple contests. Body and Seat are per-contest metadata and live on individual contest files, not on the overview. The overview does not have a Body or Seat.

### Calendar Table

All dates in the Calendar table use ISO 8601 format (`YYYY-MM-DD`). This differs intentionally from contest files, which use human-readable date formats -- overview files are more data-oriented.

| Field | Description |
|-------|-------------|
| Registration Deadline | Last day to register to vote in this election |
| Early Voting Start | First day of early/advance voting |
| Early Voting End | Last day of early/advance voting |
| Absentee Request Deadline | Last day to request an absentee ballot |
| Qualifying Period Start | First day candidates may qualify for the ballot |
| Qualifying Period End | Last day candidates may qualify for the ballot |
| Election Day | The election day itself |

The Source column attributes the date to its origin (e.g., "SOS Election Calendar PDF", "O.C.G.A. section 21-2-385").

### Data Sources Section

- **SOS Results Feed**: URL for the real-time results feed. Marked as "TBD" until the URL becomes available (typically days before the election). The converter propagates this URL to every election JSONL record derived from this event.
- **CSV/PDF sources**: Backtick-formatted file paths to the raw source data files.

## Optional Sections

Sections are included based on what contests exist for this election event -- not based on election type. Any combination of the following sections may be present:

| Section | When Included |
|---------|---------------|
| Statewide Races | Event includes statewide offices (Governor, SOS, AG, etc.) |
| Federal Races | Event includes federal offices (US Senate, US House) |
| State Legislative Races | Event includes state house or senate races |
| Local Elections | Event includes county-level local contests |
| Candidate Breakdown | Useful for events with partisan primaries; optional for small events |

For special elections with a small number of contests, inline candidate tables may be used instead of the party count tables:

```markdown
## Contests

### [{Locality} -- {Office Title}]({contest-file}.md)

**Purpose:** {Brief explanation of vacancy}

| Candidate | Incumbent | Occupation |
|-----------|-----------|------------|
| {Name} | Yes/No | {Occupation} |
```

## Content Rules

### H1 Heading

Format: `{Month D, YYYY} -- {Election Display Name}`

- Use an em-dash (U+2014) between the date and name
- Date uses the human-readable "Month D, YYYY" format (e.g., "May 19, 2026")
- The display name is a human-friendly label (e.g., "General and Primary Election", "Special Election")

### County Table

- Sorted alphabetically by county name
- Contests and Candidates columns contain numeric counts

### Links

- All contest file links must resolve to existing files
- Use relative paths from the overview file's directory
