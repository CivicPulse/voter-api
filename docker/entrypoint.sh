#!/usr/bin/env bash
set -euo pipefail

# Wait for the database to accept connections (retries handle DNS/startup races)
echo "==> Running Alembic migrations..."
migration_ok=false
for i in $(seq 1 10); do
    if alembic upgrade head; then
        migration_ok=true
        break
    fi
    echo "    Attempt $i failed, retrying in 2s..."
    sleep 2
done

if [ "$migration_ok" = false ]; then
    echo "FATAL: Alembic migrations failed after 10 attempts"
    exit 1
fi

echo "==> Seeding dev data..."
voter-api db seed-dev

echo "==> Starting uvicorn..."
exec uvicorn voter_api.main:create_app --factory --host 0.0.0.0 --port 8000 "$@"
