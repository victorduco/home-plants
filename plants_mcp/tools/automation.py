"""Automation tools."""

from __future__ import annotations

import json
import os
from typing import Any

import websockets
from fastmcp import FastMCP

from .common import (
    collect_entity_ids,
    get_states_list,
    ha_request,
    new_automation_id,
    parse_plants_from_states,
)


async def _get_entity_labels() -> dict[str, list[str]]:
    """Return entity_id -> labels via WebSocket entity registry."""
    token = os.getenv("HA_TOKEN", "")
    ha_url = os.getenv("HA_URL", "http://192.168.1.151:8123").rstrip("/")
    ws_url = ha_url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
    try:
        async with websockets.connect(ws_url) as ws:
            await ws.recv()
            await ws.send(json.dumps({"type": "auth", "access_token": token}))
            await ws.recv()
            await ws.send(json.dumps({"id": 1, "type": "config/entity_registry/list"}))
            resp = json.loads(await ws.recv())
            result: dict[str, list[str]] = {}
            for entry in resp.get("result") or []:
                eid = entry.get("entity_id")
                labels = entry.get("labels") or []
                if eid and labels:
                    result[eid] = labels
            return result
    except Exception:
        return {}


def register_automation_tools(mcp: FastMCP) -> None:
    """Register automation tools."""

    @mcp.tool
    async def automation___list() -> dict[str, Any]:
        """Return all plant automations (label: plants) with state and last triggered."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}

        entity_labels = await _get_entity_labels()

        automations: list[dict[str, Any]] = []
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id.startswith("automation."):
                continue
            labels = entity_labels.get(entity_id, [])
            if "plants" not in labels:
                continue
            attrs = state.get("attributes", {})
            automations.append({
                "id": attrs.get("id"),
                "entity_id": entity_id,
                "alias": attrs.get("friendly_name", entity_id),
                "enabled": state.get("state") == "on",
                "last_triggered": attrs.get("last_triggered"),
            })

        automations.sort(key=lambda x: x.get("alias") or "")
        return {"status": "success", "automations": automations}

    @mcp.tool
    async def automation___get_all_by_device() -> dict[str, Any]:
        """Return configured outlet entities and matching automations."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = parse_plants_from_states(states)
        outlet_entities: set[str] = set()
        for plant in plants.values():
            for key in ("light_outlet", "water_outlet", "humidifier_source"):
                value = plant.get(key)
                if value and value != "None":
                    outlet_entities.add(value)
        outlets = sorted(outlet_entities)
        if not outlets:
            return {"status": "success", "outlets": [], "automations": []}

        matched = []
        automation_states = [
            state
            for state in states
            if state.get("entity_id", "").startswith("automation.")
        ]
        for state in automation_states:
            attributes = state.get("attributes", {})
            automation_id = attributes.get("id")
            if not automation_id:
                continue
            _, config, error = await ha_request(
                "GET",
                f"/api/config/automation/config/{automation_id}",
            )
            if error or not isinstance(config, dict):
                continue
            entity_ids = collect_entity_ids(config)
            relevant = sorted(entity_ids.intersection(outlet_entities))
            if not relevant:
                continue
            matched.append(
                {
                    "id": automation_id,
                    "alias": attributes.get("friendly_name"),
                    "enabled": state.get("state") == "on",
                    "matched_entities": relevant,
                }
            )
        matched.sort(key=lambda item: item.get("alias") or "")
        return {
            "status": "success",
            "outlets": outlets,
            "automations": matched,
        }

    @mcp.tool
    async def automation___add_automation(
        payload: dict[str, Any],
        automation_id: str = "",
    ) -> dict[str, Any]:
        """Create a new automation (payload matches HA automation config schema)."""
        if not isinstance(payload, dict) or not payload:
            return {"status": "error", "error": "Payload must be a non-empty object"}
        automation_id = new_automation_id(automation_id)
        _, result, error = await ha_request(
            "POST",
            f"/api/config/automation/config/{automation_id}",
            json=payload,
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "id": automation_id, "automation": result}

    @mcp.tool
    async def automation___remove_automation(automation_id: str) -> dict[str, Any]:
        """Delete an automation by id."""
        automation_id = automation_id.strip()
        if not automation_id:
            return {"status": "error", "error": "automation_id is required"}
        _, _, error = await ha_request(
            "DELETE",
            f"/api/config/automation/config/{automation_id}",
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "deleted": automation_id}

    @mcp.tool
    async def automation___set_automation_fields(
        automation_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an automation by id (payload matches HA automation config schema)."""
        automation_id = automation_id.strip()
        if not automation_id:
            return {"status": "error", "error": "automation_id is required"}
        if not isinstance(payload, dict) or not payload:
            return {"status": "error", "error": "Payload must be a non-empty object"}
        _, result, error = await ha_request(
            "POST",
            f"/api/config/automation/config/{automation_id}",
            json=payload,
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "automation": result}
