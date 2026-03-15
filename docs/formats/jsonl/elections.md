# ElectionJSONL JSONL Schema

<!-- Auto-generated from Pydantic model. Do not edit manually. Regenerate with: uv run python tools/generate_jsonl_docs.py -->

JSONL record for a single election contest.

All records include a `schema_version` field (default: `1`) for forward compatibility. Increment on breaking changes.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `schema_version` | integer | No | `1` | Schema version integer. Increment on breaking changes. |
| `id` | uuid | Yes | -- | UUID from markdown contest metadata table. Required. |
| `election_event_id` | uuid | Yes | -- | UUID of the parent ElectionEvent (overview file). |
| `name` | string | Yes | -- | Display name matching the H1 heading in the contest markdown file. |
| `name_sos` | string or null | No | `null` | Exact SOS contest name from the Name (SOS) metadata field. |
| `election_date` | date | Yes | -- | Election day date (YYYY-MM-DD). |
| `election_type` | ElectionType enum | Yes | -- | Base election type. One of: general_primary, general, special, special_primary, municipal. |
| `election_stage` | ElectionStage enum | No | `election` | Resolution mechanism. One of: election, runoff, recount. |
| `district` | string or null | No | `null` | Free-text district name from legacy data. Being replaced by boundary_type + district_identifier. |
| `boundary_type` | string or null | No | `null` | Exact DB boundary type value resolved from Body/Seat reference. |
| `district_identifier` | string or null | No | `null` | Boundary identifier resolved from Body/Seat reference. |
| `boundary_id` | uuid or null | No | `null` | UUID of the resolved boundary polygon. Set during import when boundary exists. |
| `district_party` | string or null | No | `null` | Party restriction for this district contest (e.g. 'R' for Republican primary). |
| `data_source_url` | string or null | No | `null` | SOS results feed URL for this specific contest. |
| `source_name` | string or null | No | `null` | Human-readable name of the data source. |
| `source` | string or null | No | `null` | Source type. One of: sos_feed, manual, linked. |
| `ballot_item_id` | string or null | No | `null` | SOS ballot item ID from results feed. |
| `status` | string or null | No | `null` | Contest status. One of: active, finalized. |
| `last_refreshed_at` | datetime or null | No | `null` | Timestamp of last results feed refresh (ISO 8601 with timezone). |
| `refresh_interval_seconds` | integer or null | No | `null` | Seconds between results feed refresh cycles. |
| `eligible_county` | string or null | No | `null` | County restriction from candidate CSV COUNTY column. |
| `eligible_municipality` | string or null | No | `null` | Municipality restriction from candidate CSV MUNICIPALITY column. |

## Enum Definitions

### ElectionStage

Resolution mechanism for an election contest.

| Value | Description |
|-------|-------------|
| `election` | Election |
| `runoff` | Runoff |
| `recount` | Recount |

### ElectionType

Base election type classification.

| Value | Description |
|-------|-------------|
| `general_primary` | General Primary |
| `general` | General |
| `special` | Special |
| `special_primary` | Special Primary |
| `municipal` | Municipal |

## Example JSONL Record

Minimal record showing all required fields with realistic sample values:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "election_event_id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "Governor - Republican Primary",
  "election_date": "2026-05-19",
  "election_type": "general_primary"
}
```
