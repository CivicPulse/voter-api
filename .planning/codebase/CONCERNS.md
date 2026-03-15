# Codebase Concerns

**Analysis Date:** 2026-03-13

---

## Tech Debt

**In-process background task runner is an MVP placeholder:**
- Issue: `InProcessTaskRunner` in `src/voter_api/core/background.py` runs import/geocoding/analysis jobs as `asyncio.create_task()` within the same process. Heavy jobs (500 MB voter CSV, full geocoding batch) compete with request handling for event loop time, and crashes lose all queued work. The code itself notes "Suitable for development and MVP."
- Files: `src/voter_api/core/background.py`, `src/voter_api/api/v1/imports.py`
- Impact: High memory pressure on the single uvicorn worker during bulk imports; if the process dies mid-job, the job is left in `running` state until startup recovery runs.
- Fix approach: Replace `InProcessTaskRunner` with an out-of-process worker (ARQ + Redis, or Celery). The `BackgroundTaskRunner` Protocol in `background.py` was designed to make this swap easy.

**Settings re-instantiated on every call inside services:**
- Issue: `get_settings()` in `src/voter_api/core/config.py` calls `Settings()` (constructs a fresh Pydantic Settings object) on every invocation. This means reading from environment variables and validating constraints on every request that calls `get_settings()` in a hot path. There are 53 call sites across 22 files.
- Files: `src/voter_api/core/config.py:453`, used in `src/voter_api/services/auth_service.py`, `src/voter_api/services/geocoding_service.py`, `src/voter_api/api/v1/geocoding.py`, and 18 other files.
- Impact: Negligible per-call cost but adds up; prevents caching/singleton pattern.
- Fix approach: Apply `@lru_cache` or `functools.cache` to `get_settings()` so settings are parsed once and reused.

**Rate limiter state is in-process only:**
- Issue: `RateLimitMiddleware` in `src/voter_api/api/middleware.py` stores `_request_counts` as a plain dict on the middleware instance. Multiple uvicorn workers (if run with `--workers N`) each have independent counters.
- Files: `src/voter_api/api/middleware.py:103`
- Impact: Under multi-worker deployment, rate limiting is effectively divided by worker count — a client can exceed the configured limit `N` times.
- Fix approach: Move rate-limit counters to Redis, or use a dedicated library (slowapi with Redis backend).

**Import county detection reads only the first record of the first chunk:**
- Issue: `_process_chunk()` in `src/voter_api/services/import_service.py` detects the county from `records[0].get("county")`. Then `process_voter_import()` only captures the county the first time it is detected (`if import_county is None and detected_county`). If a multi-county voter file is imported (e.g. a state-wide file with interleaved counties), only the first county encountered is used for soft-delete scoping — voters from other counties are not soft-deleted.
- Files: `src/voter_api/services/import_service.py:416`, `src/voter_api/services/import_service.py:517-519`
- Impact: Silent data integrity issue. Voters removed from a GA SoS statewide file are not marked `present_in_latest_import=False` if their county was not the first encountered.
- Fix approach: Accumulate all detected counties into a set across all chunks and scope the soft-delete to all counties seen in the file.

**S3/R2 publisher uses synchronous boto3 in an async application:**
- Issue: `src/voter_api/lib/publisher/storage.py` uses the synchronous `boto3` client directly (blocking calls). All calls to `upload_file`, `upload_manifest`, and `fetch_manifest` block the asyncio event loop.
- Files: `src/voter_api/lib/publisher/storage.py`
- Impact: During a large boundary dataset publish, the event loop is blocked for the duration of the upload, preventing any other requests from being served.
- Fix approach: Wrap boto3 calls in `asyncio.get_event_loop().run_in_executor(None, ...)`, or switch to `aioboto3` / `s3transfer` async client.

**AI resolver uses synchronous `time.sleep()` in retry backoff:**
- Issue: `_call_api()` in `src/voter_api/lib/candidate_importer/ai_resolver.py:219` calls `time.sleep(backoff)` for exponential backoff between Anthropic API retries, blocking the asyncio event loop.
- Files: `src/voter_api/lib/candidate_importer/ai_resolver.py:219`
- Impact: Entire API is unresponsive during retry backoff (up to 8 seconds per retry).
- Fix approach: Replace with `await asyncio.sleep(backoff)` and make the call chain async, or move AI resolution to a background worker thread.

**Analysis service calls spatial queries one voter at a time:**
- Issue: `_analyze_voter()` in `src/voter_api/services/analysis_service.py` issues a separate `find_boundaries_for_point()` PostGIS query (`ST_Contains`) for every single voter in the batch. A batch of 100 voters = 100 database round-trips before the batch is committed.
- Files: `src/voter_api/services/analysis_service.py:134`, `src/voter_api/lib/analyzer/spatial.py:14`
- Impact: For a county of 100,000 geocoded voters, the full analysis requires ~1,000 batches × 100 sequential spatial queries = 100,000 DB round-trips. Analysis of large counties is very slow.
- Fix approach: Rewrite to batch spatial queries — bulk-insert voter points into a temp table or use `VALUES` and cross-join with `ST_Contains` to resolve all voters in a batch in a single query.

**`get_import_diff()` returns all registration numbers without pagination:**
- Issue: `get_import_diff()` in `src/voter_api/services/import_service.py:677` loads all added, removed, and updated voter registration numbers into Python lists. For a 700,000-voter county import, this could return lists with hundreds of thousands of items.
- Files: `src/voter_api/services/import_service.py:694-716`
- Impact: OOM risk on large county imports; API response payload is unbounded.
- Fix approach: Add pagination to the diff endpoint, or return only counts with a separate paginated "added voters" endpoint.

---

## Known Bugs

**Multi-county voter file soft-delete is incorrect:**
- Symptoms: Voters in counties other than the first county in a multi-county import file are never soft-deleted even if they are absent from the import.
- Files: `src/voter_api/services/import_service.py:415-416`, `src/voter_api/services/import_service.py:517-519`
- Trigger: Upload a voter CSV containing more than one county's data. Voters absent from county B are not marked as deleted if county A was detected first.
- Workaround: Import files one county at a time.

**Soft-delete check loads all county registration numbers into Python memory:**
- Symptoms: `_soft_delete_absent_voters()` fetches every `voter_registration_number` for the county using `scalars().all()` and builds a Python set. For a large county (e.g. Fulton with ~600,000 voters), this is a 600,000-element Python set.
- Files: `src/voter_api/services/import_service.py:112-118`
- Trigger: Any import of a large county voter file.
- Workaround: None currently; this works but consumes significant memory.

---

## Security Considerations

**Voter PII (addresses) may appear in geocoding-related error logs:**
- Risk: Several geocoder services log the address string on error paths. While the major geocoders (`census`, `nominatim`, `photon`, `geocodio`, `google_maps`, `mapbox`) redact addresses in timeouts, the generic `GeocodingProviderError` message in `_geocode_with_retry()` logs `{e}` which may include the address from the exception message depending on provider.
- Files: `src/voter_api/services/geocoding_service.py:763`, `src/voter_api/api/v1/geocoding.py:154`
- Current mitigation: Most geocoder providers log "(redacted)" for timeouts. Voter registration numbers are masked via `_mask_vrn()` in voter history and absentee services.
- Recommendations: Audit all `GeocodingProviderError` exception messages; ensure provider error messages strip address from the exception string. Apply `_mask_vrn()` pattern to any geocoding-related log that includes voter IDs or addresses.

**Geocoding API keys are stored as plain strings in Settings, not SecretStr:**
- Risk: `geocoder_google_api_key`, `geocoder_geocodio_api_key`, `geocoder_mapbox_api_key` in `src/voter_api/core/config.py` are typed `str | None`, not `SecretStr`. They will appear in plain text in any settings repr/dump, debug logging, or Pydantic serialization.
- Files: `src/voter_api/core/config.py:95`, `src/voter_api/core/config.py:111`, `src/voter_api/core/config.py:132`
- Current mitigation: `anthropic_api_key` is already `SecretStr`; `mailgun_api_key` is `str` (also unprotected).
- Recommendations: Change all API key fields to `SecretStr` and update call sites to use `.get_secret_value()`.

**CORS: no `allow_origins` fallback if neither `cors_origins` nor `cors_origin_regex` is set:**
- Risk: If both `CORS_ORIGINS` and `CORS_ORIGIN_REGEX` are empty (which is the default), `setup_cors()` in `src/voter_api/api/middleware.py` calls `app.add_middleware(CORSMiddleware, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])` with **no `allow_origins` or `allow_origin_regex`**. Starlette's `CORSMiddleware` treats this as blocking all cross-origin requests (no `Access-Control-Allow-Origin` header), but credential-bearing requests from a frontend may behave unexpectedly.
- Files: `src/voter_api/api/middleware.py:54-63`
- Current mitigation: Deployment docs note CORS must be explicitly configured.
- Recommendations: Add a startup validation warning or raise an error if neither CORS setting is provided and the environment is not `development`.

**JWT tokens have no revocation mechanism:**
- Risk: Issued access tokens (30-minute default) and refresh tokens (7-day default) cannot be revoked. A compromised token is valid until expiry even after the user's password is changed or account is deactivated.
- Files: `src/voter_api/core/security.py`, `src/voter_api/services/auth_service.py`
- Current mitigation: `get_current_user()` checks `user.is_active` on every request, so deactivating a user account limits exposure to the token TTL window.
- Recommendations: Implement a token denylist (Redis or DB table) and invalidate tokens on password change and logout. Alternatively, shorten access token TTL significantly.

**Password reset token is single-use but deletion is deferred:**
- Risk: `PasswordResetToken` is marked used by updating `used_at`, but old used tokens are not automatically purged. A high-volume password reset attempt could accumulate many rows.
- Files: `src/voter_api/models/auth_tokens.py`, `src/voter_api/services/auth_service.py`
- Current mitigation: Rate limiting via `reset_rate_limit_minutes` (5 min default) limits abuse.
- Recommendations: Add a periodic cleanup job or Alembic-driven scheduled DELETE for tokens older than 24 hours.

---

## Performance Bottlenecks

**Bulk voter import loads entire uploaded file into memory before writing to disk:**
- Problem: `import_voters()` in `src/voter_api/api/v1/imports.py:81` calls `content = await file.read()` on the entire UploadFile, loading up to 500 MB into memory, then writes it to a temp file. This doubles memory use per active upload.
- Files: `src/voter_api/api/v1/imports.py:78-88` and same pattern for voter history (line 138), candidate import (line 200), and other import endpoints.
- Cause: Using `file.read()` instead of streaming chunks to the temp file.
- Improvement path: Stream via `aiofiles` using `file.read(chunk_size)` in a loop to write to the temp file without buffering the entire payload.

**ST_Contains spatial queries are issued per-voter in analysis runs:**
- Problem: The analysis service (100-voter batches) issues 100 individual PostGIS `ST_Contains` queries per batch. For large counties, this is extremely slow.
- Files: `src/voter_api/services/analysis_service.py:133-134`, `src/voter_api/lib/analyzer/spatial.py:14`
- Cause: Per-voter function design in `_analyze_voter()`.
- Improvement path: Collect all voter points for a batch, issue a single SQL query joining points against boundaries, and process the entire result set.

**Export service fetches all matching voters into memory for writing:**
- Problem: `_fetch_export_records()` in `src/voter_api/services/export_service.py:116` executes `select(Voter)` and returns all results as a list before writing. An export of 700,000 voters loads all ORM objects.
- Files: `src/voter_api/services/export_service.py:116-151`
- Cause: No streaming/cursor-based iteration.
- Improvement path: Use `yield_per()` on the SQLAlchemy query (server-side cursor) and stream records to the exporter.

**Geocoding service issues one ST_Contains status check per voter batch (cooperative cancellation):**
- Problem: `process_geocoding_job()` in `src/voter_api/services/geocoding_service.py:521` re-queries `GeocodingJob.status` from the database before every batch to detect external cancellation. At the default batch size, this adds a status-check query per 100 voters.
- Files: `src/voter_api/services/geocoding_service.py:519-535`
- Cause: Cancellation detection implemented via DB polling.
- Improvement path: Use an in-memory flag or asyncio `Event` set by the cancel endpoint, falling back to DB check only on exception/timeout.

---

## Fragile Areas

**`_DROPPABLE_INDEXES` list is hardcoded in both `import_service.py` and duplicated in `voter_history_service.py`:**
- Files: `src/voter_api/services/import_service.py:58-91`, `src/voter_api/services/voter_history_service.py:45-74`
- Why fragile: If a new index is added to the `voters` or `voter_history` table via an Alembic migration without updating these lists, the index is maintained during bulk imports (slower) without error. If an index is renamed in the migration without updating the list, `DROP INDEX IF EXISTS` silently does nothing, leaving the old index in place.
- Safe modification: When adding new indexes to `voters` or `voter_history` via migration, also add them to the corresponding `_DROPPABLE_INDEXES` list.
- Test coverage: No test verifies that the hardcoded names match the actual database index names.

**Bulk import teardown in `finally` block may silently fail to rebuild indexes:**
- Files: `src/voter_api/services/import_service.py:575-588`, `src/voter_api/services/voter_history_service.py:176-186`
- Why fragile: The `finally` block catches and logs `Exception` during index rebuild, but if the connection is broken at that point (e.g. the DB restarted), the indexes are left in a dropped state. The startup `_verify_import_db_state()` in `src/voter_api/main.py` provides crash recovery, but only checks by index name — not by schema completeness.
- Safe modification: Monitor the "indexes may need manual rebuild" log line in production. The startup recovery in `main.py` handles the common crash case.
- Test coverage: Crash recovery path is tested in `tests/unit/test_main_recovery.py` but does not cover partial index rebuild failure.

**`InProcessTaskRunner` semaphore is lazily created per event loop:**
- Files: `src/voter_api/core/background.py:63-80`
- Why fragile: The `WeakKeyDictionary` keyed by `asyncio.AbstractEventLoop` was added to fix "attached to a different loop" errors in tests. This is a workaround for the global singleton pattern — the module-level `task_runner` is shared across test sessions that spin up different event loops.
- Safe modification: Do not add `asyncio.run()` calls that create new event loops without resetting the `task_runner` singleton.

**`VoterHistory` has no FK to `voters` table — join is by registration number at query time:**
- Files: `src/voter_api/models/voter_history.py:20-22`
- Why fragile: The model comment explicitly states "The voter association is lazy — records join to voters by registration number at query time rather than via a foreign key." If a voter's registration number changes (theoretical per GA SoS policy), voter history records become silently orphaned. There is no referential integrity constraint.
- Safe modification: Voter history queries must always join on `voter_registration_number`; never assume `voter_id` FK.

---

## Scaling Limits

**asyncpg 32,767 parameter limit constrains batch sizing:**
- Current capacity: Voter upsert sub-batches are capped at 500 rows (50 columns × 500 = 25,000 params). Voter history sub-batches are 2,000 rows (11 columns × 2,000 = 22,000 params). Soft-delete IN clauses are capped at 5,000 IDs.
- Limit: If the Voter model gains more columns, `_UPSERT_SUB_BATCH` must be recalculated or the constant updated.
- Scaling path: If the column count grows significantly, reduce `_UPSERT_SUB_BATCH` accordingly. Current `_UPSERT_EXCLUDE_COLUMNS` set excludes 6 columns; document this dependency more explicitly.

**In-memory rate limiter does not scale horizontally:**
- Current capacity: Single-worker rate limiting works at the configured `rate_limit_per_minute` (default 200/minute).
- Limit: Adding more uvicorn workers divides the effective rate limit by the number of workers.
- Scaling path: Implement Redis-backed rate limiting.

**`get_import_diff()` unbounded list loading:**
- Current capacity: Loads all added/removed/updated registration numbers into Python lists. Fine for county-level imports (~5,000–50,000 voters).
- Limit: State-wide imports (~7 million voter records) would produce lists too large to serialize as a JSON response.
- Scaling path: Paginate the diff endpoint; return only counts by default.

---

## Dependencies at Risk

**`mailgun` Python package lacks type stubs:**
- Risk: `src/voter_api/lib/mailer/mailer.py:6` imports `from mailgun.client import AsyncClient` with a `# type: ignore[import-untyped]` comment. The `mailgun` Python package has no type stubs.
- Impact: No static type checking on mailer interactions; type errors in mailer code will be invisible to mypy.
- Migration plan: Contribute stubs upstream, or rewrite using `httpx` directly against the Mailgun REST API to eliminate the untyped dependency.

**`boto3` is synchronous and blocks the async event loop:**
- Risk: `src/voter_api/lib/publisher/storage.py` uses synchronous `boto3` for R2/S3 operations.
- Impact: Any publish operation blocks the event loop.
- Migration plan: Replace with `aioboto3` or wrap calls in `run_in_executor`.

---

## Missing Critical Features

**No background job queue persistence or retry across restarts:**
- Problem: All background jobs (imports, geocoding, analysis) run as `asyncio.Task` objects. If uvicorn restarts, all in-flight tasks are lost. The startup recovery marks them as `failed`, but does not retry them.
- Blocks: Reliable large-file import processing; guaranteed-delivery geocoding runs.

**No geocoding cache expiry/TTL:**
- Problem: The `geocoder_cache` table has no TTL column or cleanup mechanism. Cached geocoding results accumulate indefinitely. An address that was incorrectly geocoded remains wrong forever unless manually evicted.
- Files: `src/voter_api/lib/geocoder/cache.py`, `src/voter_api/models/geocoder_cache.py`
- Blocks: Accurate re-geocoding after address data corrections.

**No audit trail for voter data modifications:**
- Problem: The `audit_log` table and `AuditLog` model exist (`src/voter_api/models/audit_log.py`) but there is an `AuditService` (`src/voter_api/services/audit_service.py`). Searching for usage of this service in routes shows it is not consistently applied to all write endpoints — particularly import operations do not log individual field-level changes.
- Files: `src/voter_api/models/audit_log.py`, `src/voter_api/services/audit_service.py`
- Blocks: Compliance audit requirements for voter data changes.

---

## Test Coverage Gaps

**Performance tests directory is empty:**
- What's not tested: The `tests/performance/` directory exists with only `__init__.py` and a `fixtures/` subdirectory (also empty). No performance benchmarks or load tests exist.
- Files: `tests/performance/`
- Risk: Import performance regressions (bulk upsert optimization, index drop/rebuild) could be introduced undetected. The CLAUDE.md documents a 90% coverage threshold but it is not enforced in pyproject.toml (no `--cov-fail-under` in addopts).
- Priority: Medium — documented threshold should be enforced; perf benchmarks for bulk import are high value.

**No coverage threshold enforced in CI:**
- What's not tested: CLAUDE.md states "90% threshold required" but `pyproject.toml:76` shows `addopts = "-ra -q"` — no `--cov-fail-under=90` flag.
- Files: `pyproject.toml:76`
- Risk: Coverage can silently drop below 90% without failing CI.
- Priority: Low to fix — add `--cov-fail-under=90` to addopts or a CI coverage gate.

**Multi-county import soft-delete behavior is not tested:**
- What's not tested: No test covers uploading a voter file with mixed counties and verifying correct soft-delete scoping.
- Files: `tests/unit/test_services/test_import_service.py`
- Risk: The county detection bug (see Tech Debt above) would not be caught by existing tests.
- Priority: High — this is an active data integrity concern.

**S3/R2 publisher storage uses moto mock but never tests event-loop blocking:**
- What's not tested: The sync nature of boto3 in the publisher is never tested under async load.
- Files: `tests/unit/lib/test_publisher/test_storage.py`
- Risk: No regression test for the blocking behavior.
- Priority: Low — mitigated once the boto3 → aioboto3 migration is done.

---

*Concerns audit: 2026-03-13*
