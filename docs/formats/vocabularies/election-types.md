# Election Types Vocabulary

This document defines the controlled vocabulary for classifying elections using two independent fields: `election_type` (the base category) and `election_stage` (the resolution mechanism).

## Election Type

The `election_type` field classifies the fundamental nature of the election event or contest.

| Value | Description | Example |
|-------|-------------|---------|
| `general_primary` | Combined general election and partisan primary cycle. Includes both party primaries and non-partisan races on the same ballot. | May 19, 2026 -- General and Primary Election |
| `general` | General election without an associated primary on the same ballot. All voters eligible regardless of party. | November general election |
| `special` | Special election to fill a vacancy or resolve a specific ballot question. Typically non-partisan. | March 17, 2026 -- Special Election |
| `special_primary` | Primary election held before a special general election, when multiple candidates from the same party compete for the nomination. | Special primary for a US House vacancy |
| `municipal` | Municipal election conducted by a city or town, often on a different cycle than state elections. | City council elections |

### Event Type Priority Rule

When an election event groups multiple contest types (e.g., a ballot that includes both a general primary and a special election), the event-level `election_type` uses the **broadest applicable type**. Priority order (highest wins):

1. `general_primary`
2. `general`
3. `municipal`
4. `special_primary`
5. `special`

Individual contests within the event retain their own specific `election_type`.

### Event vs. Contest Semantics

The same vocabulary applies to both election events (overview files) and individual contests (contest files), but the semantics differ:

- **Event type** = broadest applicable type across all contests in the event
- **Contest type** = specific type for that individual race

## Election Stage

The `election_stage` field indicates the resolution mechanism or phase of the election process.

| Value | Description | When Used |
|-------|-------------|-----------|
| `election` | The standard first-round election. This is the default value. | All initial elections, primaries, and general elections |
| `runoff` | A second-round election held when no candidate achieves the required vote threshold (typically a majority). | Georgia runoff elections following primaries or generals |
| `recount` | A recount of ballots from a prior election, triggered by margin thresholds or official petition. | Recounts mandated by Georgia law when margins fall within statutory thresholds |

### Default Behavior

If `election_stage` is not specified, it defaults to `election`. Only specify `runoff` or `recount` when the election is explicitly a follow-up to a prior round.

## Usage in Markdown Files

In election overview and contest file metadata tables:

```markdown
| Field | Value |
|-------|-------|
| Type | general_primary |
| Stage | election |
```

## Authoritative Source

These values are defined in this vocabulary document and will be codified as `ElectionType` and `ElectionStage` StrEnum classes in `src/voter_api/schemas/jsonl/enums.py`. The Pydantic models are the machine-readable authority; this document is the human-readable reference.
