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


def get_existing_ids(client: httpx.Client) -> set[str]:
    resp = client.get(f"{HA_URL}/api/config/automation/config", headers=HEADERS)
    if resp.status_code == 404:
        return set()
    resp.raise_for_status()
    return {a["id"] for a in resp.json() if "id" in a}


def upsert(client: httpx.Client, automation: dict, existing_ids: set[str]) -> None:
    aid = automation["id"]
    if aid in existing_ids:
        resp = client.put(
            f"{HA_URL}/api/config/automation/config/{aid}",
            headers=HEADERS,
            json=automation,
        )
    else:
        resp = client.post(
            f"{HA_URL}/api/config/automation/config",
            headers=HEADERS,
            json=automation,
        )
    resp.raise_for_status()
    print(f"  {'updated' if aid in existing_ids else 'created'}: {aid}")


def main() -> None:
    yaml_files = sorted(AUTOMATIONS_DIR.glob("*.yaml"))
    if not yaml_files:
        print("No automation files found.")
        return

    with httpx.Client(timeout=15) as client:
        existing_ids = get_existing_ids(client)
        for path in yaml_files:
            automations = yaml.safe_load(path.read_text())
            if not isinstance(automations, list):
                automations = [automations]
            for automation in automations:
                if "id" not in automation:
                    print(f"  skipped (no id): {path.name}")
                    continue
                upsert(client, automation, existing_ids)

    # Reload automations
    resp = httpx.post(
        f"{HA_URL}/api/services/automation/reload",
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    print("→ Automations reloaded")


if __name__ == "__main__":
    main()
