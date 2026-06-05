"""
Imports the newest dashboard export ZIP from docs/dashboard/ into Superset.

Uses the Superset REST API (same bundle as Settings → Import dashboards).
Reads credentials from environment (.env via docker compose).

Prerequisites:
  - Superset running (http://localhost:8088)
  - dbt mart built (marts.mart_arbitration_decisions)

Run:
    docker compose up -d superset
    docker compose exec python python superset/import_dashboard.py

From host (Superset on localhost):
    SUPERSET_URL=http://localhost:8088 python scripts/superset/import_dashboard.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import zipfile
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DASHBOARD_DIR = REPO_ROOT / "docs" / "dashboard"
DOCKER_DASHBOARD_DIR = Path("/docs/dashboard")

SUPERSET_URL = os.environ.get("SUPERSET_URL", "http://superset:8088").rstrip("/")
SUPERSET_USER = os.environ.get("SUPERSET_ADMIN_USER", "admin")
SUPERSET_PASSWORD = os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "user")

HEALTH_TIMEOUT_SEC = 180
HEALTH_POLL_SEC = 5


def resolve_dashboard_dir() -> Path:
    if DOCKER_DASHBOARD_DIR.is_dir():
        return DOCKER_DASHBOARD_DIR
    return DEFAULT_DASHBOARD_DIR


def find_newest_zip(dashboard_dir: Path) -> Path:
    zips = sorted(dashboard_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not zips:
        raise FileNotFoundError(f"No .zip files in {dashboard_dir}")
    return zips[0]


def database_password_keys(zip_path: Path) -> dict[str, str]:
    """Map databases/*.yaml paths inside the bundle to POSTGRES_PASSWORD."""
    keys: list[str] = []
    with zipfile.ZipFile(zip_path) as bundle:
        for name in bundle.namelist():
            normalized = name.replace("\\", "/")
            if "/databases/" in normalized and normalized.endswith(".yaml"):
                keys.append(f"databases/{Path(normalized).name}")
    if not keys:
        raise ValueError(f"No databases/*.yaml entries found in {zip_path.name}")
    return dict.fromkeys(keys, POSTGRES_PASSWORD)


def wait_for_superset(session: requests.Session) -> None:
    deadline = time.time() + HEALTH_TIMEOUT_SEC
    health_url = f"{SUPERSET_URL}/health"
    while time.time() < deadline:
        try:
            resp = session.get(health_url, timeout=10)
            if resp.ok:
                log.info("Superset is ready at %s", SUPERSET_URL)
                return
        except requests.RequestException:
            pass
        log.info("Waiting for Superset (%s)...", health_url)
        time.sleep(HEALTH_POLL_SEC)
    raise TimeoutError(f"Superset did not become ready within {HEALTH_TIMEOUT_SEC}s")


def login(session: requests.Session) -> str:
    resp = session.post(
        f"{SUPERSET_URL}/api/v1/security/login",
        json={
            "username": SUPERSET_USER,
            "password": SUPERSET_PASSWORD,
            "provider": "db",
            "refresh": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("Login succeeded but no access_token in response")
    log.info("Logged in as %s", SUPERSET_USER)
    return token


def auth_headers(session: requests.Session, token: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", "Referer": SUPERSET_URL}
    csrf_resp = session.get(
        f"{SUPERSET_URL}/api/v1/security/csrf_token/",
        headers=headers,
        timeout=30,
    )
    if csrf_resp.ok:
        headers["X-CSRFToken"] = csrf_resp.json().get("result", "")
    return headers


def import_dashboard(session: requests.Session, headers: dict[str, str], zip_path: Path) -> None:
    passwords = database_password_keys(zip_path)
    form = {
        "passwords": json.dumps(passwords),
        "overwrite": "true",
    }
    import_url = f"{SUPERSET_URL}/api/v1/dashboard/import/"

    with zip_path.open("rb") as handle:
        for field_name in ("formData", "bundle"):
            handle.seek(0)
            files = {field_name: (zip_path.name, handle, "application/zip")}
            resp = session.post(import_url, headers=headers, data=form, files=files, timeout=120)
            if resp.ok:
                log.info("Dashboard import succeeded (%s)", zip_path.name)
                return
            if resp.status_code not in (400, 422):
                resp.raise_for_status()

    raise RuntimeError(
        f"Dashboard import failed for {zip_path.name}: {resp.status_code} {resp.text[:500]}"
    )


def main() -> int:
    dashboard_dir = resolve_dashboard_dir()
    zip_path = find_newest_zip(dashboard_dir)
    log.info("Importing %s into %s", zip_path, SUPERSET_URL)

    session = requests.Session()
    try:
        wait_for_superset(session)
        token = login(session)
        headers = auth_headers(session, token)
        import_dashboard(session, headers, zip_path)
    except (requests.RequestException, TimeoutError, OSError, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        return 1

    log.info("Open %s and check Dashboards (login: %s)", SUPERSET_URL, SUPERSET_USER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
