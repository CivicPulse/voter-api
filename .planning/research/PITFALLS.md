# Domain Pitfalls

**Domain:** Three-stage data import pipeline (SOS -> Markdown -> JSONL -> DB)
**Researched:** 2026-03-13

## Critical Pitfalls

Mistakes that cause rewrites or major data quality issues.

### Pitfall 1: AI-Generated Markdown Drift Between Runs

**What goes wrong:** Claude Code skills process the same SOS CSV on Monday and produce "Board of Education At Large-Post 7". The same skill on Friday produces "Board of Education at Large-Post 7" (lowercase "at"). Spurious git diffs. Worse, the deterministic MD-to-JSONL converter treats these as different contest names, creating duplicate election records. This already happened -- COUNTY-FORMAT.md documents exact Title Case rules precisely because AI normalization was inconsistent across the initial 159 county file generation.

**Why it happens:** LLMs are non-deterministic for formatting tasks. Even with temperature=0, tokenization differences cause subtle variation in capitalization, whitespace, em-dash vs en-dash, and abbreviation expansion.

**Consequences:** Duplicate elections in DB; broken candidate-to-election linkage; unreliable git diffs.

**Prevention:**
1. Move ALL normalization (Title Case, acronym expansion, URL lowercasing, em-dash insertion) into a deterministic Python post-processing script
2. The skill outputs raw SOS data with minimal transformation; normalizer enforces rules programmatically
3. Run normalizer as git pre-commit hook or CI step on `data/elections/**/*.md`
4. Add diff-level validation: re-generating an existing file should flag unexpected structural changes

**Detection:** Git diffs showing only capitalization/punctuation/whitespace changes; metadata counts not matching actual table rows; duplicate elections with near-identical names.

### Pitfall 2: AI Hallucinating Candidate Data

**What goes wrong:** The skill encounters ambiguous SOS data (occupation "Ret", unusual name formatting) and "helpfully" expands "Ret" to "Retired" when the actual occupation was "Retail", or infers an email address that doesn't exist in the source. Hallucinated data enters markdown, passes human review (it looks plausible), converts to JSONL, loads into DB. Election data accuracy has legal and democratic implications.

**Why it happens:** LLMs fill gaps by design. Semi-structured input is treated as an opportunity for inference. The existing COUNTY-FORMAT.md says "Full name (no normalization)" for candidates, but the skill operator may not enforce this consistently.

**Consequences:** Incorrect public records in the database; eroded trust in the platform.

**Prevention:**
1. Skill instructions must include explicit "never infer, only extract" directive
2. Fields not present in source must be em-dash, never guessed
3. Implement JSONL-level cross-reference validation against original SOS CSV
4. Occupation normalization: keep a hardcoded allowlist of transformations; reject anything not on the list

**Detection:** Markdown files with data not in source CSV; email addresses that bounce; occupation values more detailed than terse SOS format.

### Pitfall 3: JSONL Foreign Key Ordering Breaks Imports

**What goes wrong:** Candidate JSONL imported before election JSONL. FK violation on `candidates.election_id`. Or worse: election re-import with regenerated UUIDs orphans all candidates referencing old IDs. The DATA_QUALITY_REPORT documents this pattern -- 100% of elections missing boundary_id because boundary backfill ran before elections were properly linked.

**Why it happens:** Multi-entity imports have implicit ordering dependencies (elections before candidates, boundaries before elections). Developers build for the "happy path" but don't enforce ordering.

**Consequences:** FK violations; orphaned candidates; silent data corruption.

**Prevention:**
1. Use stable, deterministic IDs -- hash of natural key (e.g., `SHA256(election_date + district_type + district_identifier + party)` truncated to UUID), NOT random UUIDs
2. Import CLI must validate FK dependencies before loading
3. Support manifest files declaring import ordering: `["elections.jsonl", "candidates.jsonl"]`
4. Consider `DEFERRABLE INITIALLY DEFERRED` FK constraints for within-transaction flexibility

**Detection:** FK violation errors; candidates with null/broken election_id; record count mismatches after re-imports.

### Pitfall 4: Markdown Table Parsing Edge Cases

**What goes wrong:** The MD-to-JSONL converter encounters pipe characters in content, em-dashes that render differently across platforms, trailing whitespace, or markdown links with special characters. Parser produces corrupted records with shifted column values.

**Why it happens:** Markdown tables are not a robust data interchange format. CommonMark doesn't even define table syntax (it's a GFM extension). Real examples from existing files:
- `Civil/Magistrate Court Judge` -- `/` is fine but could become `Civil|Magistrate` in corrupt edit
- `[mortonforschools.org](https://mortonforschools.org)` -- multiple special chars in link syntax
- Long occupation strings could trigger line wrapping

**Consequences:** Corrupted JSONL records; wrong field values in wrong columns.

**Prevention:**
1. Use mistune's AST renderer for table extraction -- handles escaped pipes, whitespace, alignment markers correctly
2. Structural validator before conversion: verify column count matches header for every row
3. Add YAML frontmatter for machine-readable metadata instead of parsing from markdown tables
4. Round-trip tests: generate markdown from known data, parse back, verify field-level equality

**Detection:** JSONL records with shifted/concatenated values; parse errors on specific county files but not others; metadata counts not matching parsed row counts.

### Pitfall 5: Two PostgreSQL Drivers (asyncpg + psycopg) Connection Pool Conflicts

**What goes wrong:** The app uses asyncpg via SQLAlchemy for all ORM queries. Procrastinate adds psycopg v3 with its own AsyncConnectionPool. Both connect to the same database. If connection limits are not properly sized, one pool starves the other. In worst case, both pools try to grab connections simultaneously during an import (procrastinate job fires, import writes via SQLAlchemy), exhausting the PostgreSQL `max_connections` limit.

**Why it happens:** procrastinate has no asyncpg connector. It requires psycopg. The codebase already uses asyncpg via SQLAlchemy. Two independent pools connecting to the same DB is architecturally sound but requires explicit connection budget planning.

**Consequences:** Connection pool exhaustion; "too many connections" errors; import failures under concurrent load.

**Prevention:**
1. Explicitly budget connections: if PostgreSQL allows 100 connections, allocate 20 to SQLAlchemy's asyncpg pool and 5 to procrastinate's psycopg pool, leaving headroom for psql, Alembic, monitoring
2. Procrastinate's PsycopgConnector pool: set `max_size = procrastinate_max_jobs + 1` (extra for LISTEN/NOTIFY channel)
3. Configure SQLAlchemy pool size in `database.py` to account for shared connection budget
4. Log pool utilization metrics from both pools to detect creeping exhaustion

**Detection:** "too many connections" PostgreSQL errors; intermittent connection timeouts; slow query starts during peak import processing.

## Moderate Pitfalls

### Pitfall 6: Georgia SOS Format Changes Between Election Cycles

**What goes wrong:** SOS adds/removes columns or changes headers between elections. Pipeline silently drops records or mismap fields. Already happened: `GENERAL ELECTION RUNOFF` and `PPP` were not in the original election type map, causing 133,636+ misclassified records.

**Prevention:**
1. Schema diff step before processing: compare CSV headers against expected schema, alert on deviations
2. Reject unknown election types rather than defaulting to "general"
3. Contest name parsing coverage report: flag any file where parsing coverage drops below 95%
4. Version the markdown format via frontmatter

### Pitfall 7: Background Job Worker Crashes Leave Imports in Liminal State

**What goes wrong:** Worker dies mid-import (OOM, deployment restart, DB timeout). Import job stuck in "running" status permanently. If procrastinate lock is held, subsequent imports blocked. Already documented: existing `cleanup_abandoned_jobs()` function exists precisely because this happened.

**Prevention:**
1. Checkpoint progress: `last_processed_line` on import job record (existing pattern in import_service.py)
2. Heartbeat mechanism: worker updates `heartbeat_at` every N seconds; periodic task detects stale jobs
3. Use `queueing_lock` (prevents duplicate submission) instead of `lock` (prevents duplicate processing)
4. Sub-transaction commits every N records; limits blast radius of crash

### Pitfall 8: Presigned URL Upload Without Content Validation

**What goes wrong:** Presigned URL generated, user uploads invalid JSONL / SQL injection payloads / 5GB garbage file. R2 presigned URLs are bearer tokens -- anyone with the URL can upload until expiry.

**Prevention:**
1. Short expiration (15 min to 1 hour, NOT the max 7 days)
2. ContentType restriction in presigned URL signature
3. Mandatory server-side validation job after upload completes
4. Never import directly from upload location; validate first, then process

### Pitfall 9: Procrastinate Schema Migration Drift from Alembic

**What goes wrong:** Procrastinate manages its own database schema (`procrastinate_jobs`, etc.) with pure SQL scripts. The app uses Alembic for all schema changes. Over time, these get out of sync -- procrastinate releases a new migration, nobody wraps it in an Alembic revision, deployment fails or procrastinate behaves unexpectedly.

**Prevention:**
1. Wrap procrastinate's initial schema in an Alembic migration using `op.execute()` with the SQL from procrastinate's schema files
2. Pin procrastinate version strictly (not just `>=`); upgrade deliberately
3. On procrastinate version bump, check for new SQL migrations and wrap each in a new Alembic revision
4. Add a CI check: verify procrastinate schema version matches the latest wrapped Alembic migration

## Minor Pitfalls

### Pitfall 10: JSONL File Encoding Issues

**What goes wrong:** JSONL files generated on one platform with different encoding (Windows UTF-16, BOM marker) fail to parse on the server.

**Prevention:** Always write JSONL as UTF-8 without BOM. Validate encoding in the validation step.

### Pitfall 11: Presigned URLs on Custom Domains

**What goes wrong:** Code generates presigned URLs using the R2 custom domain (e.g., `data.hatchtech.dev`) instead of the S3 API domain. Uploads fail with signature mismatch because R2 presigned URLs only work on `{ACCOUNT_ID}.r2.cloudflarestorage.com`.

**Prevention:** Always use the S3 API endpoint for presigned URL generation. The existing `create_r2_client()` already uses the correct endpoint.

### Pitfall 12: Metadata Count Mismatch

**What goes wrong:** Markdown metadata says "Contests: 5, Candidates: 12" but the actual tables have 4 contests and 11 candidates. Converter trusts metadata instead of counting actual records.

**Prevention:** The converter should count actual parsed records and warn (or error) if counts differ from metadata. Metadata is informational, not authoritative.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Markdown format enhancement | AI drift (P1), hallucination (P2) | Deterministic normalizer + source-fidelity constraints in skills |
| JSONL schema design | FK ordering (P3), non-deterministic IDs | Hash-based stable IDs; manifest-based import ordering |
| MD-to-JSONL converter | Table parsing (P4), encoding (P10) | mistune AST parser; round-trip tests on all 159 county files |
| Procrastinate integration | Two drivers (P5), schema drift (P9) | Connection budgeting; Alembic-wrapped migrations |
| R2 presigned URLs | Content validation (P8), custom domain (P11) | Short expiry; mandatory post-upload validation |
| JSONL import pipeline | Worker crashes (P7), FK ordering (P3) | Checkpointing; heartbeats; FK pre-validation |
| SOS data processing | Format changes (P6) | Schema diff step; reject-unknown-types policy |

## Sources

- `data/DATA_QUALITY_REPORT.md` -- 96.7% unresolved voter history, 100% missing boundary_id, election type mapping gaps
- `data/elections/formats/COUNTY-FORMAT.md` -- Title Case rules documenting prior AI drift
- `src/voter_api/services/import_service.py` -- Bulk upsert patterns, checkpoint tracking
- `src/voter_api/core/background.py` -- InProcessTaskRunner limitations
- [Cloudflare R2 Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/) -- Bearer token semantics, 7-day max, no custom domains
- [Procrastinate Docs -- Connectors](https://procrastinate.readthedocs.io/en/stable/howto/basics/connector.html) -- PsycopgConnector, pool sizing
- [Procrastinate Docs -- Migrations](https://procrastinate.readthedocs.io/en/stable/howto/production/migrations.html) -- Pure SQL migration scripts
- [Procrastinate Docs -- Schema](https://procrastinate.readthedocs.io/en/stable/howto/production/schema.html) -- Custom PG schema support

---

*Pitfalls research: 2026-03-13*
