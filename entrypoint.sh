#!/bin/sh
set -e

echo "[entrypoint] Waiting for PostgreSQL at $DB_HOST:$DB_PORT ..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -q; do
  sleep 1
done
echo "[entrypoint] PostgreSQL is ready."

echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Starting: $@"
exec "$@"
