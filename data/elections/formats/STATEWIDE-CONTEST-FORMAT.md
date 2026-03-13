# Statewide/Federal Contest File Format — Canonical Reference

This document defines the exact structure and conventions that all statewide and federal contest files must follow (governor, lieutenant governor, secretary of state, attorney general, state school superintendent, agriculture/labor/insurance commissioners, PSC districts, US senate, and US house districts). Use this as the authoritative template for file generation, review, and normalization.

## File Naming Convention

```
data/elections/{election-date}/{election-date}-{contest-slug}.md
```

Contest slugs use lowercase with hyphens. Examples:
- `2026-05-19-governor.md`
- `2026-05-19-us-house-district-01.md`
- `2026-05-19-psc-district-3.md`

## Structure

Every statewide/federal contest file **must** follow this exact markdown structure:

```markdown
# {Contest Display Name}

## Metadata

| Field | Value |
|-------|-------|
| Election | [{Election Display Name}]({overview-file}.md) |
| Type | Partisan Primary |
| Candidates | {N} Republican, {N} Democrat |

## Election Calendar

| Milestone | Date |
|-----------|------|
| Qualifying Period | {Month D–D, YYYY} |
| Voter Registration Deadline | {Month D, YYYY} |
| Early Voting | {Month D – Month D, YYYY} |
| Absentee Ballot Application Deadline | {Month D, YYYY} |
| Election Day | {Month D, YYYY} |

## Republican Primary

**Contest Name (SOS):** {SOS Contest Name} (R)

| Candidate | Status | Incumbent | Occupation | Qualified Date | Email | Website |
|-----------|--------|-----------|------------|---------------|-------|---------|
| {Name} | Qualified | Yes/No | {Occupation} | MM/DD/YYYY | email or — | [display](https://url) or — |

## Democrat Primary

**Contest Name (SOS):** {SOS Contest Name} (D)

| Candidate | Status | Incumbent | Occupation | Qualified Date | Email | Website |
|-----------|--------|-----------|------------|---------------|-------|---------|
| {Name} | Qualified | Yes/No | {Occupation} | MM/DD/YYYY | email or — | [display](https://url) or — |

## Data Source

- Candidate list: `data/new/{CSV_FILENAME}`
```

## Key Differences from County Format

| Aspect | County Format | Statewide Format |
|--------|--------------|-----------------|
| H1 heading | `{County} County — Local Elections` | `{Contest Display Name}` |
| Party sections | Contest headings under `## Contests` | Separate `## {Party} Primary` sections |
| SOS contest name | Not shown | Shown via `**Contest Name (SOS):**` |
| Metadata: Candidates | Numeric count | Breakdown by party (`N Republican, N Democrat`) |

## Content Rules

### Candidate Table Columns

The canonical column set for statewide/federal contests:

1. **Candidate** — Full name as it appears in the SOS CSV (no normalization)
2. **Status** — `Qualified` or `Withdrawn` (must use these exact values)
3. **Incumbent** — `Yes` or `No`
4. **Occupation** — Title Case, proper acronyms capitalized (see County Format for acronym rules)
5. **Qualified Date** — Date in MM/DD/YYYY format
6. **Email** — Email address or `—` (em-dash) if not provided
7. **Website** — Markdown link `[display](https://url)` or `—` if not provided

> **Note:** Existing files are missing the `Status` column. When normalizing, add it with `Qualified` for all current candidates and `Withdrawn` for any who have withdrawn.

### Party Sections

- Each party gets its own H2 section: `## Republican Primary`, `## Democrat Primary`
- Non-partisan statewide contests (if any) use a single `## Candidates` section instead
- Include the SOS contest name with party suffix: `**Contest Name (SOS):** Governor (R)`

### Contest Display Names

- Title Case for all contest names
- Use "U.S." with periods for federal offices (e.g., `U.S. Senate`, `U.S. House — District 1`)
- Use "PSC" (not "Public Service Commission") in filenames but spell out in headings
- District numbers: zero-padded in filenames (`district-01`), natural in headings (`District 1`)

### Empty Values

- Use `—` (em-dash, U+2014) for missing email and website fields
- Never use `(none)`, `N/A`, `-`, or `--`

### Website URLs

Same rules as County Format:
- Display text `[text]` is lowercase
- URL in parentheses must be lowercase
- Example: `[carrforgeorgia.com](https://www.carrforgeorgia.com)`

### Occupations

Same rules as County Format:
- Title Case with uppercase acronyms (CEO, CPA, LLC)
- See County Format for the full list of common abbreviations

## Election Calendar

The Election Calendar section is **static and identical** across all contest files for the same election date. Copy it verbatim from the election overview file.

## Validation Checklist

Before a statewide/federal contest file is considered complete:

- [ ] Filename follows `{election-date}-{contest-slug}.md` pattern
- [ ] H1 heading is the contest display name (not the SOS name)
- [ ] Metadata table links to the correct election overview file
- [ ] Candidate count in metadata matches actual rows across all party sections
- [ ] **Status** column is present with `Qualified` or `Withdrawn` values
- [ ] Every party section includes `**Contest Name (SOS):**` with party suffix
- [ ] All website URLs are lowercase in parentheses
- [ ] Occupations use proper case with uppercase acronyms
- [ ] Election Calendar matches the overview file exactly
- [ ] All email/website cells use `—` (em-dash) when empty — never `(none)`
- [ ] Data Source points to the correct CSV file
