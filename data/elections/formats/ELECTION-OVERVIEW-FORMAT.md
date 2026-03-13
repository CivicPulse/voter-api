# Election Overview File Format — Canonical Reference

This document defines the exact structure and conventions for top-level election summary files. These files serve as the entry point for an election date, linking to all individual contest files and providing aggregate statistics.

There are two variants:
- **General/Primary Overview** — for regular election cycles with partisan primaries
- **Special Election Overview** — for special elections with non-partisan contests

## File Naming Convention

```
data/elections/{election-date}/{election-date}-{type}.md
```

Examples:
- `2026-05-19-general-primary.md`
- `2026-03-17-special-election.md`

## Common Structure (Both Variants)

Both variants share these top-level elements:

```markdown
# {Month D, YYYY} — {Election Type}

**Date:** {Month D, YYYY}
**Type:** {Election Type Description}
**Candidates:** {count} {qualifier}

## Election Calendar

| Field | Date | Source |
|-------|------|--------|
| {milestone} | {YYYY-MM-DD} | {source} |

...

## Data Sources

- Candidate list: `data/new/{CSV_FILENAME}`
- Election calendar: `data/new/{PDF_FILENAME}`
```

### Header Format

- **H1**: `{Month D, YYYY} — {Election Type}` (full date with em-dash)
- **Bold key-value pairs** for Date, Type, and Candidates (not a table — overview metadata is kept lightweight)
- Candidate count includes qualifier: `10 qualified`, `2,319 (plus 14 withdrawn, 3 disqualified)`

### Election Calendar Table

| Column | Format | Description |
|--------|--------|-------------|
| Field | Human-readable milestone name | e.g., "Qualifying Period Start", "Election Day" |
| Date | ISO 8601 (`YYYY-MM-DD`) | Different from contest files, which use `Month D, YYYY` |
| Source | Attribution | e.g., "SOS Election Calendar PDF", "O.C.G.A. § 21-2-385" |

> **Note:** Overview files use ISO dates in the calendar table, while individual contest files use human-readable dates (`Month D, YYYY`). This is intentional — overview files are more data-oriented, contest files are more reader-oriented.

### Data Sources Section

- List all source files with backtick-formatted paths
- Include both CSV (candidate data) and PDF (calendar/metadata) sources

---

## Variant A: General/Primary Overview

Used for regular election cycles with partisan primaries across statewide, federal, and local contests.

### Additional Sections

```markdown
## Statewide Races

### [{Contest Name}]({contest-file}.md)

| Republican | Democrat |
|-----------|----------|
| {count} | {count} |

## Federal Races

### [{Contest Name}]({contest-file}.md)

| Republican | Democrat |
|-----------|----------|
| {count} | {count} |

### U.S. House of Representatives

| District | Republican | Democrat |
|----------|-----------|----------|
| [{N}]({contest-file}.md) | {count} | {count} |

## State Legislative Races

| Chamber | Contests |
|---------|----------|
| State House | {count} |
| State Senate | {count} |

## Local Elections

{Brief description}

| County | Contests | Candidates |
|--------|----------|------------|
| [{County Name}](counties/{county-file}.md) | {count} | {count} |

## Candidate Breakdown by Party (Qualified Only)

| Party | Candidates |
|-------|-----------|
| Republican | {count} |
| Democrat | {count} |
| Non-Partisan | {count} |
```

### Content Rules for General/Primary

- **Statewide Races**: One H3 per contest, linked to individual contest file, with party count table
- **Federal Races**: Same format, with U.S. House in a combined district table
- **Local Elections**: County-level summary table linking to county files in `counties/` subdirectory
- **Party Breakdown**: Aggregate counts across all contests, qualified candidates only
- County table sorted alphabetically

---

## Variant B: Special Election Overview

Used for special elections with a small number of non-partisan contests.

### Additional Sections

```markdown
## Participating Counties

{Comma-separated list}

> **Note:** {Explanation of any discrepancies between SOS records and actual contests}

## Contests

### [{Locality} — {Office Title}]({contest-file}.md)

**Purpose:** {Brief explanation of vacancy}

| Candidate | Incumbent | Occupation | Website |
|-----------|-----------|------------|---------|
| {Name} | Yes/No | {Occupation} | [display](https://url) or — |
```

### Content Rules for Special Election

- **Participating Counties**: Simple comma-separated list, with notes explaining any discrepancies
- **Contests**: Each contest gets an H3 with a link to the individual contest file
- **Purpose line**: Required for each contest — one sentence explaining the vacancy
- **Inline candidate tables**: Abbreviated columns (no Status, Email, or Qualified Date — those live in the individual contest files)
- **Narrative-only contests**: Use a blockquote note instead of a candidate table (e.g., "Candidates qualified through the municipality")

### Key Differences Between Variants

| Aspect | General/Primary | Special Election |
|--------|----------------|-----------------|
| Party sections | Yes (Republican/Democrat counts) | No (non-partisan) |
| Contest summaries | Party count tables | Inline candidate tables with Purpose |
| Local elections | County summary table with links | Participating Counties list |
| Candidate breakdown | Aggregate party stats | Not included (small candidate pool) |
| Inline candidate columns | None (link to contest files) | Abbreviated (Candidate, Incumbent, Occupation, Website) |

## Validation Checklist

Before an election overview file is considered complete:

- [ ] Filename follows `{election-date}-{type}.md` pattern
- [ ] H1 heading uses `{Month D, YYYY} — {Election Type}` format
- [ ] Date, Type, and Candidates shown as bold key-value pairs
- [ ] Election Calendar uses ISO dates (`YYYY-MM-DD`) with source attribution
- [ ] All contest links resolve to existing files
- [ ] Candidate counts are accurate and match individual contest files
- [ ] Data Sources section lists all CSV and PDF source files
- [ ] (General/Primary) County table is sorted alphabetically
- [ ] (General/Primary) Party breakdown totals are correct
- [ ] (Special Election) Participating Counties list matches SOS records, with notes for discrepancies
- [ ] (Special Election) Each contest has a Purpose line
