"""Plant care tools."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from fastmcp import FastMCP

from .common import (
    PLANT_SUFFIXES,
    delay,
    get_states_list,
    ha_request,
    history_window,
    match_plant_name,
    parse_plants_from_states,
    sanitize_attributes,
)


def register_plant_care_tools(mcp: FastMCP) -> None:
    """Register plant care tools."""

    def _strip_plant_name(friendly_name: str) -> str:
        for suffix in PLANT_SUFFIXES.values():
            if friendly_name.endswith(f" {suffix}"):
                return suffix
        return friendly_name

    def _parse_timestamp(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _normalize_history_payload(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            return []
        if payload and isinstance(payload[0], list):
            items: list[dict[str, Any]] = []
            for group in payload:
                if isinstance(group, list):
                    items.extend(item for item in group if isinstance(item, dict))
            return items
        return [item for item in payload if isinstance(item, dict)]

    def _build_watering_events(
        entries: list[dict[str, Any]],
        kind: str,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        current_start: datetime | None = None
        for entry in entries:
            state = entry.get("state")
            ts = _parse_timestamp(
                entry.get("last_changed") or entry.get("last_updated") or ""
            )
            if not ts:
                continue
            if state == "on" and current_start is None:
                current_start = ts
            elif state != "on" and current_start is not None:
                duration = int((ts - current_start).total_seconds())
                events.append(
                    {
                        "type": kind,
                        "start": current_start.isoformat(),
                        "end": ts.isoformat(),
                        "duration_seconds": duration,
                    }
                )
                current_start = None
        if current_start is not None:
            events.append(
                {
                    "type": kind,
                    "start": current_start.isoformat(),
                    "end": None,
                    "duration_seconds": None,
                }
            )
        return events

    @mcp.tool
    async def plant_care___full_status() -> dict[str, Any]:
        """Return full info for all plants (empty if none)."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}
        raw_plants = parse_plants_from_states(states)
        watering_entities: dict[str, dict[str, str | None]] = {}
        watering_ids: list[str] = []
        for plant_name, plant in raw_plants.items():
            auto_id = plant.get("water_power_entity_id")
            manual_id = plant.get("manual_watering_entity_id")
            watering_entities[plant_name] = {
                "auto": auto_id,
                "manual": manual_id,
            }
            if auto_id:
                watering_ids.append(auto_id)
            if manual_id:
                watering_ids.append(manual_id)
        history_by_entity: dict[str, list[dict[str, Any]]] = {}
        if watering_ids:
            start_time, end_time = history_window(30)
            _, history, error = await ha_request(
                "GET",
                f"/api/history/period/{start_time.isoformat()}",
                params={
                    "end_time": end_time.isoformat(),
                    "filter_entity_id": ",".join(watering_ids),
                    "minimal_response": 1,
                },
            )
            if not error:
                history_items = _normalize_history_payload(history)
                for item in history_items:
                    entity_id = item.get("entity_id")
                    if entity_id in watering_ids:
                        history_by_entity.setdefault(entity_id, []).append(item)
                for entries in history_by_entity.values():
                    entries.sort(
                        key=lambda entry: _parse_timestamp(
                            entry.get("last_changed")
                            or entry.get("last_updated")
                            or ""
                        )
                        or datetime.min.replace(tzinfo=timezone.utc)
                    )
        plants = []
        for plant_name, plant in raw_plants.items():
            grouped = {
                "controls": [],
                "configuration": [],
                "sensors": [],
                "recommendations": [],
            }
            for entity in plant.get("entities", []):
                entity_id = entity.get("entity_id", "")
                attributes = entity.get("attributes", {})
                name = attributes.get("friendly_name", entity_id)
                unit = attributes.get("unit_of_measurement") or ""
                value = entity.get("state")
                display = f"{value} {unit}".strip() if value is not None else ""
                domain = entity_id.split(".", 1)[0] if entity_id else ""
                if domain == "text":
                    category = "recommendations"
                elif domain == "select":
                    category = "configuration"
                elif domain in {"switch", "valve"}:
                    category = "controls"
                else:
                    category = "sensors"
                grouped[category].append(
                    {
                        "name": _strip_plant_name(name),
                        "value": display,
                    }
                )
            normalized = {}
            for key, items in grouped.items():
                items.sort(key=lambda item: item.get("name") or "")
                normalized[key] = {item["name"]: item["value"] for item in items}
            water_meta = watering_entities.get(plant_name, {})
            auto_id = water_meta.get("auto")
            manual_id = water_meta.get("manual")
            events: list[dict[str, Any]] = []
            if auto_id:
                events.extend(
                    _build_watering_events(
                        history_by_entity.get(auto_id, []),
                        "auto",
                    )
                )
            if manual_id:
                events.extend(
                    _build_watering_events(
                        history_by_entity.get(manual_id, []),
                        "manual",
                    )
                )
            events.sort(key=lambda item: item.get("start") or "", reverse=True)
            normalized["watering_history"] = events
            plants.append({"name": plant_name, "fields": normalized})
        plants.sort(key=lambda plant: plant.get("name", ""))

        weather_entities = []
        weather_blacklist = {
            "sensor.openweathermap_apparent_temperature",
            "sensor.openweathermap_dew_point_temperature",
            "sensor.openweathermap_wind_speed",
            "sensor.openweathermap_wind_gust_speed",
            "sensor.openweathermap_wind_direction",
            "sensor.openweathermap_pressure",
            "sensor.openweathermap_snow_intensity",
            "sensor.openweathermap_precipitation_kind",
            "sensor.openweathermap_weather_code",
        }
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id:
                continue
            if (
                entity_id.startswith("weather.")
                or "openweathermap" in entity_id
                or entity_id == "sun.sun"
            ):
                if entity_id in weather_blacklist:
                    continue
                attributes = state.get("attributes", {})
                if entity_id == "sun.sun":
                    for key, label in (
                        ("next_rising", "Sun Next Rising"),
                        ("next_setting", "Sun Next Setting"),
                    ):
                        if key in attributes:
                            weather_entities.append(
                                {"name": label, "value": attributes.get(key)}
                            )
                    continue
                unit = attributes.get("unit_of_measurement") or ""
                value = state.get("state")
                display = f"{value} {unit}".strip() if value is not None else ""
                name = attributes.get("friendly_name", entity_id)
                if name.startswith("OpenWeatherMap "):
                    name = name.replace("OpenWeatherMap ", "", 1)
                if name == "OpenWeatherMap":
                    name = "Weather"
                weather_entities.append(
                    {
                        "name": name,
                        "value": display,
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
    async def plant_care___get_plant_history(
        identifier: str,
        details: str = "main",
        days: int = 7,
        step_hours: int = 6,
    ) -> dict[str, Any]:
        """Return history for plant sensors and watering events."""
        if days <= 0:
            return {"status": "error", "error": "Days must be positive"}
        if step_hours <= 0:
            return {"status": "error", "error": "step_hours must be positive"}
        details_value = details.strip().lower() if details else "main"
        if details_value not in {"main", "full"}:
            return {
                "status": "error",
                "error": "details must be 'main' or 'full'",
            }
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}
        plants = parse_plants_from_states(states)
        plant_name = match_plant_name(plants.keys(), identifier)
        if not plant_name:
            return {"status": "error", "error": "Plant not found"}
        plant = plants[plant_name]
        entity_ids = {
            "soil_moisture": plant.get("moisture_entity_id"),
            "air_humidity": plant.get("humidity_entity_id"),
            "air_temperature": plant.get("air_temperature_entity_id"),
            "auto_watering_state": plant.get("auto_watering_state_entity_id"),
            "manual_watering": plant.get("manual_watering_entity_id"),
        }
        if details_value == "full":
            for key, value in plant.items():
                if not key.endswith("_entity_id"):
                    continue
                label = key[: -len("_entity_id")]
                if label not in entity_ids or not entity_ids[label]:
                    entity_ids[label] = value
        active_ids = [eid for eid in entity_ids.values() if eid]
        if not active_ids:
            return {
                "status": "error",
                "error": "No sensors configured for this plant",
            }

        start_time, end_time = history_window(days)
        _, history, error = await ha_request(
            "GET",
            f"/api/history/period/{start_time.isoformat()}",
            params={
                "end_time": end_time.isoformat(),
                "filter_entity_id": ",".join(active_ids),
                "minimal_response": 1,
            },
        )
        if error:
            return {"status": "error", "error": error}
        history_items = _normalize_history_payload(history)
        grouped: dict[str, list[dict[str, Any]]] = {eid: [] for eid in active_ids}
        for item in history_items:
            entity_id = item.get("entity_id")
            if entity_id not in grouped:
                continue
            grouped[entity_id].append(item)
        for entries in grouped.values():
            entries.sort(
                key=lambda entry: _parse_timestamp(
                    entry.get("last_changed") or entry.get("last_updated") or ""
                )
                or datetime.min.replace(tzinfo=timezone.utc)
            )

        def last_state_before(
            entries: list[dict[str, Any]],
            timestamp: datetime,
        ) -> dict[str, Any] | None:
            last = None
            for entry in entries:
                ts = _parse_timestamp(
                    entry.get("last_changed") or entry.get("last_updated") or ""
                )
                if not ts or ts > timestamp:
                    break
                last = entry
            return last

        points = []
        step_seconds = step_hours * 3600
        start_epoch = int(start_time.timestamp())
        end_epoch = int(end_time.timestamp())
        for ts_epoch in range(end_epoch, start_epoch - 1, -step_seconds):
            ts = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
            point = {"timestamp": ts.isoformat()}
            for key, entity_id in entity_ids.items():
                if not entity_id:
                    point[key] = None
                    continue
                entry = last_state_before(grouped.get(entity_id, []), ts)
                point[key] = entry.get("state") if entry else None
            points.append(point)

        result: dict[str, Any] = {
            "status": "success",
            "plant": plant_name,
            "details": details_value,
            "days": days,
            "step_hours": step_hours,
            "points": points,
        }
        if details_value == "full":
            result["entities"] = entity_ids
        return result

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
