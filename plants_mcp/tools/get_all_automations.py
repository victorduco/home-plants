"""Tool: get_all_automations."""

from __future__ import annotations

import json
import os
from typing import Any

import websockets
from fastmcp import FastMCP

from .common import get_states_list


async def _get_entity_labels() -> dict[str, list[str]]:
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


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_all_automations() -> dict[str, Any]:
        """Return all plant automations (label: plants) with enabled state and last triggered time."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}

        entity_labels = await _get_entity_labels()

        automations: list[dict[str, Any]] = []
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id.startswith("automation."):
                continue
            if "plants" not in entity_labels.get(entity_id, []):
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
