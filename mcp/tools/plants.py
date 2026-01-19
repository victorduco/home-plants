"""Home Assistant Plants tools."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Iterable

import httpx
from fastmcp import FastMCP


def _get_ha_config() -> tuple[str, str] | None:
    ha_token = os.getenv("HA_TOKEN", "")
    ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123").rstrip("/")
    if not ha_token:
        return None
    return ha_url, ha_token


async def _ha_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> tuple[int, Any | None, str | None]:
    config = _get_ha_config()
    if not config:
        return 0, None, "HA_TOKEN is not set"
    ha_url, ha_token = config
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }
    url = f"{ha_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
            )
    except httpx.HTTPError as exc:
        return 0, None, f"Home Assistant request failed: {exc}"
    if response.status_code >= 400:
        return response.status_code, None, response.text
    if not response.content:
        return response.status_code, None, None
    try:
        return response.status_code, response.json(), None
    except ValueError:
        return (
            response.status_code,
            None,
            f"Unexpected non-JSON response: {response.text}",
        )


async def _get_config_entries(domain: str) -> tuple[list[dict[str, Any]], str | None]:
    _, data, error = await _ha_request("GET", "/api/config/config_entries/entry")
    if error:
        return [], error
    if not isinstance(data, list):
        return [], "Unexpected config entries response"
    return [entry for entry in data if entry.get("domain") == domain], None


async def _get_states_list() -> tuple[list[dict[str, Any]], str | None]:
    _, data, error = await _ha_request("GET", "/api/states")
    if error:
        return [], error
    if not isinstance(data, list):
        return [], "Unexpected states response"
    return data, None


def _match_entry(entries: list[dict[str, Any]], identifier: str) -> dict[str, Any] | None:
    identifier = identifier.strip()
    if not identifier:
        return None
    for entry in entries:
        if entry.get("entry_id") == identifier:
            return entry
    lowered = identifier.lower()
    for entry in entries:
        if str(entry.get("title", "")).lower() == lowered:
            return entry
    return None


def _plant_friendly_names(title: str) -> dict[str, str]:
    return {
        "status": f"{title} Status",
        "soil_moisture": f"{title} Soil Moisture",
        "location_x": f"{title} Location X",
        "location_y": f"{title} Location Y",
        "last_watered": f"{title} Last Watered",
    }


def _find_entity_ids(title: str, states: Iterable[dict[str, Any]]) -> dict[str, str]:
    names = _plant_friendly_names(title)
    matched: dict[str, str] = {}
    for state in states:
        friendly = state.get("attributes", {}).get("friendly_name", "")
        for key, name in names.items():
            if friendly == name:
                entity_id = state.get("entity_id")
                if entity_id:
                    matched[key] = entity_id
    return matched


def _parse_plant_states(
    entry: dict[str, Any],
    states: list[dict[str, Any]],
) -> dict[str, Any]:
    entry_id = entry.get("entry_id")
    title = entry.get("title")
    info: dict[str, Any] = {
        "entry_id": entry_id,
        "name": title,
        "entities": [],
    }
    if not title:
        return info
    names = _plant_friendly_names(title)
    for state in states:
        entity_id = state.get("entity_id")
        if not entity_id:
            continue
        attributes = state.get("attributes", {})
        friendly = attributes.get("friendly_name", "")
        if friendly not in names.values():
            continue
        info["entities"].append(
            {
                "entity_id": entity_id,
                "state": state.get("state"),
                "attributes": attributes,
            }
        )
        if friendly == names["last_watered"]:
            info["last_watered"] = state.get("state")
        elif friendly == names["soil_moisture"]:
            info["soil_moisture"] = state.get("state")
        elif friendly == names["location_x"]:
            info["location_x"] = state.get("state")
        elif friendly == names["location_y"]:
            info["location_y"] = state.get("state")
        elif friendly == names["status"]:
            info["status"] = state.get("state")
    return info


def register_plants_tools(mcp: FastMCP) -> None:
    """Register tools for managing plants."""

    @mcp.tool
    async def get_plants_status() -> dict[str, Any]:
        """Return full info for all plants (empty if none)."""
        entries, error = await _get_config_entries("plants")
        if error:
            return {"status": "error", "error": error}
        if not entries:
            return {"status": "success", "plants": []}
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = [_parse_plant_states(entry, states) for entry in entries]
        return {"status": "success", "plants": plants}

    @mcp.tool
    async def water_plant(identifier: str) -> dict[str, Any]:
        """Set last watered to now and soil moisture to 100%."""
        entries, error = await _get_config_entries("plants")
        if error:
            return {"status": "error", "error": error}
        entry = _match_entry(entries, identifier)
        if not entry:
            return {"status": "error", "error": "Plant not found"}
        title = entry.get("title", "")
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        entity_ids = _find_entity_ids(title, states)
        moisture_id = entity_ids.get("soil_moisture")
        watered_id = entity_ids.get("last_watered")
        now = datetime.now(timezone.utc).isoformat()
        results = {}
        if watered_id:
            _, _, error = await _ha_request(
                "POST",
                "/api/services/datetime/set_value",
                json={"entity_id": watered_id, "value": now},
            )
            results["last_watered"] = "ok" if not error else error
        else:
            results["last_watered"] = "missing"
        if moisture_id:
            _, _, error = await _ha_request(
                "POST",
                "/api/services/number/set_value",
                json={"entity_id": moisture_id, "value": 100},
            )
            results["soil_moisture"] = "ok" if not error else error
        else:
            results["soil_moisture"] = "missing"
        return {"status": "success", "plant": entry.get("title"), "results": results}

    @mcp.tool
    async def add_plant(name: str) -> dict[str, Any]:
        """Create a new plant entry via config flow."""
        if not name.strip():
            return {"status": "error", "error": "Name is required"}
        _, start, error = await _ha_request(
            "POST",
            "/api/config/config_entries/flow",
            json={"handler": "plants"},
        )
        if error or not isinstance(start, dict):
            return {"status": "error", "error": error or "Failed to start flow"}
        flow_id = start.get("flow_id")
        if not flow_id:
            return {"status": "error", "error": "Missing flow_id"}
        _, finish, error = await _ha_request(
            "POST",
            f"/api/config/config_entries/flow/{flow_id}",
            json={"name": name.strip()},
        )
        if error or not isinstance(finish, dict):
            return {"status": "error", "error": error or "Failed to finish flow"}
        return {"status": "success", "entry": finish.get("result")}

    @mcp.tool
    async def delete_plant(identifier: str) -> dict[str, Any]:
        """Delete a plant entry."""
        entries, error = await _get_config_entries("plants")
        if error:
            return {"status": "error", "error": error}
        entry = _match_entry(entries, identifier)
        if not entry:
            return {"status": "error", "error": "Plant not found"}
        entry_id = entry.get("entry_id")
        _, _, error = await _ha_request(
            "DELETE",
            f"/api/config/config_entries/entry/{entry_id}",
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "deleted": entry.get("title")}

    @mcp.tool
    async def edit_plant(
        identifier: str,
        new_name: str = "",
        location_x: float | None = None,
        location_y: float | None = None,
    ) -> dict[str, Any]:
        """Edit plant name or location coordinates."""
        entries, error = await _get_config_entries("plants")
        if error:
            return {"status": "error", "error": error}
        entry = _match_entry(entries, identifier)
        if not entry:
            return {"status": "error", "error": "Plant not found"}
        entry_id = entry.get("entry_id")
        results: dict[str, Any] = {}
        if new_name.strip():
            _, _, error = await _ha_request(
                "PATCH",
                f"/api/config/config_entries/entry/{entry_id}",
                json={"title": new_name.strip()},
            )
            results["name"] = "ok" if not error else error
        if location_x is not None or location_y is not None:
            title = entry.get("title", "")
            states, error = await _get_states_list()
            if error:
                return {"status": "error", "error": error}
            entity_ids = _find_entity_ids(title, states)
            if location_x is not None:
                target = entity_ids.get("location_x")
                if target:
                    _, _, error = await _ha_request(
                        "POST",
                        "/api/services/number/set_value",
                        json={"entity_id": target, "value": location_x},
                    )
                    results["location_x"] = "ok" if not error else error
                else:
                    results["location_x"] = "missing"
            if location_y is not None:
                target = entity_ids.get("location_y")
                if target:
                    _, _, error = await _ha_request(
                        "POST",
                        "/api/services/number/set_value",
                        json={"entity_id": target, "value": location_y},
                    )
                    results["location_y"] = "ok" if not error else error
                else:
                    results["location_y"] = "missing"
        return {"status": "success", "plant": entry.get("title"), "results": results}
