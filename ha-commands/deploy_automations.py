#!/usr/bin/env python3
"""Deploy automations from ha/automations/*.yaml to Home Assistant via REST API.

Each YAML file must be a list with one automation dict containing an `id` field.
The script upserts each automation: creates if missing, updates if exists.
"""

import os
import sys
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
load_dotenv(REPO_ROOT / ".env")

HA_URL = os.environ["HA_URL"].rstrip("/")
HA_TOKEN = os.environ["HA_TOKEN"]
HEADERS = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
AUTOMATIONS_DIR = REPO_ROOT / "ha" / "automations"


def upsert(client: httpx.Client, automation: dict) -> None:
    """Write one automation.

    Home Assistant's config API is per-id only: there is no collection endpoint to list
    or create against, and posting to one answers 404. The id-scoped POST both creates
    and updates, so existence is only checked to label the output.
    """
    aid = automation["id"]
    existed = (
        client.get(
            f"{HA_URL}/api/config/automation/config/{aid}", headers=HEADERS
        ).status_code
        == 200
    )
    resp = client.post(
        f"{HA_URL}/api/config/automation/config/{aid}",
        headers=HEADERS,
        json=automation,
    )
    resp.raise_for_status()
    print(f"  {'updated' if existed else 'created'}: {aid}")


def main() -> None:
    yaml_files = sorted(AUTOMATIONS_DIR.glob("*.yaml"))
    if not yaml_files:
        print("No automation files found.")
        return

    # Generous timeouts: deploy.sh runs this straight after an HA restart, and this
    # instance takes minutes to settle — its API answers slowly long after it is up.
    with httpx.Client(timeout=120) as client:
        for path in yaml_files:
            automations = yaml.safe_load(path.read_text())
            if not isinstance(automations, list):
                automations = [automations]
            for automation in automations:
                if "id" not in automation:
                    print(f"  skipped (no id): {path.name}")
                    continue
                upsert(client, automation)

    # Reload automations
    resp = httpx.post(
        f"{HA_URL}/api/services/automation/reload",
        headers=HEADERS,
        timeout=120,
    )
    resp.raise_for_status()
    print("→ Automations reloaded")


if __name__ == "__main__":
    main()
