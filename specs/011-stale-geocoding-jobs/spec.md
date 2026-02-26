# Feature Specification: Stale Geocoding Job Detection & Cancellation

**Feature Branch**: `011-stale-geocoding-jobs`
**Created**: 2026-02-25
**Status**: Draft
**Input**: User description: "Add stale job detection and cancel capability for batch geocoding jobs"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Stale Job Recovery on Server Restart (Priority: P1)

When the server restarts after a crash or deployment, any batch geocoding jobs that were in a "running" or "pending" state are automatically detected and marked as failed. This prevents phantom jobs from cluttering the job listing and gives administrators an accurate view of system status immediately after restart.

**Why this priority**: This is the highest-impact fix because it addresses the root cause — jobs becoming permanently stuck after server restarts. It requires no manual intervention and follows an established pattern already proven for analysis runs.

**Independent Test**: Can be fully tested by creating a geocoding job in "running" status, restarting the server, and verifying the job is now marked "failed" with an explanatory note. Delivers immediate value by eliminating phantom jobs.

**Acceptance Scenarios**:

1. **Given** a geocoding job exists with status "running" and the server restarts, **When** the application starts up, **Then** the job status is updated to "failed" with a note indicating "Server restarted while task was in progress" and `completed_at` is set to the current time.
2. **Given** a geocoding job exists with status "pending" and the server restarts, **When** the application starts up, **Then** the job status is updated to "failed" with the same recovery note and timestamp.
3. **Given** no geocoding jobs are in "running" or "pending" state, **When** the server starts, **Then** no jobs are modified and no warnings are logged.
4. **Given** a geocoding job in "running" state already has entries in its error log, **When** the server recovers it, **Then** the existing error log entries are preserved and the recovery note is appended.

---

### User Story 2 - Administrator Manually Cancels a Geocoding Job (Priority: P2)

An administrator sees a geocoding job in the job listing that is stuck or no longer needed. They cancel it through the API, which immediately marks it as cancelled and records when it was cancelled. This prevents wasted resources and keeps the job listing clean.

**Why this priority**: Manual cancellation gives administrators direct control over runaway or unwanted jobs. It complements automatic recovery by handling cases where a job is stuck but the server has not restarted.

**Independent Test**: Can be tested by creating a batch geocoding job, then calling the cancel endpoint as an admin user, and verifying the job status changes to "cancelled".

**Acceptance Scenarios**:

1. **Given** a geocoding job exists with status "running", **When** an administrator sends a cancel request for that job, **Then** the job status changes to "cancelled" and `completed_at` is set to the current time.
2. **Given** a geocoding job exists with status "pending", **When** an administrator sends a cancel request for that job, **Then** the job status changes to "cancelled" and `completed_at` is set.
3. **Given** a geocoding job exists with status "completed", **When** an administrator sends a cancel request, **Then** the request is rejected with an error indicating the job is already in a terminal state.
4. **Given** a geocoding job exists with status "failed", **When** an administrator sends a cancel request, **Then** the request is rejected with an error indicating the job is already in a terminal state.
5. **Given** a user with "viewer" or "analyst" role attempts to cancel a job, **When** they send a cancel request, **Then** the request is rejected with a 403 Forbidden response.

---

### User Story 3 - Administrator Marks a Geocoding Job as Failed (Priority: P3)

An administrator identifies a geocoding job that has produced incorrect or partial results and needs to be marked as failed for record-keeping purposes. They mark it as failed through the API, optionally providing a reason.

**Why this priority**: Provides administrative flexibility beyond simple cancellation. Useful for cases where a job technically completed but produced bad data, or where an administrator wants to explicitly flag a job as problematic.

**Independent Test**: Can be tested by calling the mark-as-failed endpoint on a running job and verifying the status change and optional reason are recorded.

**Acceptance Scenarios**:

1. **Given** a geocoding job exists with status "running", **When** an administrator marks it as failed with a reason, **Then** the job status changes to "failed", the reason is recorded in the error log, and `completed_at` is set.
2. **Given** a geocoding job exists with status "pending", **When** an administrator marks it as failed without a reason, **Then** the job status changes to "failed" and `completed_at` is set.
3. **Given** a geocoding job is already in a terminal state ("completed", "failed", "cancelled"), **When** an administrator attempts to mark it as failed, **Then** the request is rejected.

---

### Edge Cases

- What happens when the server restarts while no geocoding jobs table exists yet (fresh database before migrations)? The recovery should silently succeed without errors.
- What happens when an administrator cancels a job that is actively processing records? The status update in the database takes effect immediately. The background task re-reads the job status before each batch and stops processing when it detects the terminal state, respecting the cancellation at the next batch boundary.
- What happens when two administrators attempt to cancel the same job simultaneously? Only one should succeed; the second should see the job is already in a terminal state.
- What happens when a job has been "running" for a legitimate long time (e.g., a large county batch)? Automatic recovery only runs on server restart, not on a timer, so long-running legitimate jobs are not affected during normal operation.

## Clarifications

### Session 2026-02-25

- Q: Should the background task be modified to check for cancellation (current code only handles KeyboardInterrupt/CancelledError, not DB status changes)? → A: Yes — add a status check to the processing loop (re-read job status from DB before each batch; stop if terminal).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automatically mark all geocoding jobs with status "running" or "pending" as "failed" when the server starts up, following the same pattern used for analysis run recovery.
- **FR-002**: System MUST set the `completed_at` timestamp to the current time when recovering stale geocoding jobs on startup.
- **FR-003**: System MUST append a descriptive note to the job's error log when recovering stale jobs, indicating the job was interrupted by a server restart.
- **FR-004**: System MUST preserve any existing error log entries when appending the recovery note.
- **FR-005**: System MUST log a warning with the count of recovered geocoding jobs when any are found during startup recovery.
- **FR-006**: System MUST silently handle the case where the geocoding jobs table does not yet exist (e.g., fresh database before migrations).
- **FR-007**: System MUST provide an endpoint for administrators to cancel a geocoding job that is in a non-terminal state ("running" or "pending").
- **FR-008**: System MUST provide an endpoint for administrators to mark a geocoding job as failed, with an optional reason.
- **FR-009**: System MUST reject cancel or mark-as-failed requests for jobs already in a terminal state ("completed", "failed", "cancelled") with an appropriate error message.
- **FR-010**: System MUST restrict the cancel and mark-as-failed endpoints to users with the "admin" role.
- **FR-011**: System MUST set `completed_at` to the current time when a job is cancelled or marked as failed via the endpoints.
- **FR-012**: The background geocoding task MUST re-read the job status from the database before processing each batch and stop processing if the status has been changed to a terminal state ("cancelled" or "failed").

### Key Entities

- **GeocodingJob**: Existing entity representing a batch geocoding operation. Key attributes relevant to this feature: `status` (pending, running, completed, cancelled, failed), `completed_at`, `error_log` (structured log of errors and notes), `triggered_by` (the user who created the job).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a server restart, 100% of previously "running" or "pending" geocoding jobs are marked as "failed" within the startup sequence, before the server begins accepting requests.
- **SC-002**: Administrators can cancel or mark-as-failed any non-terminal geocoding job in a single request, receiving confirmation within 2 seconds.
- **SC-003**: The job listing returns zero phantom "running" jobs after a server restart, giving administrators an accurate view of system status.
- **SC-004**: Non-admin users are prevented from cancelling or modifying job statuses, with 100% of unauthorized attempts rejected.

## Assumptions

- The existing GeocodingJob model's `error_log` field (structured array) is suitable for appending recovery notes without schema changes.
- The "cancelled" status already exists in the GeocodingJob model and is a valid terminal state.
- The background geocoding task will be modified to re-read the job status from the database before each batch. If the status has been changed to a terminal state (e.g., by an admin cancellation), the task will stop processing and exit gracefully. This is new behavior — the current code only handles `KeyboardInterrupt`/`asyncio.CancelledError`, not DB-level status changes.
- No new database migration is needed — all required fields and statuses already exist on the GeocodingJob model.
- The stale job recovery runs once at server startup (not on a periodic timer), consistent with the analysis run recovery pattern.
