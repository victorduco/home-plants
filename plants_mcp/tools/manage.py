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
    async def manage___get_plant_fields_info(plant_name: str) -> dict[str, Any]:
        """Get editable plant fields metadata."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}

        # Parse all plants to find the target
        plants_data = parse_plants_from_states(states)
        matched_name = match_plant_name(plants_data.keys(), plant_name)
        if not matched_name:
            return {"status": "error", "error": "Plant not found"}

        # Collect fields for the specific plant
        plant_fields: dict[str, list[dict[str, Any]]] = {
            "recommendations": [],
            "configuration": [],
        }

        for state in states:
            entity_id = state.get("entity_id")
            if not entity_id:
                continue
            attributes = state.get("attributes", {})
            friendly = attributes.get("friendly_name", "")
            if not friendly:
                continue

            # Check if this entity belongs to the target plant
            matched_key = None
            entity_plant_name = None
            for key, suffix in PLANT_SUFFIXES.items():
                if friendly.endswith(f" {suffix}"):
                    matched_key = key
                    entity_plant_name = friendly[: -len(suffix) - 1].strip()
                    break

            if not matched_key or entity_plant_name != matched_name:
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
                # Add example attribute if present
                example = attributes.get("example")
                if example:
                    field_info["example"] = example

            plant_fields[category].append(field_info)

        # Sort fields by name
        for key in plant_fields:
            plant_fields[key].sort(key=lambda item: item.get("name") or "")

        return {
            "status": "success",
            "plant": matched_name,
            "fields": plant_fields,
        }

    @mcp.tool
    async def manage___set_plant_fields(
        plant_name: str,
        fields: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Set plant fields (configuration and recommendations).

        Args:
            plant_name: Name of the plant
            fields: List of field updates, each with 'entity_id' and 'value'
                    Example: [{"entity_id": "select.alocasia_water_outlet", "value": "valve.watering_device_1"}]
        """
        if not fields:
            return {"status": "error", "error": "No fields provided"}

        # Get current plant fields info for validation
        fields_info_result = await manage___get_plant_fields_info(plant_name)
        if fields_info_result["status"] != "success":
            return fields_info_result

        # Build a map of entity_id -> field_info for validation
        editable_fields: dict[str, dict[str, Any]] = {}
        for category in ["configuration", "recommendations"]:
            for field in fields_info_result["fields"][category]:
                editable_fields[field["entity_id"]] = field

        # Validate and prepare service calls
        errors = []
        updates = []

        for field_update in fields:
            entity_id = field_update.get("entity_id")
            value = field_update.get("value")

            if not entity_id:
                errors.append("Missing entity_id in field update")
                continue

            if value is None:
                errors.append(f"Missing value for {entity_id}")
                continue

            # Check if field is editable
            if entity_id not in editable_fields:
                errors.append(
                    f"Field {entity_id} is not editable or does not belong to {plant_name}"
                )
                continue

            field_info = editable_fields[entity_id]
            domain = field_info["type"]

            # Validate based on field type
            if domain == "select":
                # Validate against options
                options = field_info.get("options", [])
                if not options:
                    errors.append(f"No options available for {entity_id}")
                    continue
                if value not in options:
                    errors.append(
                        f"Invalid value '{value}' for {entity_id}. Valid options: {', '.join(options)}"
                    )
                    continue

                updates.append({
                    "service": "select/select_option",
                    "entity_id": entity_id,
                    "data": {"option": value},
                })

            elif domain == "text":
                # Validate text length
                value_str = str(value)
                # Note: min/max are not provided by get_plant_fields_info anymore
                # But we can still validate based on entity attributes if needed

                updates.append({
                    "service": "text/set_value",
                    "entity_id": entity_id,
                    "data": {"value": value_str},
                })

            else:
                errors.append(f"Unsupported field type '{domain}' for {entity_id}")
                continue

        if errors:
            return {
                "status": "error",
                "error": "Validation failed",
                "errors": errors,
            }

        # Execute all updates
        results = []
        for update in updates:
            service_path = update["service"]
            entity_id = update["entity_id"]
            data = update["data"]
            data["entity_id"] = entity_id

            domain, service = service_path.split("/")
            _, _, error = await ha_request(
                "POST",
                f"/api/services/{domain}/{service}",
                json=data,
            )

            if error:
                errors.append(f"Failed to update {entity_id}: {error}")
            else:
                results.append({
                    "entity_id": entity_id,
                    "updated": True,
                })

        if errors:
            return {
                "status": "partial_success",
                "updated": results,
                "errors": errors,
            }

        return {
            "status": "success",
            "plant": plant_name,
            "updated": results,
        }
