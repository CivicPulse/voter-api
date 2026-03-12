#!/usr/bin/env bash
set -euo pipefail

# Wait for the database to accept connections (retries handle DNS/startup races)
echo "==> Running Alembic migrations..."
for i in $(seq 1 10); do
    alembic upgrade head && break
    echo "    Attempt $i failed, retrying in 2s..."
    sleep 2
done

echo "==> Seeding dev data..."
voter-api db seed-dev

echo "==> Starting uvicorn..."
exec uvicorn voter_api.main:create_app --factory --host 0.0.0.0 --port 8000 "$@"
