# ElectionEventJSONL JSONL Schema

<!-- Auto-generated from Pydantic model. Do not edit manually. Regenerate with: uv run python tools/generate_jsonl_docs.py -->

JSONL record for an election event (election day).

All records include a `schema_version` field (default: `1`) for forward compatibility. Increment on breaking changes.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `schema_version` | integer | No | `1` | Schema version integer. Increment on breaking changes. |
| `id` | uuid | Yes | -- | UUID from markdown overview metadata table. Required. |
| `event_date` | date | Yes | -- | Election day date (YYYY-MM-DD). |
| `event_name` | string | Yes | -- | Display name of the election event, e.g. 'May 19, 2026 - General Primary Election'. |
| `event_type` | ElectionType enum | Yes | -- | Base election type. One of: general_primary, general, special, special_primary, municipal. |
| `registration_deadline` | date or null | No | `null` | Voter registration deadline date (YYYY-MM-DD). |
| `early_voting_start` | date or null | No | `null` | First day of early voting (YYYY-MM-DD). |
| `early_voting_end` | date or null | No | `null` | Last day of early voting (YYYY-MM-DD). |
| `absentee_request_deadline` | date or null | No | `null` | Deadline to request an absentee ballot (YYYY-MM-DD). |
| `qualifying_start` | date or null | No | `null` | First day of candidate qualifying period (YYYY-MM-DD). |
| `qualifying_end` | date or null | No | `null` | Last day of candidate qualifying period (YYYY-MM-DD). |
| `data_source_url` | string or null | No | `null` | SOS results feed URL for this election event. Set when available. |
| `last_refreshed_at` | datetime or null | No | `null` | Timestamp of last results feed refresh (ISO 8601 with timezone). |
| `refresh_interval_seconds` | integer or null | No | `null` | Seconds between results feed refresh cycles. Minimum 60. |

## Enum Definitions

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
  "event_date": "2026-05-19",
  "event_name": "May 19, 2026 - General Primary Election",
  "event_type": "general_primary"
}
```
