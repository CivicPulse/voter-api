# Quickstart: Static Dataset Publishing

**Feature**: 002-static-dataset-publish

## Prerequisites

- voter-api installed and configured (`uv sync`)
- PostgreSQL + PostGIS running with boundaries imported
- Cloudflare R2 bucket created with public access enabled (custom domain or r2.dev)
- R2 API token with read/write permissions for the bucket

## Configuration

Add the following to your `.env` file:

```bash
# R2 / S3-Compatible Object Storage
R2_ENABLED=true
R2_ACCOUNT_ID=your-cloudflare-account-id
R2_ACCESS_KEY_ID=your-r2-access-key
R2_SECRET_ACCESS_KEY=your-r2-secret-key
R2_BUCKET=your-bucket-name
R2_PUBLIC_URL=https://geo.yourdomain.com
R2_PREFIX=
R2_MANIFEST_TTL=300
```

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `R2_ENABLED` | Yes | Set to `true` to enable publishing and redirect |
| `R2_ACCOUNT_ID` | Yes | Your Cloudflare account ID (found in R2 dashboard) |
| `R2_ACCESS_KEY_ID` | Yes | R2 API token access key ID |
| `R2_SECRET_ACCESS_KEY` | Yes | R2 API token secret access key |
| `R2_BUCKET` | Yes | Name of the R2 bucket |
| `R2_PUBLIC_URL` | Yes | Public URL prefix (custom domain or `https://pub-xxx.r2.dev`) |
| `R2_PREFIX` | No | Key prefix within bucket (default: empty) |
| `R2_MANIFEST_TTL` | No | Manifest cache TTL in seconds (default: 300) |

## CLI Commands

### Publish All Boundary Datasets

```bash
# Publish all boundary types + combined file
uv run voter-api publish datasets

# Publish with verbose progress
uv run voter-api publish datasets --verbose
```

### Publish Filtered Datasets

```bash
# Publish only congressional boundaries
uv run voter-api publish datasets --boundary-type congressional

# Publish only boundaries from state source
uv run voter-api publish datasets --source state

# Publish only Fulton county boundaries
uv run voter-api publish datasets --county Fulton
```

### Check Publish Status

```bash
# Show status of all published datasets
uv run voter-api publish status
```

Example output:
```
Published Datasets (last updated: 2026-02-12 15:30:00 UTC)
──────────────────────────────────────────────────────────
  all-boundaries.geojson    1,523 features   45.2 MB   2026-02-12 15:30:00
  congressional.geojson        14 features    2.3 MB   2026-02-12 15:30:00
  state_senate.geojson         56 features    8.1 MB   2026-02-12 15:30:00
  state_house.geojson         180 features   22.4 MB   2026-02-12 15:30:00
  county_precinct.geojson     892 features   41.7 MB   2026-02-12 15:30:00
  ...
```

## API Behavior

### Redirect (when datasets are published)

```bash
# Request the GeoJSON endpoint
curl -v http://localhost:8000/api/v1/boundaries/geojson

# Response: HTTP 302 redirect
< HTTP/1.1 302 Found
< Location: https://geo.yourdomain.com/boundaries/all-boundaries.geojson

# With boundary type filter
curl -v "http://localhost:8000/api/v1/boundaries/geojson?boundary_type=congressional"

# Response: HTTP 302 redirect to type-specific file
< HTTP/1.1 302 Found
< Location: https://geo.yourdomain.com/boundaries/congressional.geojson
```

### Fallback (when no published datasets or non-matching filter)

```bash
# Filters that don't match a static file fall back to database
curl "http://localhost:8000/api/v1/boundaries/geojson?county=Fulton"

# Response: HTTP 200 with GeoJSON from database (original behavior)
< HTTP/1.1 200 OK
< Content-Type: application/geo+json
```

### Publish Status API

```bash
# Check publish status (requires admin auth)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/boundaries/publish/status
```

## R2 Bucket Setup

### Create Bucket

1. Go to Cloudflare Dashboard > R2
2. Create a new bucket (e.g., `voter-api-datasets`)

### Enable Public Access

**Option A: Custom Domain (recommended for production)**
1. Go to bucket Settings > Custom Domains
2. Add your domain (e.g., `geo.yourdomain.com`)
3. Domain must be in your Cloudflare account

**Option B: r2.dev Subdomain (development only)**
1. Go to bucket Settings > Public Access
2. Enable r2.dev subdomain
3. Note the URL: `https://pub-xxx.r2.dev`

### Create API Token

1. Go to R2 > Manage R2 API Tokens
2. Create a token with "Object Read & Write" permissions
3. Scope to the specific bucket
4. Copy the Access Key ID and Secret Access Key

## Typical Workflow

```bash
# 1. Import boundary data (existing command)
uv run voter-api import all-boundaries

# 2. Publish to R2
uv run voter-api publish datasets

# 3. Verify status
uv run voter-api publish status

# 4. Start API server — GeoJSON endpoint now redirects to R2
uv run voter-api serve
```

## Troubleshooting

| Issue | Solution |
| ----- | -------- |
| "R2 publishing is not configured" | Set `R2_ENABLED=true` and all required R2 env vars |
| "Failed to connect to R2" | Check `R2_ACCOUNT_ID`, access key, and network connectivity |
| "Bucket not found" | Verify `R2_BUCKET` matches the bucket name in Cloudflare dashboard |
| "Access denied" | Verify API token has Object Read & Write permissions for the bucket |
| "Redirect URL returns 403" | Enable public access on the bucket (custom domain or r2.dev) |
| GeoJSON endpoint not redirecting | Check `R2_ENABLED=true`, publish datasets, wait up to 5 minutes for manifest cache refresh |
