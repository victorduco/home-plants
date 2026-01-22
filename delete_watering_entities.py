#!/usr/bin/env python3
"""Delete manual and automatic watering entities from Plants integration."""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

if not HA_URL or not HA_TOKEN:
    print("Error: HA_URL and HA_TOKEN must be set in .env file")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}


def get_states():
    """Get all current states."""
    url = f"{HA_URL}/api/states"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def delete_entity(entity_id):
    """Delete an entity from the entity registry."""
    # First, get the entity registry entry to get the entity_id in registry format
    url = f"{HA_URL}/api/config/entity_registry/{entity_id}"
    
    try:
        response = requests.delete(url, headers=HEADERS)
        if response.status_code == 200:
            print(f"✓ Deleted: {entity_id}")
            return True
        elif response.status_code == 404:
            print(f"✗ Not found in registry: {entity_id}")
            return False
        else:
            print(f"✗ Failed to delete {entity_id}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error deleting {entity_id}: {e}")
        return False


def main():
    print("=" * 80)
    print("DELETING WATERING ENTITIES FROM PLANTS INTEGRATION")
    print("=" * 80)
    print()
    
    # Get all states
    print("Fetching all entities...")
    states = get_states()
    
    # Find watering-related entities
    watering_entities = []
    
    for state in states:
        entity_id = state["entity_id"]
        
        # Check for manual watering events
        if "manual_watering" in entity_id and entity_id.startswith("event."):
            watering_entities.append(entity_id)
        
        # Check for manual watering buttons
        elif "manual_watering" in entity_id and entity_id.startswith("button."):
            watering_entities.append(entity_id)
        
        # Check for auto watering valves
        elif "auto_watering" in entity_id and entity_id.startswith("valve."):
            watering_entities.append(entity_id)
    
    print(f"\nFound {len(watering_entities)} watering entities to delete:")
    for entity_id in watering_entities:
        print(f"  - {entity_id}")
    
    if not watering_entities:
        print("\nNo watering entities found. Nothing to delete.")
        return
    
    print("\n" + "=" * 80)
    print("DELETING ENTITIES")
    print("=" * 80)
    print()
    
    deleted_count = 0
    failed_count = 0
    
    for entity_id in watering_entities:
        if delete_entity(entity_id):
            deleted_count += 1
        else:
            failed_count += 1
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total entities: {len(watering_entities)}")
    print(f"Successfully deleted: {deleted_count}")
    print(f"Failed to delete: {failed_count}")
    print()
    
    if deleted_count > 0:
        print("Note: You may need to restart Home Assistant for changes to take full effect.")
        print("Run: curl -X POST \"$HA_URL/api/services/homeassistant/restart\" \\")
        print("       -H \"Authorization: Bearer $HA_TOKEN\" \\")
        print("       -H \"Content-Type: application/json\" -d '{}'")


if __name__ == "__main__":
    main()
