#!/usr/bin/env python3
"""Remove old plant text entities from entity registry."""
import json

REGISTRY_PATH = "/config/.storage/core.entity_registry"

def main():
    with open(REGISTRY_PATH, "r") as f:
        registry = json.load(f)

    original_count = len(registry["data"]["entities"])

    # Remove all text entities from plants platform
    registry["data"]["entities"] = [
        entity for entity in registry["data"]["entities"]
        if not (
            entity.get("platform") == "plants" and
            entity.get("entity_id", "").startswith("text.")
        )
    ]

    removed = original_count - len(registry["data"]["entities"])

    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)

    print(f"Removed {removed} text entities from plants platform")

if __name__ == "__main__":
    main()
