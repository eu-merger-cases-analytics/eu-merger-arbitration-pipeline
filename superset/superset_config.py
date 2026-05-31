"""Minimal Superset config for local Docker testing."""

import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "dev-only-change-me")

# SQLite metastore — no separate Postgres DB needed for Superset itself.
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SUPERSET__SQLALCHEMY_DATABASE_URI",
    "sqlite:////app/superset_home/superset.db",
)

WTF_CSRF_ENABLED = True
