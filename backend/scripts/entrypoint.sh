#!/bin/sh
# Apply database migrations (idempotent) before starting the API.
set -e
echo "Applying database migrations..."
alembic upgrade head
exec "$@"
