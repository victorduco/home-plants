#!/usr/bin/env python3
"""Find manual and automatic watering records in Plants integration."""

import os
import sys
from datetime import datetime, timedelta
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


def get_history(entity_id, start_time=None):
    """Get history for a specific entity."""
    if start_time is None:
        start_time = datetime.now() - timedelta(days=30)
    
    timestamp = start_time.isoformat()
    url = f"{HA_URL}/api/history/period/{timestamp}"
    params = {"filter_entity_id": entity_id}
    
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def get_logbook(start_time=None, end_time=None, entity=None):
    """Get logbook entries."""
    if start_time is None:
        start_time = datetime.now() - timedelta(days=30)
    
    timestamp = start_time.isoformat()
    url = f"{HA_URL}/api/logbook/{timestamp}"
    
    params = {}
    if entity:
        params["entity"] = entity
    if end_time:
        params["end_time"] = end_time.isoformat()
    
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def main():
    print("=" * 80)
    print("SEARCHING FOR WATERING RECORDS IN PLANTS INTEGRATION")
    print("=" * 80)
    print()
    
    # Get all states
    print("Fetching all entities...")
    states = get_states()
    
    # Find Plants integration entities
    plants_entities = {
        "manual_watering_events": [],
        "manual_watering_buttons": [],
        "auto_watering_valves": [],
        "plants": set(),
    }
    
    for state in states:
        entity_id = state["entity_id"]
        
        # Check if it's a plants integration entity
        if "plant_" in entity_id or entity_id.startswith("event.") or entity_id.startswith("button.") or entity_id.startswith("valve."):
            attributes = state.get("attributes", {})
            
            # Manual watering events
            if "manual_watering" in entity_id and entity_id.startswith("event."):
                plants_entities["manual_watering_events"].append(entity_id)
                plant_name = attributes.get("friendly_name", "Unknown")
                plants_entities["plants"].add(plant_name.replace(" Manual Watering", ""))
                
            # Manual watering buttons
            elif "manual_watering" in entity_id and entity_id.startswith("button."):
                plants_entities["manual_watering_buttons"].append(entity_id)
                plant_name = attributes.get("friendly_name", "Unknown")
                plants_entities["plants"].add(plant_name.replace(" Add Manual Watering", ""))
                
            # Auto watering valves
            elif "auto_watering" in entity_id and entity_id.startswith("valve."):
                plants_entities["auto_watering_valves"].append(entity_id)
                plant_name = attributes.get("friendly_name", "Unknown")
                plants_entities["plants"].add(plant_name.replace(" Auto Watering Control", ""))
    
    print(f"\nFound {len(plants_entities['plants'])} plants in the system")
    print(f"Manual watering events: {len(plants_entities['manual_watering_events'])}")
    print(f"Manual watering buttons: {len(plants_entities['manual_watering_buttons'])}")
    print(f"Auto watering valves: {len(plants_entities['auto_watering_valves'])}")
    print()
    
    # Display current states
    print("=" * 80)
    print("CURRENT STATES")
    print("=" * 80)
    print()
    
    # Manual watering events
    if plants_entities["manual_watering_events"]:
        print("\n--- Manual Watering Events ---")
        for entity_id in plants_entities["manual_watering_events"]:
            for state in states:
                if state["entity_id"] == entity_id:
                    print(f"\n{entity_id}")
                    print(f"  Friendly name: {state['attributes'].get('friendly_name')}")
                    print(f"  State: {state['state']}")
                    print(f"  Last changed: {state.get('last_changed')}")
                    print(f"  Last updated: {state.get('last_updated')}")
                    event_data = state['attributes'].get('event_data')
                    if event_data:
                        print(f"  Event data: {event_data}")
                    break
    
    # Auto watering valves
    if plants_entities["auto_watering_valves"]:
        print("\n--- Auto Watering Valves ---")
        for entity_id in plants_entities["auto_watering_valves"]:
            for state in states:
                if state["entity_id"] == entity_id:
                    print(f"\n{entity_id}")
                    print(f"  Friendly name: {state['attributes'].get('friendly_name')}")
                    print(f"  State: {state['state']}")
                    print(f"  Last changed: {state.get('last_changed')}")
                    print(f"  Last updated: {state.get('last_updated')}")
                    break
    
    # Get history for the last 30 days
    print("\n" + "=" * 80)
    print("HISTORY (LAST 30 DAYS)")
    print("=" * 80)
    
    # Manual watering events history
    if plants_entities["manual_watering_events"]:
        print("\n--- Manual Watering Events History ---")
        for entity_id in plants_entities["manual_watering_events"]:
            print(f"\nFetching history for {entity_id}...")
            try:
                history = get_history(entity_id)
                if history and len(history) > 0 and len(history[0]) > 0:
                    print(f"  Found {len(history[0])} state changes:")
                    for event in history[0][-10:]:  # Last 10 events
                        print(f"    - {event.get('last_changed')}: {event.get('state')}")
                        if event.get('attributes', {}).get('event_data'):
                            print(f"      Data: {event['attributes']['event_data']}")
                else:
                    print("  No history found")
            except Exception as e:
                print(f"  Error fetching history: {e}")
    
    # Auto watering valves history
    if plants_entities["auto_watering_valves"]:
        print("\n--- Auto Watering Valves History ---")
        for entity_id in plants_entities["auto_watering_valves"]:
            print(f"\nFetching history for {entity_id}...")
            try:
                history = get_history(entity_id)
                if history and len(history) > 0 and len(history[0]) > 0:
                    print(f"  Found {len(history[0])} state changes:")
                    # Count open/close events
                    opens = sum(1 for e in history[0] if e.get('state') in ['open', 'opening', 'on'])
                    closes = sum(1 for e in history[0] if e.get('state') in ['closed', 'closing', 'off'])
                    print(f"    Total open events: {opens}")
                    print(f"    Total close events: {closes}")
                    print(f"  Last 10 state changes:")
                    for event in history[0][-10:]:
                        print(f"    - {event.get('last_changed')}: {event.get('state')}")
                else:
                    print("  No history found")
            except Exception as e:
                print(f"  Error fetching history: {e}")
    
    # Try to get logbook entries
    print("\n" + "=" * 80)
    print("LOGBOOK ENTRIES (LAST 30 DAYS)")
    print("=" * 80)
    print("\nFetching logbook entries...")
    try:
        logbook = get_logbook()
        watering_entries = [
            entry for entry in logbook
            if any(plant_word in str(entry).lower() 
                   for plant_word in ['watering', 'полив', 'valve', 'button'])
        ]
        
        if watering_entries:
            print(f"Found {len(watering_entries)} watering-related logbook entries")
            print("\nLast 20 entries:")
            for entry in watering_entries[-20:]:
                print(f"\n  {entry.get('when')}")
                print(f"    Entity: {entry.get('entity_id')}")
                print(f"    Name: {entry.get('name')}")
                print(f"    Message: {entry.get('message')}")
                if entry.get('state'):
                    print(f"    State: {entry.get('state')}")
        else:
            print("No watering-related logbook entries found")
    except Exception as e:
        print(f"Error fetching logbook: {e}")
    
    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
