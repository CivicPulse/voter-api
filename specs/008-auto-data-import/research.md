# Research: Automated Data Download & Import

**Feature**: 008-auto-data-import
**Date**: 2026-02-20

## R1: HTTP Download Strategy

**Decision**: Use `httpx.AsyncClient` with streaming response for large file downloads.

**Rationale**: httpx is already a project dependency (>=0.28.0) used in `election_tracker/fetcher.py` and `deploy_check_cmd.py`. Streaming avoids loading entire files into memory (the largest file is ~84 MB). The async client fits the existing async patterns.

**Alternatives considered**:
- `urllib.request` — stdlib, but no async support, less ergonomic error handling
- `aiohttp` — would add a new dependency; httpx already covers this
- `boto3` direct R2 access — would require R2 credentials; the Data Root serves files over public HTTPS without auth

**Implementation pattern** (from election_tracker):
```python
async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
    async with client.stream("GET", url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes(chunk_size=8192):
            ...
```

## R2: Checksum Verification Approach

**Decision**: Compute SHA512 from downloaded bytes and compare against the manifest's expected hash. Reuse the same streaming `hashlib.sha512` pattern from `boundary_loader/checksum.py` but read expected hashes from the manifest (not companion `.sha512.txt` files).

**Rationale**: The manifest is the single source of truth per spec clarification. The existing `verify_sha512()` in `boundary_loader` reads from companion `.txt` files — this feature needs a different source but the same hashing logic.

**Alternatives considered**:
- Reuse `verify_sha512()` directly — would require generating `.sha512.txt` files for every download; adds complexity
- Skip checksum on download, verify later — loses the ability to discard corrupted files immediately

## R3: Atomic File Writes (FR-011)

**Decision**: Download to a temporary file (`.part` suffix) in the same directory, then rename to final path on success. On failure, delete the `.part` file.

**Rationale**: `os.rename()` is atomic on the same filesystem. This prevents half-written files from being mistaken for complete downloads on retry.

**Alternatives considered**:
- Download to a separate temp directory then move — risks cross-filesystem moves which aren't atomic
- Download in-place — leaves corrupted partial files on failure

## R4: Remote Manifest Format

**Decision**: JSON file at `{data_root_url}/manifest.json` with a flat file list. Each entry has: filename, sha512, category, size_bytes.

**Rationale**: JSON is simple, widely supported, and consistent with the publisher library's manifest pattern. A flat list (not nested by category) keeps the format simple and lets the client do filtering.

**Alternatives considered**:
- YAML — adds a dependency (pyyaml not currently used)
- Parse `data.md` markdown — fragile, depends on table formatting
- CSV manifest — less expressive for metadata

**Schema**: See `contracts/manifest-schema.json`

## R5: CLI Command Name and Location

**Decision**: `voter-api seed` as a top-level Typer command, not under the `import` subgroup.

**Rationale**: The command orchestrates downloads + multiple import types (boundaries, voters, county-districts). Placing it under `import` would be confusing since it does more than import. "seed" communicates the primary use case (bootstrapping environments with data).

**Alternatives considered**:
- `voter-api import seed` — misleading; the command downloads first, then imports
- `voter-api import all` — conflicts conceptually with existing `import all-boundaries`
- `voter-api data sync` — "sync" implies bidirectional; this is one-way download+import

## R6: Progress Reporting

**Decision**: Use `tqdm` for download progress bars (per-file with bytes progress) and `typer.echo()` for import status messages.

**Rationale**: tqdm is already a dependency and provides rich terminal progress bars. The existing import commands already use `typer.echo()` for status output.

## R7: Import Orchestration — Direct Function Calls vs Subprocess

**Decision**: Call the existing async import functions directly (`_import_voters`, `_import_all_boundaries`, `_import_county_districts`) rather than spawning subprocesses.

**Rationale**: Direct calls share the database session factory, avoid process overhead, and allow proper error propagation. The existing import functions are already async and independently callable.

**Alternatives considered**:
- `subprocess.run(["voter-api", "import", ...])` — process overhead, harder error handling, requires re-initializing the database engine in each subprocess

## R8: Data Root URL Configuration

**Decision**: Add `data_root_url` as an optional setting in `Settings` with default `https://data.hatchtech.dev/`. Overridable via `--data-root` CLI argument.

**Rationale**: Follows 12-factor configuration (Principle IV). The default matches the current R2 public URL. Being optional with a sensible default means no configuration needed for the common case.

**Note**: This is separate from the existing `r2_public_url` setting (which is for the publisher feature writing to R2, not reading from it).
