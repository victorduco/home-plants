---
description: Manage home plants via Home Assistant integration and MCP server
---

# Home Plants Skill

This skill helps manage the home plants system built on Home Assistant.

## Architecture

- **HA Integration** (`ha/custom_components/plants/`) — custom component running inside Home Assistant
- **MCP Server** (`plants_mcp/`) — FastMCP server exposing plant data as tools/resources
- **Deploy** — `make deploy-integration` rsync + HA restart via API

## Key Files

- `ha/custom_components/plants/__init__.py` — entry setup, config entries per device type
- `ha/custom_components/plants/data.py` — storage models (PlantsData, GrowLightsData, etc.)
- `ha/custom_components/plants/select.py` — Select entities including 20 plant slots per device
- `ha/custom_components/plants/sensor.py` — Sensor entities (state mirrors)
- `ha/custom_components/plants/text.py` — Text entities (recommendations, location notes)
- `main.py` — MCP server entrypoint

## Device Types (Config Entry types)

- `plants` — individual plants with moisture/humidity/temperature sensors
- `grow_lights` — grow lights with 20 plant slots (select entities)
- `humidifiers` — humidifiers with 20 plant slots
- `auto_waterers` — auto waterers with 20 plant slots
- `meter_locations` — air sensor locations

## HA Server

- Host: `192.168.1.151:8123`
- SSH: `hassio@192.168.1.151` port 22, key `~/.ssh/id_ed25519`
- Config: `/config/`, storage: `/config/.storage/`

## Common Tasks

**Deploy integration:**
```sh
make deploy-integration
```

**Check entity states:**
```sh
source .env && curl -s "$HA_URL/api/states" -H "Authorization: Bearer $HA_TOKEN" | python3 -c "import json,sys; [print(s['entity_id'], s['state']) for s in json.load(sys.stdin) if 'plant' in s['entity_id']]"
```

**Remove entity from registry (WebSocket):**
```python
import asyncio, json, websockets
async def remove(entity_id):
    async with websockets.connect("ws://192.168.1.151:8123/api/websocket") as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        await ws.recv()
        await ws.send(json.dumps({"id": 1, "type": "config/entity_registry/remove", "entity_id": entity_id}))
        print(json.loads(await ws.recv()))
```

## Gotchas

- HA TextEntity hard-limits state to 255 chars regardless of `_attr_native_max` — use Select entities for lists
- Editing `core.entity_registry` while HA runs causes `KeyError: 'capabilities'` crash on next boot — always restore the field
- `sensor.*` and `text.*` entities with the same `unique_id` conflict — only one gets registered
- Plant slot selects store plant names in state, plant UUIDs in storage (`nearby_plant_ids`)
