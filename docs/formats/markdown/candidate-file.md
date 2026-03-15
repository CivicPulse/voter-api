# Candidate File Format Specification

This document defines the format for global candidate files. Each candidate file represents a **person** (not a candidacy) and contains stable person-level data at the top with election-keyed sections below. This is a new format with no predecessor.

## File Location

```
data/candidates/{name-slug}-{8-char-hash}.md
```

Examples:
- `data/candidates/jane-doe-a3f2e1b4.md`
- `data/candidates/kerry-warren-hatcher-7f3e1a2b.md`
- `data/candidates/david-lafayette-mincey-iii-550e8400.md`

### Filename Convention

- `{name-slug}`: Lowercase, hyphenated version of the candidate's full name
- `{8-char-hash}`: First 8 characters of the candidate's UUID (for human disambiguation of common names)
- The hash ensures uniqueness when two candidates share the same name

## Structure

```markdown
# {Full Name}

## Metadata

| Field | Value |
|-------|-------|
| ID | {uuid} |
| Format Version | 1 |
| Name | {Full Name} |
| Photo URL | {url or --} |
| Email | {email or --} |

## Bio

{Biographical paragraph with professional background, community ties, and relevant experience. Use -- if unavailable.}

## External IDs

| Source | ID |
|--------|----|
| Ballotpedia | {id or --} |
| Open States | {id or --} |
| VPAP | {id or --} |

## Links

| Type | URL | Label |
|------|-----|-------|
| {link-type} | {url} | {display label} |

## Elections

### {Election Display Name} -- {Contest Name}

| Field | Value |
|-------|-------|
| Election ID | {uuid of election contest} |
| Contest File | [{relative path}]({relative-link-to-contest-file}) |
| Party | {party or Non-Partisan} |
| Occupation | {occupation for this contest} |
| Filing Status | {filing_status value} |
| Qualified Date | {MM/DD/YYYY} |
| Is Incumbent | Yes/No |

### {Another Election} -- {Another Contest}

| Field | Value |
|-------|-------|
| Election ID | {uuid} |
| Contest File | [{relative path}]({relative-link}) |
| Party | {party} |
| Occupation | {occupation} |
| Filing Status | {filing_status value} |
| Qualified Date | {MM/DD/YYYY} |
| Is Incumbent | Yes/No |
```

## Field Reference

### Person Metadata Table

| Field | Required | Description |
|-------|----------|-------------|
| ID | Yes | UUID for this candidate (person). Source of truth for the Candidate identity. Converter error if missing. |
| Format Version | Yes | Integer version of this format specification. Starts at `1`. |
| Name | Yes | Full name as displayed. Title Case. |
| Photo URL | Yes | URL to a photo of the candidate, or `--` (em-dash) if unavailable. |
| Email | Yes | Primary email address, or `--` (em-dash) if unavailable. |

### Bio Section

A brief biographical paragraph covering:
- Professional background and career
- Community ties and civic involvement
- Campaign priorities (if running)

Use `--` (em-dash) if no biographical information is available. This section is populated by the candidate-enrichment skill (Phase 3).

### External IDs Table

Cross-references to the candidate's records in external data sources.

| Column | Description |
|--------|-------------|
| Source | Name of the external data source (e.g., Ballotpedia, Open States, VPAP) |
| ID | The candidate's identifier in that source, or `--` if not yet linked |

Common sources:
- **Ballotpedia**: Ballotpedia page slug or ID
- **Open States**: Open States person ID
- **VPAP**: Virginia Public Access Project ID (if applicable)
- **Google Civic**: Google Civic Information API ID

Additional sources may be added as rows. The table is not limited to a fixed set of sources.

### Links Table

URLs associated with the candidate, using types from the [link-types vocabulary](../vocabularies/link-types.md).

| Column | Description |
|--------|-------------|
| Type | Link type value: `website`, `campaign`, `facebook`, `twitter`, `instagram`, `youtube`, `linkedin`, `other` |
| URL | Full URL including protocol |
| Label | Human-readable display text for the link |

### Elections Section

Each election the candidate has participated in gets its own H3 subsection under `## Elections`. The heading format is:

```
### {Election Display Name} -- {Contest Name}
```

Each subsection contains a metadata table with contest-specific fields:

| Field | Required | Description |
|-------|----------|-------------|
| Election ID | Yes | UUID of the election contest (from the contest file's metadata). |
| Contest File | Yes | Relative link to the contest file where this candidate appears. |
| Party | Yes | Party affiliation for this specific contest (e.g., "Republican", "Democrat", "Non-Partisan"). |
| Occupation | Yes | Occupation as listed for this specific contest. May differ across elections. |
| Filing Status | Yes | Filing status value from the [filing-status vocabulary](../vocabularies/filing-status.md): `qualified`, `withdrawn`, `disqualified`, `write_in`. |
| Qualified Date | Yes | Date the candidate qualified, in `MM/DD/YYYY` format. |
| Is Incumbent | Yes | `Yes` or `No` -- whether the candidate is the incumbent for this seat. |

## Design Decisions

### One File Per Person

A candidate who runs in multiple elections (or multiple contests within the same election) has **one** candidate file. Each contest appearance is a subsection under `## Elections`. This enables:

- Tracking candidates across election cycles
- Avoiding data duplication (photo, bio, links are stored once)
- Cross-referencing all of a candidate's contests from a single location

### Deduplication

Candidate deduplication (matching the same person across different SOS CSV records) is handled by the Claude skill in Phase 3, not by format rules. Phase 1 defines the "one person, one file, one ID" contract.

### Contest Table Integration

Contest files (single-contest and multi-contest) link to candidate files in the Candidate column:

```markdown
| [Jane Doe](../../candidates/jane-doe-a3f2e1b4.md) | Qualified | No | Attorney | 03/02/2026 |
```

Person-level data (email, website, bio, photo) lives only in the candidate file. Contest tables contain only contest-specific fields.

## Content Rules

### Empty Values

- Use `--` (em-dash, U+2014) for missing fields
- Never use `(none)`, `N/A`, `-`, or `--` (double hyphen)

### Name Formatting

- Full name in Title Case
- Name slug in filename is lowercase with hyphens
- Suffixes preserved: "III", "Jr", "Sr"

### Link URLs

- Display text is lowercase for domain-based labels
- URL must include protocol (`https://`)
- Use canonical profile URLs (not individual post URLs)

## Validation Checklist

- [ ] ID is a valid UUID
- [ ] Format Version is present and set to `1`
- [ ] Filename follows `{name-slug}-{8-char-hash}.md` pattern
- [ ] 8-char hash matches the first 8 characters of the UUID
- [ ] Name matches the H1 heading
- [ ] Every election subsection has an Election ID, Contest File link, and all required fields
- [ ] Filing Status values are from the controlled vocabulary
- [ ] Link Type values are from the controlled vocabulary
- [ ] All empty values use em-dash (U+2014)
