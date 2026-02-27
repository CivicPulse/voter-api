# Quickstart: Stale Geocoding Job Detection & Cancellation

**Feature**: 011-stale-geocoding-jobs

## What This Feature Does

1. **Startup recovery** — On server restart, any geocoding jobs stuck in `running` or `pending` are automatically marked as `failed` with an explanatory note.
2. **Admin cancel** — Administrators can cancel a running/pending geocoding job via API.
3. **Admin mark-as-failed** — Administrators can mark a running/pending job as failed with an optional reason.
4. **Cooperative cancellation** — Background geocoding tasks check the job status at each batch boundary and stop processing if the job has been cancelled or failed externally.

## No Setup Required

This feature requires no database migrations, no new configuration, and no new dependencies. It extends existing code paths.

## API Endpoints

### Cancel a geocoding job

```bash
curl -X PATCH https://voteapi-dev.hatchtech.dev/api/v1/geocoding/jobs/{job_id}/cancel \
  -H "Authorization: Bearer <admin-token>"
```

**Response** (200):
```json
{
  "id": "...",
  "status": "cancelled",
  "completed_at": "2026-02-25T12:00:00Z",
  "message": "Job cancelled successfully"
}
```

**Response** (409 — job already in terminal state):
```json
{
  "detail": "Job is already in terminal state 'completed' and cannot be cancelled"
}
```

### Mark a geocoding job as failed

```bash
curl -X PATCH https://voteapi-dev.hatchtech.dev/api/v1/geocoding/jobs/{job_id}/fail \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Produced incorrect geocode results for Fulton County"}'
```

**Response** (200):
```json
{
  "id": "...",
  "status": "failed",
  "completed_at": "2026-02-25T12:00:00Z",
  "message": "Job marked as failed"
}
```

## Verification

### Check startup recovery

1. Create a geocoding job that stays in `running` status (e.g., start a batch job and kill the server mid-run)
2. Restart the server
3. Check server logs for: `Recovered N stale geocoding job(s) on startup`
4. Verify the job status is now `failed` via the job status endpoint

### Test cancel endpoint

```bash
# Trigger a batch job
curl -X POST https://voteapi-dev.hatchtech.dev/api/v1/geocoding/batch \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"provider": "census", "county": "FULTON"}'

# Cancel it
curl -X PATCH https://voteapi-dev.hatchtech.dev/api/v1/geocoding/jobs/{job_id}/cancel \
  -H "Authorization: Bearer <admin-token>"

# Verify status
curl https://voteapi-dev.hatchtech.dev/api/v1/geocoding/status/{job_id} \
  -H "Authorization: Bearer <admin-token>"
```
