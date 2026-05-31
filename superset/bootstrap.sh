#!/bin/bash
set -e

echo "Initializing Superset metastore..."
superset db upgrade

ADMIN_USER="${SUPERSET_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${SUPERSET_ADMIN_PASSWORD:-admin}"
ADMIN_EMAIL="${SUPERSET_ADMIN_EMAIL:-admin@local}"

if superset fab list-users 2>/dev/null | grep -q "${ADMIN_USER}"; then
  echo "Admin user '${ADMIN_USER}' already exists."
else
  echo "Creating admin user '${ADMIN_USER}'..."
  superset fab create-admin \
    --username "${ADMIN_USER}" \
    --firstname Admin \
    --lastname User \
    --email "${ADMIN_EMAIL}" \
    --password "${ADMIN_PASSWORD}"
fi

superset init

echo "Starting Superset on http://localhost:8088"
exec superset run -h 0.0.0.0 -p 8088 --with-threads
