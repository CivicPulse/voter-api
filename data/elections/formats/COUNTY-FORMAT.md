# County Election File Format — Canonical Reference

This document defines the exact structure and conventions that all 159 Georgia county election files must follow. Use this as the authoritative template for file generation, review, and normalization.

## File Naming Convention

```
data/elections/2026-05-19/counties/2026-05-19-{county}.md
```

All files follow the date-based naming scheme for the May 19, 2026 election cycle. County names are lowercase.

## Structure

Every county file **must** follow this exact markdown structure. No variations are permitted:

```markdown
# {County Name} County — Local Elections

## Metadata

| Field | Value |
|-------|-------|
| Election | [May 19, 2026 — General and Primary Election](../2026-05-19-general-primary.md) |
| Type | Local Races |
| Contests | {number} |
| Candidates | {number} |

## Election Calendar

| Milestone | Date |
|-----------|------|
| Qualifying Period | March 2–6, 2026 |
| Voter Registration Deadline | April 20, 2026 |
| Early Voting | April 27 – May 15, 2026 |
| Absentee Ballot Application Deadline | May 8, 2026 |
| Election Day | May 19, 2026 |

## Contests

### {Contest Name in Title Case}

[**{Party Primary}** if applicable]

| Candidate | Status | Incumbent | Occupation | Qualified | Email | Website |
|-----------|--------|-----------|------------|-----------|-------|---------|
| {Name} | Qualified/Withdrawn | Yes/No | {Title Case Occupation} | MM/DD/YYYY | email or — | [display](https://lowercase-url) or — |

## Data Source

- Candidate list: `data/new/MAY_19_2026-GENERAL_AND_PRIMARY_ELECTION_Qualified_Candidates.csv`
```

## Content Rules

### Contest Names

**Rule**: All contest names **must** be in Title Case.

- **Lowercase articles and prepositions**: "of", "at", "for", "in", "to", "the", "and", "or", "a" (unless at the start of the name)
- **Keep acronyms capitalized**: BOE, PSC, PUD, EMC, etc.
- **Parenthetical suffixes**: Preserve as written, typically in parentheses (e.g., "State Court Judge (Hanson)")

**Examples**:
- ❌ `BOARD OF EDUCATION AT LARGE-POST 7` → ✅ `Board of Education At Large-Post 7`
- ❌ `CIVIL/MAGISTRATE COURT JUDGE` → ✅ `Civil/Magistrate Court Judge`
- ❌ `STATE COURT JUDGE (HANSON)` → ✅ `State Court Judge (Hanson)`
- ❌ `MACON WATER AUTHORITY-AT LARGE` → ✅ `Macon Water Authority-At Large`

### Website URLs

**Rule**: Website display text `[text]` stays lowercase; only the URL in parentheses must be lowercased.

**Format**:
```markdown
[lowercase-display.org](https://lowercase-url.org)
```

**Examples**:
- ❌ `[mortonforschools.org](https://MORTONFORSCHOOLS.ORG)` → ✅ `[mortonforschools.org](https://mortonforschools.org)`
- ❌ `[votehatcher.com](https://VOTEHATCHER.COM)` → ✅ `[votehatcher.com](https://votehatcher.com)`

### Occupations

**Rule**: Occupation fields must use proper case. Common acronyms must be uppercase.

**Common abbreviations to normalize**:
- `Ceo` → `CEO`
- `Cfo` → `CFO`
- `Cpa` → `CPA`
- `Clio` → `CLO` (Chief Legal Officer)
- `Llc` → `LLC`
- `Llp` → `LLP`
- `Ret` → `Retired` (expand if part of longer phrase like "Ret Educator" → "Retired Educator")

**Judgment**: Only normalize clear acronyms. Do not alter general occupations like "Educator", "Attorney", "Business Owner", etc.

**Examples**:
- ❌ `Ceo` → ✅ `CEO`
- ❌ `Cpa` → ✅ `CPA`
- ❌ `Blue Armor Network of America Llc` → ✅ `Blue Armor Network of America LLC`
- ✅ `Software Engineer` (no change)
- ✅ `Retired Educator` (no change)

## Tables

### Candidate Table Columns

1. **Candidate** — Full name (no normalization)
2. **Status** — `Qualified`, `Withdrawn`, `Disqualified`, `Qualified - Signatures Accepted`, or `Qualified - Signatures Required` (must use these exact values from the SOS CSV)
3. **Incumbent** — `Yes` or `No`
4. **Occupation** — Title Case, proper acronyms capitalized
5. **Qualified** — Date in MM/DD/YYYY format
6. **Email** — Email address or `—` (em-dash) if not provided
7. **Website** — Markdown link `[display](https://url)` or `—` if not provided

## Metadata

- **Contests** — Numeric count of distinct contests (contest headings)
- **Candidates** — Numeric count of all candidate rows across all contests

Count accurately; these are used for filtering and navigation.

## Validation Checklist

Before a county file is considered complete:

- [ ] Filename follows `2026-05-19-{county}.md` pattern
- [ ] Every contest name is in Title Case (no ALL CAPS)
- [ ] All website URLs are lowercase in parentheses
- [ ] Occupations use proper case with uppercase acronyms (CEO, CPA, LLC)
- [ ] Election Calendar section is identical across all files
- [ ] Data Source points to correct CSV
- [ ] All email/website cells use `—` (em-dash, not hyphen or double-dash) when empty
- [ ] No trailing whitespace on any line

## Notes

- The Election Calendar is **static and identical** across all county files
- Only the Contests section varies by county
- Metadata numbers (Contests, Candidates) must be updated if contests/candidates are added/removed
- All dates follow MM/DD/YYYY format (US East Coast convention per Georgia SOS standards)
