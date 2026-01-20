"""Home Assistant Plants tools."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
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
    "manual_watering": "Manual Watering",
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


def _collect_entity_ids(payload: Any) -> set[str]:
    entity_ids: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "entity_id":
                if isinstance(value, str):
                    entity_ids.add(value)
                elif isinstance(value, list):
                    entity_ids.update(
                        item for item in value if isinstance(item, str)
                    )
            else:
                entity_ids.update(_collect_entity_ids(value))
    elif isinstance(payload, list):
        for item in payload:
            entity_ids.update(_collect_entity_ids(item))
    return entity_ids


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
    async def list_moisture_sources() -> dict[str, Any]:
        """List available moisture source entities."""
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        options = sorted(
            state.get("entity_id")
            for state in states
            if state.get("entity_id", "").startswith(("sensor.", "number.", "input_number."))
        )
        return {"status": "success", "options": options}

    @mcp.tool
    async def list_light_outlets() -> dict[str, Any]:
        """List available light outlet entities."""
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        options = sorted(
            state.get("entity_id")
            for state in states
            if state.get("entity_id", "").startswith(("light.", "switch."))
        )
        return {"status": "success", "options": options}

    @mcp.tool
    async def list_water_outlets() -> dict[str, Any]:
        """List available water outlet entities."""
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        options = sorted(
            state.get("entity_id")
            for state in states
            if state.get("entity_id", "").startswith(("light.", "switch."))
        )
        return {"status": "success", "options": options}

    @mcp.tool
    async def get_plants_automation_status() -> dict[str, Any]:
        """Return configured outlet entities and matching automations."""
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        outlet_entities: set[str] = set()
        for plant in plants.values():
            for key in ("light_outlet", "water_outlet"):
                value = plant.get(key)
                if value and value != "None":
                    outlet_entities.add(value)
        outlets = sorted(outlet_entities)
        if not outlets:
            return {"status": "success", "outlets": [], "automations": []}

        _, automations, error = await _ha_request(
            "GET",
            "/api/config/automation/config",
        )
        if error:
            return {"status": "error", "error": error}
        if not isinstance(automations, list):
            return {"status": "error", "error": "Unexpected automation response"}

        matched = []
        for automation in automations:
            entity_ids = _collect_entity_ids(automation)
            relevant = sorted(entity_ids.intersection(outlet_entities))
            if not relevant:
                continue
            matched.append(
                {
                    "id": automation.get("id"),
                    "alias": automation.get("alias"),
                    "enabled": automation.get("enabled"),
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
    async def get_watering_history(
        identifier: str,
        days: int = 60,
    ) -> dict[str, Any]:
        """Return watering history for a plant (manual + automatic)."""
        if days <= 0:
            return {"status": "error", "error": "Days must be positive"}
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        plant_name = _match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        auto_switch_id = plants[plant_name].get("water_power_entity_id")
        manual_switch_id = plants[plant_name].get("manual_watering_entity_id")
        if not auto_switch_id and not manual_switch_id:
            return {"status": "error", "error": "Water switches not found"}
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        filter_ids = [
            entity_id
            for entity_id in (auto_switch_id, manual_switch_id)
            if entity_id
        ]
        _, history, error = await _ha_request(
            "GET",
            f"/api/history/period/{start_time.isoformat()}",
            params={
                "filter_entity_id": ",".join(filter_ids),
                "end_time": end_time.isoformat(),
                "minimal_response": "1",
            },
        )
        if error:
            return {"status": "error", "error": error}
        entries = []
        if isinstance(history, list):
            for entity_states in history:
                for item in entity_states:
                    state = item.get("state")
                    if state != "on":
                        continue
                    entity_id = item.get("entity_id")
                    if not entity_id:
                        continue
                    entry_type = "automatic" if entity_id == auto_switch_id else "manual"
                    entries.append(
                        {
                            "type": entry_type,
                            "state": state,
                            "last_changed": item.get("last_changed"),
                        }
                    )
        entries.sort(key=lambda item: item.get("last_changed", ""), reverse=True)
        return {
            "status": "success",
            "plant": plant_name,
            "water_switch": auto_switch_id,
            "manual_switch": manual_switch_id,
            "history": entries,
        }

    @mcp.tool
    async def water_plant(
        identifier: str,
        duration_seconds: int,
    ) -> dict[str, Any]:
        """Turn on the watering outlet for a plant for a set duration."""
        if duration_seconds <= 0:
            return {"status": "error", "error": "Duration must be positive"}
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
            return {
                "status": "error",
                "error": (
                    "No watering device is configured for this plant. "
                    "You can only water it manually."
                ),
            }
        outlet_state = next(
            (
                state
                for state in states
                if state.get("entity_id") == switch_entity_id
            ),
            None,
        )
        if not outlet_state or outlet_state.get("state") == "unavailable":
            return {
                "status": "error",
                "error": (
                    "The watering device for this plant is unavailable. "
                    "You can only water it manually."
                ),
            }
        _, _, error = await _ha_request(
            "POST",
            "/api/services/switch/turn_on",
            json={"entity_id": switch_entity_id},
        )
        if error:
            return {"status": "error", "error": error}
        await asyncio.sleep(duration_seconds)
        _, _, error = await _ha_request(
            "POST",
            "/api/services/switch/turn_off",
            json={"entity_id": switch_entity_id},
        )
        if error:
            return {"status": "error", "error": error}
        return {
            "status": "success",
            "plant": plant_name,
            "water_switch": switch_entity_id,
            "duration_seconds": duration_seconds,
        }

    @mcp.tool
    async def manual_water_plant(
        identifier: str,
        state: str = "on",
    ) -> dict[str, Any]:
        """Toggle the manual watering switch for a plant."""
        state_value = state.strip().lower()
        if state_value not in {"on", "off"}:
            return {"status": "error", "error": "State must be 'on' or 'off'"}
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        plant_name = _match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        switch_entity_id = plants[plant_name].get("manual_watering_entity_id")
        if not switch_entity_id:
            return {"status": "error", "error": "Manual watering switch not found"}
        service = "turn_on" if state_value == "on" else "turn_off"
        _, _, error = await _ha_request(
            "POST",
            f"/api/services/switch/{service}",
            json={"entity_id": switch_entity_id},
        )
        if error:
            return {"status": "error", "error": error}
        return {
            "status": "success",
            "plant": plant_name,
            "manual_switch": switch_entity_id,
            "state": state_value,
        }

    @mcp.tool
    async def add_plant(
        name: str,
        moisture_entity_id: str = "",
    ) -> dict[str, Any]:
        """Create a new plant device via the Plants service."""
        if not name.strip():
            return {"status": "error", "error": "Name is required"}
        user_input: dict[str, Any] = {"name": name.strip()}
        if moisture_entity_id.strip():
            user_input["moisture_entity_id"] = moisture_entity_id.strip()
        _, _, error = await _ha_request(
            "POST",
            "/api/services/plants/add_plant",
            json=user_input,
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "name": name.strip()}

    @mcp.tool
    async def delete_plant(identifier: str) -> dict[str, Any]:
        """Delete a plant device via the Plants service."""
        states, error = await _get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = _parse_plants_from_states(states)
        plant_name = _match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        _, _, error = await _ha_request(
            "POST",
            "/api/services/plants/remove_plant",
            json={"name": plant_name},
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "deleted": plant_name}

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
