"""Tool: get_all_plants."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .common import get_states_list, parse_plants_from_states


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


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_all_plants() -> dict[str, Any]:
        """Return all plants with all their entities grouped by category (sensors, thresholds, controls, buttons, recommendations)."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}

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
                "sensors": [], "thresholds": [], "controls": [],
                "buttons": [], "recommendations": [], "config": [],
            }

            for entity in plant.get("entities", []):
                entity_id = entity.get("entity_id", "")
                attrs = entity.get("attributes", {})
                value = entity.get("state")
                unit = attrs.get("unit_of_measurement") or ""
                grouped[_classify(entity_id)].append({
                    "entity_id": entity_id,
                    "name": attrs.get("friendly_name", entity_id),
                    "state": f"{value} {unit}".strip() if value is not None else None,
                })

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

            for eid, s in button_states.items():
                if f".{pid}_" in eid or eid == f"button.{pid}":
                    attrs = s.get("attributes", {})
                    grouped["buttons"].append({
                        "entity_id": eid,
                        "name": attrs.get("friendly_name", eid),
                        "state": s.get("state"),
                    })

            result: dict[str, Any] = {"name": plant_name}
            for cat, items in grouped.items():
                if items:
                    result[cat] = sorted(items, key=lambda x: x["entity_id"])
            plants.append(result)

        return {"status": "success", "plants": plants}
