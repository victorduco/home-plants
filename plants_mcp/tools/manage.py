"""Plant management tools."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .common import (
    PLANT_SUFFIXES,
    get_states_list,
    ha_request,
    match_plant_name,
    parse_plants_from_states,
)


def register_manage_tools(mcp: FastMCP) -> None:
    """Register management tools."""

    @mcp.tool
    async def manage___add_plant(
        name: str,
        moisture_entity_id: str = "",
    ) -> dict[str, Any]:
        """Create a new plant device via the Plants service."""
        if not name.strip():
            return {"status": "error", "error": "Name is required"}
        user_input: dict[str, Any] = {"name": name.strip()}
        if moisture_entity_id.strip():
            user_input["moisture_entity_id"] = moisture_entity_id.strip()
        _, _, error = await ha_request(
            "POST",
            "/api/services/plants/add_plant",
            json=user_input,
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "name": name.strip()}

    @mcp.tool
    async def manage___remove_plant(identifier: str) -> dict[str, Any]:
        """Delete a plant device via the Plants service."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = parse_plants_from_states(states)
        plant_name = match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        _, _, error = await ha_request(
            "POST",
            "/api/services/plants/remove_plant",
            json={"name": plant_name},
        )
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "deleted": plant_name}

    @mcp.tool
    async def manage___get_plant_fields_info() -> dict[str, Any]:
        """Get plant fields metadata (configuration and recommendations only)."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}

        plants: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for state in states:
            entity_id = state.get("entity_id")
            if not entity_id:
                continue
            attributes = state.get("attributes", {})
            friendly = attributes.get("friendly_name", "")
            if not friendly:
                continue

            matched_key = None
            plant_name = None
            for key, suffix in PLANT_SUFFIXES.items():
                if friendly.endswith(f" {suffix}"):
                    matched_key = key
                    plant_name = friendly[: -len(suffix) - 1].strip()
                    break
            if not matched_key or not plant_name:
                continue

            domain = entity_id.split(".")[0]

            # Only include select (configuration) and text (recommendations)
            if domain == "select":
                category = "configuration"
            elif domain == "text":
                category = "recommendations"
            else:
                # Skip controls and sensors
                continue

            # Build field info with only relevant fields
            field_info: dict[str, Any] = {
                "type": domain,
                "name": friendly,
                "current_value": state.get("state"),
                "required": False,
                "entity_id": entity_id,
            }

            # Add domain-specific fields
            if domain == "select":
                options = attributes.get("options")
                if options:
                    field_info["options"] = options
            elif domain == "text":
                # Text entities don't need extra metadata in output
                pass

            plant_fields = plants.setdefault(
                plant_name,
                {
                    "recommendations": [],
                    "configuration": [],
                },
            )
            plant_fields[category].append(field_info)

        result = []
        for plant_name, groups in plants.items():
            for key in groups:
                groups[key].sort(key=lambda item: item.get("name") or "")
            result.append({"name": plant_name, "fields": groups})
        result.sort(key=lambda item: item.get("name") or "")
        return {"status": "success", "plants": result}

    @mcp.tool
    async def manage___set_plant_fields() -> dict[str, Any]:
        """Set plant fields."""
        return {"status": "error", "error": "Not implemented yet"}
