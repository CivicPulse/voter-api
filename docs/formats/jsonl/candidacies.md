# CandidacyJSONL JSONL Schema

<!-- Auto-generated from Pydantic model. Do not edit manually. Regenerate with: uv run python tools/generate_jsonl_docs.py -->

JSONL record for a candidacy (candidate-election junction).

All records include a `schema_version` field (default: `1`) for forward compatibility. Increment on breaking changes.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `schema_version` | integer | No | `1` | Schema version integer. Increment on breaking changes. |
| `id` | uuid | Yes | -- | UUID of this candidacy record. From markdown metadata. |
| `candidate_id` | uuid | Yes | -- | UUID of the candidate (person). From candidate file metadata. |
| `election_id` | uuid | Yes | -- | UUID of the election contest. From contest file metadata. |
| `party` | string or null | No | `null` | Party affiliation for this contest. Null for non-partisan races. |
| `filing_status` | FilingStatus enum | No | `qualified` | Candidate filing status. One of: qualified, withdrawn, disqualified, write_in. |
| `is_incumbent` | boolean | No | `false` | Whether the candidate is the incumbent for this seat. |
| `occupation` | string or null | No | `null` | Occupation as listed in SOS data. Title case. |
| `qualified_date` | date or null | No | `null` | Date candidate qualified for the ballot (YYYY-MM-DD). |
| `ballot_order` | integer or null | No | `null` | Position on ballot. Typically set from SOS results data. |
| `sos_ballot_option_id` | string or null | No | `null` | SOS ballot option ID from results feed for matching. |
| `contest_name` | string or null | No | `null` | Exact SOS contest name for matching. From Name (SOS) metadata. |

## Enum Definitions

### FilingStatus

Candidate filing status lifecycle.

| Value | Description |
|-------|-------------|
| `qualified` | Qualified |
| `withdrawn` | Withdrawn |
| `disqualified` | Disqualified |
| `write_in` | Write In |

## Example JSONL Record

Minimal record showing all required fields with realistic sample values:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "candidate_id": "880e8400-e29b-41d4-a716-446655440003",
  "election_id": "990e8400-e29b-41d4-a716-446655440004"
}
```
