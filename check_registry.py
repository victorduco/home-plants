#!/usr/bin/env python3
import json

with open("/config/.storage/core.entity_registry", "r") as f:
    registry = json.load(f)

text_entities = [e for e in registry['data']['entities']
                 if e.get('platform') == 'plants' and e.get('entity_id', '').startswith('text.')]

print(f'Text entities in registry: {len(text_entities)}')
for e in text_entities[:5]:
    print(f"  entity_id: {e.get('entity_id')}")
    print(f"  unique_id: {e.get('unique_id')}")
    print()
