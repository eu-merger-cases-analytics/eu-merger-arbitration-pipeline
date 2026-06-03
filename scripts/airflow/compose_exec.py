#!/usr/bin/env python3
"""Run commands in pipeline containers from Airflow (via docker exec)."""

from __future__ import annotations

import os
import subprocess
import sys

# Must match container_name in compose.yml
SERVICE_CONTAINERS = {
    "python": "eu-merger-arbitration-python",
    "db": "eu-merger-arbitration-db",
    "dbt": "eu-merger-arbitration-dbt",
}


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: compose_exec.py <service> <command...>", file=sys.stderr)
        raise SystemExit(1)

    service = sys.argv[1]
    command = sys.argv[2:]

    try:
        container = SERVICE_CONTAINERS[service]
    except KeyError:
        print(f"Unknown service {service!r}. Known: {list(SERVICE_CONTAINERS)}", file=sys.stderr)
        raise SystemExit(1)

    docker_cmd = ["docker", "exec"]
    test_limit = os.environ.get("TEST_LIMIT")
    if test_limit:
        docker_cmd.extend(["-e", f"TEST_LIMIT={test_limit}"])
    docker_cmd.extend(["-i", container])
    docker_cmd.extend(command)

    subprocess.run(docker_cmd, check=True)


if __name__ == "__main__":
    main()
