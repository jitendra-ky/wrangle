#!/bin/sh
set -e

echo "[entrypoint] Waiting for PostgreSQL at $DB_HOST:$DB_PORT ..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -q; do
  sleep 1
done
echo "[entrypoint] PostgreSQL is ready."

# Only the api service runs migrations (SKIP_MIGRATE=1 on the worker)
# to avoid a race condition when both containers start simultaneously.
if [ "${SKIP_MIGRATE}" != "1" ]; then
  echo "[entrypoint] Running migrations..."
  python manage.py migrate --noinput
else
  echo "[entrypoint] Skipping migrations (SKIP_MIGRATE=1)."
fi

echo "[entrypoint] Starting: $@"
exec "$@"
