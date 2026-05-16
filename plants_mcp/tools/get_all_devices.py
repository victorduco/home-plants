"""Tool: get_all_devices."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .common import get_states_list

_GROW_LIGHT_PREFIXES = ("horizontal_grow_light", "vertical_grow_light")
_AUTO_WATERER_PREFIXES = ("auto_waterer",)
_HUMIDIFIER_PREFIXES = ("humidifier",)
_THERMOSTAT_PREFIXES = ("thermostat",)
_INTERESTING_DOMAINS = {"sensor", "switch", "valve", "button", "number", "select", "climate"}
_PLANT_SLOT_SUFFIX = tuple(f"_plant_{i}" for i in range(1, 21))


def _device_prefix(entity_id: str) -> str | None:
    name = entity_id.split(".", 1)[-1]
    for prefix in (*_GROW_LIGHT_PREFIXES, *_AUTO_WATERER_PREFIXES, *_HUMIDIFIER_PREFIXES, *_THERMOSTAT_PREFIXES):
        if name == prefix or name.startswith(prefix + "_"):
            return prefix
    return None


def _group_entities(states: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for state in states:
        entity_id = state.get("entity_id", "")
        domain = entity_id.split(".")[0]
        if domain not in _INTERESTING_DOMAINS:
            continue
        prefix = _device_prefix(entity_id)
        if prefix is None:
            continue
        entry: dict[str, Any] = {"entity_id": entity_id, "state": state.get("state")}
        attrs = state.get("attributes", {})
        if attrs.get("friendly_name"):
            entry["name"] = attrs["friendly_name"]
        if attrs.get("unit_of_measurement"):
            entry["unit"] = attrs["unit_of_measurement"]
        groups.setdefault(prefix, []).append(entry)
    return groups


def _build_device(prefix: str, label: str, device_type: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    nearby_plants: list[str] = []
    regular: list[dict[str, Any]] = []
    for e in entities:
        eid = e["entity_id"]
        name_part = eid.split(".", 1)[-1]
        if eid.startswith("select.") and any(name_part.endswith(s) for s in _PLANT_SLOT_SUFFIX):
            val = e.get("state")
            if val and val not in ("None", "unknown", "unavailable"):
                nearby_plants.append(val)
        else:
            regular.append(e)
    return {
        "name": label,
        "type": device_type,
        "nearby_plants": sorted(nearby_plants),
        "entities": sorted(regular, key=lambda x: x["entity_id"]),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_all_devices() -> dict[str, Any]:
        """Return all plant-related devices (grow lights, auto waterer, humidifier) with their entities and nearby plants."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}

        groups = _group_entities(states)
        devices: list[dict[str, Any]] = []

        for prefix in _GROW_LIGHT_PREFIXES:
            if prefix in groups:
                devices.append(_build_device(prefix, prefix.replace("_", " ").title(), "grow_light", groups[prefix]))
        for prefix in _AUTO_WATERER_PREFIXES:
            if prefix in groups:
                devices.append(_build_device(prefix, prefix.replace("_", " ").title(), "auto_waterer", groups[prefix]))
        for prefix in _HUMIDIFIER_PREFIXES:
            if prefix in groups:
                devices.append(_build_device(prefix, prefix.replace("_", " ").title(), "humidifier", groups[prefix]))
        for prefix in _THERMOSTAT_PREFIXES:
            if prefix in groups:
                devices.append(_build_device(prefix, prefix.replace("_", " ").title(), "thermostat", groups[prefix]))

        return {"status": "success", "devices": devices}
