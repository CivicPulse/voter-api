# County Reference File Format Specification

This document defines the format for county reference files. County reference files provide metadata about a Georgia county and its governing bodies. The Governing Bodies table is the key integration point: it maps Body IDs used in election contest files to their `boundary_type` values, enabling the converter to resolve district linkage.

## File Location

```
data/states/GA/counties/{county}.md
```

Examples:
- `data/states/GA/counties/bibb.md`
- `data/states/GA/counties/fulton.md`
- `data/states/GA/counties/chatham.md`

County names are lowercase in filenames.

## Structure

```markdown
# {County Name} County

## Metadata

| Field | Value |
|-------|-------|
| ID | {uuid} |
| Format Version | 1 |
| County | {County Name} |
| State | [Georgia](../georgia.md) |
| County Seat | {City Name} |
| Consolidated Government | {Name, if applicable, or --} |
| Official Website | [{display}]({url}) |

## Governing Bodies

| Body ID | Name | boundary_type | Seat Pattern | Notes |
|---------|------|---------------|--------------|-------|
| {body-id} | {Full Name} | {boundary_type value} | {seat pattern description} | {notes} |
```

## Field Reference

### County Metadata Table

| Field | Required | Description |
|-------|----------|-------------|
| ID | Yes | UUID for this county reference record. Source of truth for identity. Converter error if missing. |
| Format Version | Yes | Integer version of this format specification. Starts at `1`. |
| County | Yes | County name in Title Case. |
| State | Yes | Link to the state reference file. Always `[Georgia](../georgia.md)` for Georgia counties. |
| County Seat | Yes | Name of the county seat city. |
| Consolidated Government | Optional | Name of the consolidated government, if the county and city have merged (e.g., "Macon-Bibb County"). Use `--` (em-dash) if not applicable. |
| Official Website | Yes | Markdown link to the county's official website. Display text is the bare domain. |

### Governing Bodies Table

The Governing Bodies table is the critical integration point for the Body/Seat reference system. It maps each Body ID to a `boundary_type` value from the [boundary-types vocabulary](../vocabularies/boundary-types.md).

| Column | Description |
|--------|-------------|
| Body ID | The Body ID slug used in contest files (e.g., `bibb-boe`). Must match exactly. |
| Name | Full human-readable name of the governing body (e.g., "Bibb County Board of Education"). |
| boundary_type | Exact value from the [boundary-types vocabulary](../vocabularies/boundary-types.md) (e.g., `school_board`, `county_commission`, `judicial`). |
| Seat Pattern | Description of the seat naming convention for this body. Documents which seat ID patterns apply and how seats are organized. |
| Notes | Additional context (e.g., "At-large seats use county boundary", "Multi-judge court; seat = incumbent surname"). |

### Seat Pattern Column

The Seat Pattern column documents how seats are organized within a body. Examples:

| Pattern Description | Meaning |
|---------------------|---------|
| `sole` | Single-seat body (e.g., Probate Judge) |
| `district-N` | All seats are district-based, numbered |
| `at-large (posts 7-8), district-N (1-6)` | Mix of at-large posts and district seats |
| `at-large, district-N` | Both at-large and district seats exist |
| `judge-{surname}` | Judicial seats named by incumbent |

## How the Converter Uses This File

1. A contest file contains `**Body:** bibb-boe | **Seat:** post-7`
2. The converter looks up `bibb-boe` in this file's Governing Bodies table
3. It finds `boundary_type: school_board`
4. It resolves the full district reference for the JSONL output:
   - `boundary_type = school_board`
   - `district_identifier` derived from the seat ID and body context
5. **If the Body ID is not found in this table, the converter emits a validation error** (strict mode, no fallback)

This ensures that every contest in the election data can be deterministically linked to a geographic boundary without relying on AI interpretation or fuzzy matching.

## Worked Example: Bibb County

```markdown
# Bibb County

## Metadata

| Field | Value |
|-------|-------|
| ID | {uuid} |
| Format Version | 1 |
| County | Bibb |
| State | [Georgia](../georgia.md) |
| County Seat | Macon |
| Consolidated Government | Macon-Bibb County |
| Official Website | [maconbibb.us](https://www.maconbibb.us/) |

## Governing Bodies

| Body ID | Name | boundary_type | Seat Pattern | Notes |
|---------|------|---------------|--------------|-------|
| bibb-boe | Bibb County Board of Education | school_board | at-large (posts 7-8), district-N (1-6) | At-large seats use county boundary |
| bibb-commission | Bibb County Commission | county_commission | district-N | |
| bibb-superior-court | Superior Court, Macon Judicial Circuit | judicial | judge-{surname} | Multi-judge court; seat = incumbent surname |
| bibb-state-court | State Court of Bibb County | judicial | judge-{surname} | |
| bibb-magistrate-court | Civil/Magistrate Court of Bibb County | judicial | sole | Single-judge court |
| macon-water-authority | Macon Water Authority | water_board | at-large, district-N | Mixed at-large and district seats |
```

This example covers the 12 contests in the Bibb County file:
- Board of Education At Large-Post 7 -> `bibb-boe` / `post-7`
- Board of Education At Large-Post 8 -> `bibb-boe` / `post-8`
- Civil/Magistrate Court Judge -> `bibb-magistrate-court` / `sole`
- Judge of Superior Court (Mincey) -> `bibb-superior-court` / `judge-mincey`
- Judge of Superior Court (Raymond) -> `bibb-superior-court` / `judge-raymond`
- Judge of Superior Court (Smith) -> `bibb-superior-court` / `judge-smith`
- Judge of Superior Court (Williford) -> `bibb-superior-court` / `judge-williford`
- State Court Judge (Hanson) -> `bibb-state-court` / `judge-hanson`
- State Court Judge (Lewis) -> `bibb-state-court` / `judge-lewis`
- Macon Water Authority-At Large -> `macon-water-authority` / `at-large`
- Macon Water Authority-District 1 -> `macon-water-authority` / `district-1`
- Macon Water Authority-District 4 -> `macon-water-authority` / `district-4`

## Content Rules

### Body ID Naming

Body IDs follow the `{scope}-{body}` convention from the [seat-ids vocabulary](../vocabularies/seat-ids.md):
- Scope is the county name (lowercase) for county-level bodies
- Scope is the municipality name for municipal-level bodies
- Body is a shortened, recognizable slug

### Empty Values

- Use `--` (em-dash, U+2014) for optional fields that are not applicable
- Never use `(none)`, `N/A`, `-`, or `--` (double hyphen)

### Website URLs

- Display text is the bare domain (lowercase)
- URL must include protocol and trailing slash for root domains

## Validation Checklist

- [ ] ID is a valid UUID
- [ ] Format Version is present and set to `1`
- [ ] County name matches the H1 heading
- [ ] Governing Bodies table is present with all columns
- [ ] Every Body ID follows the `{scope}-{body}` naming convention
- [ ] Every `boundary_type` value is from the [boundary-types vocabulary](../vocabularies/boundary-types.md)
- [ ] Seat Pattern descriptions accurately reflect the body's seat structure
- [ ] All contest Body IDs from the county's election files are represented in this table
- [ ] All empty values use em-dash (U+2014)
