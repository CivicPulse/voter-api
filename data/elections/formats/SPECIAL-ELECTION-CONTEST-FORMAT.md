# Special Election Contest File Format — Canonical Reference

This document defines the exact structure and conventions that all individual special election contest files must follow. Use this as the authoritative template for file generation, review, and normalization.

## File Naming Convention

```
data/elections/{election-date}/{election-date}-{contest-slug}.md
```

Contest slugs use lowercase with hyphens, combining locality and office:
- `2026-03-17-clayton-probate-judge.md`
- `2026-03-17-bibb-commission-district-5.md`
- `2026-03-17-buchanan-mayor.md`
- `2026-03-17-wadley-council-member.md`

## Structure

Every special election contest file **must** follow this exact markdown structure:

```markdown
# {Locality} — {Office Title}

## Metadata

| Field | Value |
|-------|-------|
| Election | [{Election Display Name}]({overview-file}.md) |
| Type | Non-Partisan |
| Contest Name (SOS) | {SOS Contest Name or "N/A — municipal qualifying"} |
| Party | Non-Partisan |
| County | {County Name} |
| Municipality | {City Name} *(only if applicable)* |
| District | [{Boundary Name}]({API URL}) *(or note if unavailable)* |
| Candidates | {number} |
| Purpose | {Brief description of why this special election exists} |
| Eligibility | {Who is eligible to vote} |

## Candidates

| Candidate | Status | Incumbent | Occupation | Qualified Date | Email | Website |
|-----------|--------|-----------|------------|---------------|-------|---------|
| {Name} | Qualified | Yes/No | {Occupation} | MM/DD/YYYY | email or — | [display](https://url) or — |

### Candidate Bios

**{Candidate Name}** — {Brief biographical paragraph}

## Data Source

- Candidate list: `data/new/{CSV_FILENAME}`
- [{Source Title}]({URL}) — {Publication}
```

### Narrative-Only Contests (Municipal Qualifying)

When candidates qualified through a municipality rather than the SOS (and therefore lack structured SOS data), the file uses a `## Background` section instead of a candidate table:

```markdown
## Background

{Narrative describing the circumstances, candidates, and context}
```

This is the only case where the candidate table may be omitted. The Metadata table must still include `Contest Name (SOS) | N/A — municipal qualifying` and a note explaining why.

## Key Differences from Other Formats

| Aspect | Special Election | Statewide | County |
|--------|-----------------|-----------|--------|
| H1 heading | `{Locality} — {Office Title}` | `{Contest Display Name}` | `{County} County — Local Elections` |
| Metadata fields | Includes Purpose, Eligibility, Municipality | Minimal (Election, Type, Candidates) | Includes Contests count |
| Party sections | None (non-partisan) | Separate per party | None (contests grouped) |
| Candidate Bios | Yes (researched) | No | No |
| Background section | Optional (narrative-only) | No | No |

## Content Rules

### Metadata Table Format

**All metadata must use the table format** (`| Field | Value |`). This resolves the inconsistency where some files used bullet lists (`- **Field:** Value`) or bold key-value pairs.

Do **not** use these deprecated formats:
- ~~`- **Election:** ...`~~ (bullet list — used in Clayton)
- ~~`**Election:** ...`~~ (bold key-value — used in Bibb)

### Metadata Fields

| Field | Required | Description |
|-------|----------|-------------|
| Election | Yes | Link to the parent overview file |
| Type | Yes | `Non-Partisan` for all special elections to date |
| Contest Name (SOS) | Yes | Exact SOS name, or `N/A — municipal qualifying` |
| Party | Yes | `Non-Partisan` |
| County | Yes | County name (Title Case) |
| Municipality | If applicable | City/town name (only for municipal contests) |
| District | Yes | Link to boundary API, or note if unavailable |
| Candidates | Yes | Numeric count |
| Purpose | Yes | Brief explanation of why the seat is vacant |
| Eligibility | Yes | Description of who may vote |

### Candidate Table Columns

The canonical column set (superset of all existing files):

1. **Candidate** — Full name as it appears in the SOS CSV
2. **Status** — `Qualified` or `Withdrawn`
3. **Incumbent** — `Yes` or `No`
4. **Occupation** — Title Case, proper acronyms capitalized
5. **Qualified Date** — Date in MM/DD/YYYY format
6. **Email** — Email address or `—` (em-dash)
7. **Website** — Markdown link `[display](https://url)` or `—`

### Empty Values

- Use `—` (em-dash, U+2014) for missing email and website fields
- Never use `(none)`, `N/A`, `-`, or `--`
- This resolves the inconsistency where Bibb/Wadley used `(none)` while Clayton used `—`

### Candidate Bios

- Section heading: `### Candidate Bios` (not `## Candidate Bios` or `### Background`)
- Each bio starts with `**{Full Name}** — ` followed by a brief paragraph
- Bios are researched from local news sources, campaign websites, and public records
- Include relevant professional background, community ties, and campaign priorities
- Cite sources in the Data Source section, not inline

### Purpose Field

Every special election exists because a seat became vacant. The Purpose field must explain:
- **What happened**: resignation, death, conviction, retirement, etc.
- **Who**: the person who vacated the seat (if known)
- Keep it factual and concise (one sentence)

### Website URLs

Same rules as County Format:
- Display text is lowercase
- URL in parentheses must be lowercase
- Multiple websites are separated by commas: `[site1.org](https://site1.org), [Facebook](https://facebook.com/page)`

### Occupations

Same rules as County Format:
- Title Case with uppercase acronyms (CEO, CPA, LLC)

## Validation Checklist

Before a special election contest file is considered complete:

- [ ] Filename follows `{election-date}-{contest-slug}.md` pattern
- [ ] H1 heading uses `{Locality} — {Office Title}` format
- [ ] Metadata uses table format (not bullets or bold key-value)
- [ ] All required metadata fields are present
- [ ] Purpose field explains why the seat is vacant
- [ ] Eligibility field describes who may vote
- [ ] **Status** column is present in candidate table
- [ ] All email/website cells use `—` (em-dash) when empty — never `(none)`
- [ ] Candidate Bios section is present (unless narrative-only contest)
- [ ] Data Source includes both the SOS CSV reference and news source links
- [ ] All website URLs are lowercase in parentheses

## Known Inconsistencies in Existing Files

These issues exist in the current files and should be resolved in a future normalization pass:

| File | Issue | Resolution |
|------|-------|------------|
| Clayton Probate Judge | Metadata uses bullet list format | Convert to table format |
| Bibb Commission Dist 5 | Metadata uses bold key-value format | Convert to table format |
| Bibb Commission Dist 5 | Uses `(none)` for empty values | Replace with `—` |
| Wadley Council Member | Uses `(none)` for empty values | Replace with `—` |
| All 4 files | Missing `Status` column | Add with `Qualified` for all candidates |
| Buchanan Mayor | No candidate table (narrative-only) | Acceptable — document as narrative-only variant |
