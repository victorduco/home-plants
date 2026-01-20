"""Home Assistant Plants tools."""

from __future__ import annotations

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


PLANT_SUFFIXES = {
    "moisture": "Moisture",
    "moisture_source": "Moisture Source",
    "light_outlet": "Light Outlet",
    "water_outlet": "Water Outlet",
    "light_power": "Light Power",
    "water_power": "Water Power",
}


def _match_plant_name(names: Iterable[str], identifier: str) -> str | None:
    candidate = identifier.strip()
    if not candidate:
        return None
    for name in names:
        if name == candidate:
            return name
    lowered = candidate.lower()
    for name in names:
        if name.lower() == lowered:
            return name
    return None


def _sanitize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    if "options" not in attributes:
        return attributes
    cleaned = dict(attributes)
    cleaned.pop("options", None)
    return cleaned


def _parse_plants_from_states(
    states: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    plants: dict[str, dict[str, Any]] = {}
    for state in states:
        entity_id = state.get("entity_id")
        if not entity_id:
            continue
        attributes = state.get("attributes", {})
        friendly = attributes.get("friendly_name", "")
        if not friendly:
            continue
        matched_key = None
        for key, suffix in PLANT_SUFFIXES.items():
            if friendly.endswith(f" {suffix}"):
                matched_key = key
                plant_name = friendly[: -len(suffix) - 1]
                break
        if not matched_key:
            continue
        plant_name = plant_name.strip()
        if not plant_name:
            continue
        plant_info = plants.setdefault(
            plant_name,
            {"name": plant_name, "entities": []},
        )
        plant_info["entities"].append(
            {
                "entity_id": entity_id,
                "state": state.get("state"),
                "attributes": _sanitize_attributes(attributes),
            }
        )
        plant_info[f"{matched_key}_entity_id"] = entity_id
        plant_info[matched_key] = state.get("state")
    return plants


async def _get_plants_entry_id() -> tuple[str | None, str | None]:
    entries, error = await _get_config_entries("plants")
    if error:
        return None, error
    if not entries:
        return None, "Plants config entry not found"
    entry_id = entries[0].get("entry_id")
    if not entry_id:
        return None, "Plants entry_id missing"
    return entry_id, None


async def _run_options_flow(
    entry_id: str,
    next_step_id: str,
    user_input: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    _, start, error = await _ha_request(
        "POST",
        "/api/config/config_entries/options/flow",
        json={"entry_id": entry_id},
    )
    if error or not isinstance(start, dict):
        return None, error or "Failed to start options flow"
    flow_id = start.get("flow_id")
    if not flow_id:
        return None, "Missing flow_id"
    _, _, error = await _ha_request(
        "POST",
        f"/api/config/config_entries/options/flow/{flow_id}",
        json={"next_step_id": next_step_id},
    )
    if error:
        return None, error
    _, finish, error = await _ha_request(
        "POST",
        f"/api/config/config_entries/options/flow/{flow_id}",
        json=user_input,
    )
    if error or not isinstance(finish, dict):
        return None, error or "Failed to finish options flow"
    return finish, None


async def _select_option(entity_id: str, option: str) -> str | None:
    _, _, error = await _ha_request(
        "POST",
        "/api/services/select/select_option",
        json={"entity_id": entity_id, "option": option},
    )
    return error


def register_plants_tools(mcp: FastMCP) -> None:
    """Register tools for managing plants."""

    @mcp.tool
    async def get_plants_status() -> dict[str, Any]:
        """Return full info for all plants (empty if none)."""
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = list(_parse_plants_from_states(states).values())
        plants.sort(key=lambda plant: plant.get("name", ""))
        return {"status": "success", "plants": plants}

    @mcp.tool
    async def water_plant(identifier: str) -> dict[str, Any]:
        """Turn on the watering outlet for a plant."""
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        plant_name = _match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        plant = plants[plant_name]
        switch_entity_id = plant.get("water_power_entity_id")
        if not switch_entity_id:
            return {"status": "error", "error": "Water switch not found"}
        _, _, error = await _ha_request(
            "POST",
            "/api/services/switch/turn_on",
            json={"entity_id": switch_entity_id},
        )
        if error:
            return {"status": "error", "error": error}
        return {
            "status": "success",
            "plant": plant_name,
            "water_switch": switch_entity_id,
        }

    @mcp.tool
    async def add_plant(
        name: str,
        moisture_entity_id: str = "",
    ) -> dict[str, Any]:
        """Create a new plant device via the options flow."""
        if not name.strip():
            return {"status": "error", "error": "Name is required"}
        entry_id, error = await _get_plants_entry_id()
        if error or not entry_id:
            return {"status": "error", "error": error or "Plants entry not found"}
        user_input: dict[str, Any] = {"name": name.strip()}
        if moisture_entity_id.strip():
            user_input["moisture_entity_id"] = moisture_entity_id.strip()
        finish, error = await _run_options_flow(
            entry_id,
            "add_plant",
            user_input,
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "result": finish}

    @mcp.tool
    async def delete_plant(identifier: str) -> dict[str, Any]:
        """Delete a plant device via the options flow."""
        entry_id, error = await _get_plants_entry_id()
        if error:
            return {"status": "error", "error": error}
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        plant_name = _match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        finish, error = await _run_options_flow(
            entry_id,
            "remove_plant",
            {"plant_label": plant_name},
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "deleted": plant_name, "result": finish}

    @mcp.tool
    async def set_plant_moisture_source(
        identifier: str,
        moisture_entity_id: str,
    ) -> dict[str, Any]:
        """Set the moisture source for a plant."""
        entity_id = moisture_entity_id.strip()
        if not entity_id:
            return {"status": "error", "error": "Moisture entity is required"}
        if not entity_id.startswith(("sensor.", "number.", "input_number.")):
            return {
                "status": "error",
                "error": "Moisture entity must be sensor.*, number.*, or input_number.*",
            }
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        plant_name = _match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        select_entity_id = plants[plant_name].get("moisture_source_entity_id")
        if not select_entity_id:
            return {"status": "error", "error": "Moisture select not found"}
        error = await _select_option(select_entity_id, entity_id)
        if error:
            return {"status": "error", "error": error}
        return {
            "status": "success",
            "plant": plant_name,
            "moisture_source": entity_id,
        }

    @mcp.tool
    async def set_plant_light_outlet(
        identifier: str,
        outlet_entity_id: str,
    ) -> dict[str, Any]:
        """Set the light outlet for a plant."""
        entity_id = outlet_entity_id.strip()
        if not entity_id:
            return {"status": "error", "error": "Outlet entity is required"}
        if not entity_id.startswith(("light.", "switch.")):
            return {
                "status": "error",
                "error": "Outlet entity must be light.* or switch.*",
            }
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        plant_name = _match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        select_entity_id = plants[plant_name].get("light_outlet_entity_id")
        if not select_entity_id:
            return {"status": "error", "error": "Light outlet select not found"}
        error = await _select_option(select_entity_id, entity_id)
        if error:
            return {"status": "error", "error": error}
        return {
            "status": "success",
            "plant": plant_name,
            "light_outlet": entity_id,
        }

    @mcp.tool
    async def set_plant_water_outlet(
        identifier: str,
        outlet_entity_id: str,
    ) -> dict[str, Any]:
        """Set the water outlet for a plant."""
        entity_id = outlet_entity_id.strip()
        if not entity_id:
            return {"status": "error", "error": "Outlet entity is required"}
        if not entity_id.startswith(("light.", "switch.")):
            return {
                "status": "error",
                "error": "Outlet entity must be light.* or switch.*",
            }
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        plant_name = _match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        select_entity_id = plants[plant_name].get("water_outlet_entity_id")
        if not select_entity_id:
            return {"status": "error", "error": "Water outlet select not found"}
        error = await _select_option(select_entity_id, entity_id)
        if error:
            return {"status": "error", "error": error}
        return {
            "status": "success",
            "plant": plant_name,
            "water_outlet": entity_id,
        }
