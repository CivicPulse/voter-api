# Seat IDs and Body IDs Vocabulary

This document defines the slug patterns for Seat IDs and the naming convention for Body IDs. Together, these form the Body/Seat reference system that links every election contest to its geographic boundary.

## Seat ID Patterns

Seat IDs are lowercase slugs that identify a specific seat within a governing body. They use hyphens as separators, no spaces, no uppercase.

| Pattern | Description | Examples |
|---------|-------------|----------|
| `sole` | Single-seat office where there is only one seat for the entire body. | Governor, Lieutenant Governor, Secretary of State, Attorney General, County Probate Judge |
| `at-large` | At-large seat without a numbered designation. Used when a body has exactly one at-large seat. | A water authority with a single at-large position |
| `post-N` | Numbered post or position within a body. Used when seats are identified by post number rather than geographic district. | `post-7`, `post-8` (Board of Education at-large posts) |
| `district-N` | District-based seat identified by district number. | `district-1`, `district-3`, `district-14` (Commission districts, Congressional districts) |
| `judge-{surname}` | Judicial seat identified by the incumbent judge's surname. Used for multi-judge courts where seats are named after the sitting judge. | `judge-hanson`, `judge-mincey`, `judge-raymond` |

### Rules

- All seat IDs are **lowercase**
- Use **hyphens** as word separators (no underscores, no spaces)
- Numeric values are **unpadded** (`district-1`, not `district-01`)
- Judicial surnames are **lowercased** and **slugified** (`judge-mincey`, not `judge-Mincey`)
- Judicial seat IDs **change when a new judge takes the seat** -- this is expected behavior consistent with SOS contest naming conventions

### Seat ID and Boundary Resolution

Each contest independently declares its seat, and the boundary resolution depends on the seat type:

- **At-large seats** (e.g., `post-7` on a county board of education) typically point to the parent county boundary
- **District seats** (e.g., `district-3` on a county commission) point to the district-specific boundary
- The county reference file documents this mapping in the **Seat Pattern** column of the Governing Bodies table

## Body ID Naming Convention

Body IDs identify a governing body and follow the pattern `{scope}-{body}`, where:

- `{scope}` is the geographic or jurisdictional scope (state abbreviation, county name, or municipality name)
- `{body}` is a slugified name for the governing body

### Rules

- All Body IDs are **lowercase**
- Use **hyphens** as word separators
- Scope prefixes: `ga` for statewide/federal, county name for county-level, municipality name for municipal-level
- Body name is a shortened, recognizable slug

### Statewide/Federal Body IDs

| Body ID | Office | Seat Pattern |
|---------|--------|--------------|
| `ga-governor` | Governor | `sole` |
| `ga-lt-governor` | Lieutenant Governor | `sole` |
| `ga-sos` | Secretary of State | `sole` |
| `ga-ag` | Attorney General | `sole` |
| `ga-school-superintendent` | State School Superintendent | `sole` |
| `ga-agriculture` | Agriculture Commissioner | `sole` |
| `ga-labor` | Labor Commissioner | `sole` |
| `ga-insurance` | Insurance Commissioner | `sole` |
| `ga-us-senate` | U.S. Senate | `sole` (per seat; Georgia has 2 seats) |
| `ga-us-house` | U.S. House of Representatives | `district-N` |
| `ga-state-senate` | State Senate | `district-N` |
| `ga-state-house` | State House | `district-N` |
| `ga-psc` | Public Service Commission | `district-N` |

### County-Level Body ID Examples (Bibb County)

| Body ID | Name | Seat Pattern |
|---------|------|--------------|
| `bibb-boe` | Bibb County Board of Education | `at-large` (posts 7-8), `district-N` (1-6) |
| `bibb-commission` | Bibb County Commission | `district-N` |
| `bibb-superior-court` | Superior Court, Macon Judicial Circuit | `judge-{surname}` |
| `bibb-state-court` | State Court of Bibb County | `judge-{surname}` |
| `bibb-magistrate-court` | Civil/Magistrate Court of Bibb County | `sole` |

### Municipal-Level Body ID Examples

| Body ID | Name | Seat Pattern |
|---------|------|--------------|
| `macon-water-authority` | Macon Water Authority | `at-large`, `district-N` |

## How Body/Seat Resolution Works

1. A contest markdown file declares `Body: bibb-boe` and `Seat: post-7`
2. The converter looks up `bibb-boe` in the Bibb county reference file (`data/states/GA/counties/bibb.md`)
3. The county reference file's Governing Bodies table maps `bibb-boe` to `boundary_type: school_board`
4. The converter resolves the full district reference: `boundary_type=school_board`, `district_identifier` derived from the seat pattern
5. If the Body ID is not found in the county reference file, the converter emits a **validation error** (strict mode)

## Notes

- Body/Seat is used **everywhere** for consistency -- even statewide offices like Governor use `Body: ga-governor`, `Seat: sole`
- The county reference file is the single source of truth for mapping Body IDs to boundary types
- Statewide/federal Body IDs resolve to well-known boundary types without needing a county reference lookup (they are state-scoped, not county-scoped)
