# Data Model: Stale Geocoding Job Detection & Cancellation

**Feature**: 011-stale-geocoding-jobs
**Date**: 2026-02-25

## No New Models or Migrations

This feature uses the existing `GeocodingJob` model without modifications. All required fields already exist.

## Existing Model Reference

### GeocodingJob (`geocoding_jobs` table)

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` (PK) | Via `UUIDMixin` |
| `status` | `String(20)` | Indexed. Values: `pending`, `running`, `completed`, `failed`, `cancelled` |
| `error_log` | `JSONB` | `list[dict] | None` — array of error entries |
| `started_at` | `DateTime(tz)` | Set when job transitions to `running` |
| `completed_at` | `DateTime(tz)` | Set when job reaches a terminal state |
| `created_at` | `DateTime(tz)` | Server default `now()`, indexed |
| `provider` | `String(50)` | Geocoding provider name |
| `county` | `String(100)` | Optional county filter |
| `force_regeocode` | `Boolean` | Whether to re-geocode |
| `total_records` | `Integer` | Total voters to process |
| `processed` | `Integer` | Voters processed so far |
| `succeeded` | `Integer` | Successful geocodes |
| `failed` | `Integer` | Failed geocodes |
| `cache_hits` | `Integer` | Cache hit count |
| `last_processed_voter_offset` | `Integer` | Checkpoint for resume |
| `triggered_by` | `UUID` | User who triggered the job |

Source: `src/voter_api/models/geocoding_job.py`

## State Transitions

```
pending ──→ running ──→ completed
  │            │
  │            ├──→ failed
  │            │
  │            └──→ cancelled
  │
  ├──→ failed      (startup recovery or admin action)
  │
  └──→ cancelled   (admin action)
```

**Terminal states**: `completed`, `failed`, `cancelled` — no further transitions allowed.

**New transitions added by this feature**:
- `pending → failed` (startup recovery)
- `running → failed` (startup recovery, admin mark-as-failed)
- `pending → cancelled` (admin cancel)
- `running → cancelled` (admin cancel)

## Index Recommendation

The spec mentions adding a composite index `(status, created_at DESC)` for job list queries. The current schema already has:
- `ix_geocoding_jobs_status` on `status`
- `ix_geocoding_jobs_created_at` on `created_at`

A composite index would be beneficial for the `ORDER BY created_at DESC` + `WHERE status = ?` query pattern in `list_geocoding_jobs()`, but since the existing individual indexes are adequate for current query volumes and adding the composite index requires a migration, this is deferred. The individual indexes cover the common query patterns.
