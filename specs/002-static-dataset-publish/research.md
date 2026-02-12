# Research: Static Dataset Publishing

**Feature**: 002-static-dataset-publish
**Date**: 2026-02-12

## Decision 1: S3 Client Library

**Decision**: Use `boto3` as the sole S3 client library.

**Rationale**: boto3 is the gold standard for S3-compatible storage in Python, with the largest community and the most documentation for Cloudflare R2 (Cloudflare's own docs use boto3 examples). For the API-side manifest fetch (a small JSON file every 5 minutes), wrapping boto3 in `asyncio.to_thread()` is negligible overhead compared to adding a second async library dependency. This keeps the dependency tree simple and means only one S3 client to learn and maintain.

**Alternatives considered**:
- `aiobotocore` / `aioboto3` — Native async support, but adds complexity and a second library. The manifest fetch is too infrequent (5-min TTL) to justify async overhead.
- `minio` — Simpler API and no checksum issue, but smaller community, no async support, and Cloudflare's R2 docs don't reference it.
- `s3fs` — Wrong abstraction (filesystem metaphor for data science). Overkill for targeted upload/download operations.

## Decision 2: R2-Specific Configuration

**Decision**: Use boto3 with R2-specific configuration to work around the checksum issue introduced in boto3 v1.36.0+.

**Rationale**: boto3 v1.36.0+ introduced automatic checksum calculations that break R2 compatibility. The fix is a one-line config addition.

**Required configuration**:
```python
from botocore.config import Config

config = Config(
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
)
```

**R2 endpoint format**: `https://{account_id}.r2.cloudflarestorage.com`
**R2 region**: Always `"auto"` for R2.

## Decision 3: Atomic Upload Strategy

**Decision**: Use ordered upload (data files first, manifest last) rather than temp-key + copy.

**Rationale**: S3 and R2 both provide strong read-after-write consistency. A `PutObject` overwrite is atomic per-key — readers see either the complete old object or the complete new object. By uploading all GeoJSON files first and the manifest last, the manifest acts as an atomic "commit" — by the time it's visible, all referenced files already exist. The temp-key + copy pattern adds complexity without benefit for single-key writes.

**Upload order**:
1. Upload all per-type GeoJSON files (e.g., `boundaries/congressional.geojson`)
2. Upload the combined file (`boundaries/all-boundaries.geojson`)
3. Upload `manifest.json` last (the "commit")

**Alternatives considered**:
- Temp-key + copy + delete — Adds 2 extra API calls per file. Useful for cross-key atomicity but unnecessary here since each key is independently atomic and the manifest controls visibility.

## Decision 4: Multipart Upload Configuration

**Decision**: Use boto3 `TransferConfig` with a 25 MB multipart threshold.

**Rationale**: Georgia boundary GeoJSON files are typically 1–50 MB. A 25 MB threshold means most files upload as a single PUT (simpler, fewer API calls) while very large files still get multipart. R2 requires all multipart parts (except the last) to be at least 5 MB and the same size.

**Configuration**:
```python
TransferConfig(
    multipart_threshold=25 * 1024 * 1024,   # 25 MB
    multipart_chunksize=25 * 1024 * 1024,    # 25 MB
    max_concurrency=4,
    use_threads=True,
)
```

## Decision 5: Public Access on R2

**Decision**: Public access is configured at the bucket level via Cloudflare R2's custom domain or r2.dev subdomain. The application does not set per-object ACLs.

**Rationale**: R2 does not support S3-style per-object ACLs (`x-amz-acl: public-read`). Public access is controlled entirely at the bucket level through:
- **Custom domain** (production): Connect a domain (e.g., `geo.example.com`) to the R2 bucket. Enables Cloudflare CDN caching, WAF, and access controls.
- **r2.dev subdomain** (development): Cloudflare provides a `*.r2.dev` URL. Rate-limited, no caching, development only.

**Implication for the application**: The publish command uploads files to R2 without setting ACLs. The public URL prefix is configured via environment variable (pointing to the custom domain or r2.dev URL). The application constructs redirect URLs using this prefix.

## Decision 6: Testing Strategy for S3

**Decision**: Use `moto` for mocking S3 in unit/integration tests.

**Rationale**: `moto` is the standard mocking library for boto3/AWS services. It provides a full in-memory S3 implementation that supports all operations used in this feature (PutObject, GetObject, CopyObject, multipart). No external services needed for testing.

**Dependencies**: `uv add --dev moto[s3]`

## Decision 7: Library Placement

**Decision**: Create a new `lib/publisher/` library following the library-first architecture pattern.

**Rationale**: The constitution requires all features to be implemented as standalone libraries. The publisher library will handle:
- GeoJSON generation from boundary data (stateless, takes boundary dicts as input)
- S3 upload operations (takes boto3 client as dependency)
- Manifest generation and parsing

The library must be independently testable without the database or FastAPI — it operates on plain dicts and file-like objects.

## Decision 8: Manifest Cache in API

**Decision**: Use a simple in-memory cache with TTL-based expiration, implemented as a module-level singleton.

**Rationale**: The manifest is a small JSON file (< 1 KB for ~31 boundary types). A module-level cache with a 5-minute TTL is the simplest approach. No need for Redis or external cache — the manifest is fetched infrequently and is small enough to hold in memory. The cache should be thread-safe but does not need distributed coordination (each API instance maintains its own cache).

**Alternatives considered**:
- Redis cache — Overkill for a single small JSON file fetched every 5 minutes.
- Database cache — Adds unnecessary database dependency to the redirect path, defeating the purpose of offloading from the database.
- On-demand refresh via admin endpoint — Requires an extra step after publishing, worse UX.
