"""Plant care tools."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .common import (
    delay,
    get_states_list,
    ha_request,
    match_plant_name,
    parse_plants_from_states,
    sanitize_attributes,
)


def register_plant_care_tools(mcp: FastMCP) -> None:
    """Register plant care tools."""

    @mcp.tool
    async def plant_care___full_status() -> dict[str, Any]:
        """Return full info for all plants (empty if none)."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = list(parse_plants_from_states(states).values())
        plants.sort(key=lambda plant: plant.get("name", ""))

        weather_entities = []
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id:
                continue
            if (
                entity_id.startswith("weather.")
                or "openweathermap" in entity_id
                or entity_id == "sun.sun"
            ):
                weather_entities.append(
                    {
                        "entity_id": entity_id,
                        "state": state.get("state"),
                        "attributes": sanitize_attributes(
                            state.get("attributes", {})
                        ),
                    }
                )
        weather_entities.sort(key=lambda item: item.get("entity_id") or "")

        return {
            "status": "success",
            "weather": weather_entities,
            "indoor_area": [],
            "indoor_plants": plants,
        }

    @mcp.tool
    async def plant_care___water(
        identifier: str,
        duration_seconds: int,
    ) -> dict[str, Any]:
        """Turn on the watering outlet for a plant for a set duration."""
        if duration_seconds <= 0:
            return {"status": "error", "error": "Duration must be positive"}
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = parse_plants_from_states(states)
        plant_name = match_plant_name(plants.keys(), identifier)
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
        _, _, error = await ha_request(
            "POST",
            "/api/services/switch/turn_on",
            json={"entity_id": switch_entity_id},
        )
        if error:
            return {"status": "error", "error": error}
        await delay(duration_seconds)
        _, _, error = await ha_request(
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
    async def plant_care___mark_manually_watered(
        identifier: str,
        state: str = "on",
    ) -> dict[str, Any]:
        """Toggle the manual watering switch for a plant."""
        state_value = state.strip().lower()
        if state_value not in {"on", "off"}:
            return {"status": "error", "error": "State must be 'on' or 'off'"}
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = parse_plants_from_states(states)
        plant_name = match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        switch_entity_id = plants[plant_name].get("manual_watering_entity_id")
        if not switch_entity_id:
            return {"status": "error", "error": "Manual watering switch not found"}
        service = "turn_on" if state_value == "on" else "turn_off"
        _, _, error = await ha_request(
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
