"""Plants tool — returns all plants with all their entities."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .common import get_states_list, parse_plants_from_states, PLANT_SUFFIXES

_SUFFIX_TO_KEY = {v: k for k, v in PLANT_SUFFIXES.items()}


def _classify(entity_id: str) -> str:
    domain = entity_id.split(".")[0]
    if domain == "number":
        return "thresholds"
    if domain == "text":
        return "recommendations"
    if domain in {"switch", "valve"}:
        return "controls"
    if domain == "button":
        return "buttons"
    if domain == "select":
        return "config"
    return "sensors"


def register_plants_tools(mcp: FastMCP) -> None:
    """Register plants tools."""

    @mcp.tool
    async def plants___all() -> dict[str, Any]:
        """Return all plants with all their entities grouped by category."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}

        # Also grab number entities which aren't in parse_plants_from_states
        number_states: dict[str, dict[str, Any]] = {}
        button_states: dict[str, dict[str, Any]] = {}
        for s in states:
            eid = s.get("entity_id", "")
            if eid.startswith("number."):
                number_states[eid] = s
            elif eid.startswith("button."):
                button_states[eid] = s

        raw_plants = parse_plants_from_states(states)

        plants: list[dict[str, Any]] = []
        for plant_name, plant in sorted(raw_plants.items()):
            grouped: dict[str, list[dict[str, Any]]] = {
                "sensors": [],
                "thresholds": [],
                "controls": [],
                "buttons": [],
                "recommendations": [],
                "config": [],
            }

            for entity in plant.get("entities", []):
                entity_id = entity.get("entity_id", "")
                attrs = entity.get("attributes", {})
                value = entity.get("state")
                unit = attrs.get("unit_of_measurement") or ""
                category = _classify(entity_id)
                grouped[category].append({
                    "entity_id": entity_id,
                    "name": attrs.get("friendly_name", entity_id),
                    "state": f"{value} {unit}".strip() if value is not None else None,
                })

            # Add number entities by name pattern
            pid = plant_name.lower().replace(" ", "_")
            for eid, s in number_states.items():
                if f".{pid}_" in eid or eid == f"number.{pid}":
                    attrs = s.get("attributes", {})
                    value = s.get("state")
                    unit = attrs.get("unit_of_measurement") or ""
                    grouped["thresholds"].append({
                        "entity_id": eid,
                        "name": attrs.get("friendly_name", eid),
                        "state": f"{value} {unit}".strip() if value is not None else None,
                    })

            # Add button entities by name pattern
            for eid, s in button_states.items():
                if f".{pid}_" in eid or eid == f"button.{pid}":
                    attrs = s.get("attributes", {})
                    grouped["buttons"].append({
                        "entity_id": eid,
                        "name": attrs.get("friendly_name", eid),
                        "state": s.get("state"),
                    })

            # Sort each category and remove empty ones
            result: dict[str, Any] = {"name": plant_name}
            for cat, items in grouped.items():
                if items:
                    result[cat] = sorted(items, key=lambda x: x["entity_id"])

            plants.append(result)

        return {"status": "success", "plants": plants}
