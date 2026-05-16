"""Tool: get_current_status."""

from __future__ import annotations

from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

from .common import (
    get_states_list,
    ha_request,
    history_window,
    parse_plants_from_states,
)


def register(mcp: FastMCP) -> None:

    def _parse_timestamp(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
            return parsed
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

    def _normalize_logbook_payload(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _manual_button_ids(
        states: list[dict[str, Any]],
    ) -> dict[str, str]:
        mapping: dict[str, str] = {}
        suffix = "Add Manual Watering"
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id.startswith("button."):
                continue
            attributes = state.get("attributes") or {}
            friendly = attributes.get("friendly_name", "")
            if not friendly or not friendly.endswith(f" {suffix}"):
                continue
            plant_name = friendly[: -len(suffix) - 1].strip()
            if plant_name:
                mapping[plant_name] = entity_id
        return mapping

    def _manual_shower_button_ids(
        states: list[dict[str, Any]],
    ) -> dict[str, str]:
        mapping: dict[str, str] = {}
        suffix = "Add Manual Shower"
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id.startswith("button."):
                continue
            attributes = state.get("attributes") or {}
            friendly = attributes.get("friendly_name", "")
            if not friendly or not friendly.endswith(f" {suffix}"):
                continue
            plant_name = friendly[: -len(suffix) - 1].strip()
            if plant_name:
                mapping[plant_name] = entity_id
        return mapping

    def _build_auto_watering_events(
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

    def _extract_event_data(entry: dict[str, Any]) -> dict[str, Any]:
        attributes = entry.get("attributes") or {}
        event_data = attributes.get("event_data") or attributes.get("event_attributes")
        if isinstance(event_data, dict):
            merged = dict(event_data)
        else:
            merged = {}
        for key in ("duration_minutes", "amount_ml", "notes"):
            if key in attributes and key not in merged:
                merged[key] = attributes.get(key)
        return merged

    def _build_manual_watering_events(
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for entry in entries:
            ts = _parse_timestamp(
                entry.get("last_changed") or entry.get("last_updated") or ""
            )
            if not ts:
                continue
            state = entry.get("state")
            event_data = _extract_event_data(entry)
            if not event_data and state in ("unknown", "unavailable", None):
                continue
            event: dict[str, Any] = {
                "type": "manual",
                "start": ts.isoformat(),
                "end": None,
                "duration_seconds": None,
            }
            if event_data.get("duration_minutes") is not None:
                event["duration_minutes"] = event_data.get("duration_minutes")
            if event_data.get("amount_ml") is not None:
                event["amount_ml"] = event_data.get("amount_ml")
            if event_data.get("notes"):
                event["notes"] = event_data.get("notes")
            if state and state not in ("unknown", "unavailable"):
                event["event"] = state
            events.append(event)
        return events

    def _build_manual_watering_button_events(
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        last_state: str | None = None
        for entry in entries:
            state = entry.get("state")
            if not state or state == last_state:
                continue
            ts = _parse_timestamp(state)
            if not ts:
                continue
            last_state = state
            events.append(
                {
                    "type": "manual",
                    "start": ts.isoformat(),
                    "end": None,
                    "duration_seconds": None,
                }
            )
        return events

    def _build_manual_watering_logbook_events(
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for entry in entries:
            ts = _parse_timestamp(entry.get("when") or entry.get("timestamp") or "")
            if not ts:
                continue
            message = entry.get("message") or entry.get("state") or ""
            event: dict[str, Any] = {
                "type": "manual",
                "start": ts.isoformat(),
                "end": None,
                "duration_seconds": None,
            }
            if message:
                event["event"] = message
            events.append(event)
        return events

    def _build_manual_shower_events(
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for entry in entries:
            ts = _parse_timestamp(
                entry.get("last_changed") or entry.get("last_updated") or ""
            )
            if not ts:
                continue
            state = entry.get("state")
            event_data = _extract_event_data(entry)
            if not event_data and state in ("unknown", "unavailable", None):
                continue
            event: dict[str, Any] = {
                "type": "shower",
                "start": ts.isoformat(),
                "end": None,
                "duration_seconds": None,
            }
            if event_data.get("duration_minutes") is not None:
                event["duration_minutes"] = event_data.get("duration_minutes")
            if event_data.get("notes"):
                event["notes"] = event_data.get("notes")
            if state and state not in ("unknown", "unavailable"):
                event["event"] = state
            events.append(event)
        return events

    def _build_manual_shower_button_events(
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        last_state: str | None = None
        for entry in entries:
            state = entry.get("state")
            if not state or state == last_state:
                continue
            ts = _parse_timestamp(state)
            if not ts:
                continue
            last_state = state
            events.append(
                {
                    "type": "shower",
                    "start": ts.isoformat(),
                    "end": None,
                    "duration_seconds": None,
                }
            )
        return events

    def _build_manual_shower_logbook_events(
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for entry in entries:
            ts = _parse_timestamp(entry.get("when") or entry.get("timestamp") or "")
            if not ts:
                continue
            message = entry.get("message") or entry.get("state") or ""
            event: dict[str, Any] = {
                "type": "shower",
                "start": ts.isoformat(),
                "end": None,
                "duration_seconds": None,
            }
            if message:
                event["event"] = message
            events.append(event)
        return events

    def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        deduped: list[dict[str, Any]] = []
        for event in events:
            key = (
                event.get("type"),
                event.get("start"),
                event.get("end"),
                event.get("duration_seconds"),
                event.get("duration_minutes"),
                event.get("amount_ml"),
                event.get("notes"),
                event.get("event"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)
        return deduped

    def _group_care_events_by_day(
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for event in events:
            start_ts = _parse_timestamp(event.get("start") or "")
            if not start_ts:
                continue
            day = start_ts.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
            bucket = buckets.setdefault(
                day,
                {
                    "date": day,
                    "auto_watering": {"total_seconds": 0},
                    "manual_watering": {"total_liters": 0.0, "count": 0},
                    "shower": {"count": 0},
                },
            )
            kind = event.get("type")
            if kind == "auto_watering":
                duration = event.get("duration_seconds")
                if isinstance(duration, int) and duration > 0:
                    bucket["auto_watering"]["total_seconds"] += duration
            elif kind == "manual":
                bucket["manual_watering"]["count"] += 1
                amount_ml = event.get("amount_ml")
                if isinstance(amount_ml, (int, float)) and amount_ml > 0:
                    bucket["manual_watering"]["total_liters"] += float(amount_ml) / 1000.0
            elif kind == "shower":
                bucket["shower"]["count"] += 1

        days = sorted(buckets.values(), key=lambda item: item.get("date") or "", reverse=True)
        for item in days:
            mw = item.get("manual_watering")
            if isinstance(mw, dict):
                mw["total_liters"] = round(mw["total_liters"], 3)
        return days

    @mcp.tool
    async def get_current_status() -> dict[str, Any]:
        """Return current weather, time, and per-plant status: soil/humidity/temperature zones and care history."""
        states, error = await get_states_list()
        if error:
            return {"status": "error", "error": error}
        raw_plants = parse_plants_from_states(states)
        manual_watering_button_entities = _manual_button_ids(states)
        manual_shower_button_entities = _manual_shower_button_ids(states)
        watering_entities: dict[str, dict[str, str | None]] = {}
        shower_entities: dict[str, dict[str, str | None]] = {}
        all_event_ids: list[str] = []
        manual_watering_ids: list[str] = []
        manual_shower_ids: list[str] = []
        for plant_name, plant in raw_plants.items():
            auto_id = plant.get("water_power_entity_id")
            manual_watering_id = plant.get("manual_watering_entity_id")
            manual_watering_button_id = manual_watering_button_entities.get(plant_name)
            manual_shower_id = plant.get("manual_shower_entity_id")
            manual_shower_button_id = manual_shower_button_entities.get(plant_name)

            watering_entities[plant_name] = {
                "auto": auto_id,
                "manual": manual_watering_id,
                "manual_button": manual_watering_button_id,
            }
            shower_entities[plant_name] = {
                "manual": manual_shower_id,
                "manual_button": manual_shower_button_id,
            }

            if auto_id:
                all_event_ids.append(auto_id)
            if manual_watering_id:
                all_event_ids.append(manual_watering_id)
                manual_watering_ids.append(manual_watering_id)
            if manual_watering_button_id:
                all_event_ids.append(manual_watering_button_id)
            if manual_shower_id:
                all_event_ids.append(manual_shower_id)
                manual_shower_ids.append(manual_shower_id)
            if manual_shower_button_id:
                all_event_ids.append(manual_shower_button_id)
        history_by_entity: dict[str, list[dict[str, Any]]] = {}
        logbook_by_entity: dict[str, list[dict[str, Any]]] = {}
        if all_event_ids:
            start_time, end_time = history_window(30)
            _, history, error = await ha_request(
                "GET",
                f"/api/history/period/{start_time.isoformat()}",
                params={
                    "end_time": end_time.isoformat(),
                    "filter_entity_id": ",".join(all_event_ids),
                },
            )
            if not error:
                history_items = _normalize_history_payload(history)
                for item in history_items:
                    entity_id = item.get("entity_id")
                    if entity_id in all_event_ids:
                        history_by_entity.setdefault(entity_id, []).append(item)
                for entries in history_by_entity.values():
                    entries.sort(
                        key=lambda entry: _parse_timestamp(
                            entry.get("last_changed")
                            or entry.get("last_updated")
                            or ""
                        )
                        or datetime.min.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
                    )
            all_manual_ids = manual_watering_ids + manual_shower_ids
            if all_manual_ids:
                _, logbook, log_error = await ha_request(
                    "GET",
                    f"/api/logbook/period/{start_time.isoformat()}",
                    params={
                        "end_time": end_time.isoformat(),
                        "entity_id": ",".join(all_manual_ids),
                    },
                )
                if not log_error:
                    log_items = _normalize_logbook_payload(logbook)
                    for item in log_items:
                        entity_id = item.get("entity_id")
                        if entity_id in all_manual_ids:
                            logbook_by_entity.setdefault(entity_id, []).append(item)
        # Build a quick lookup: entity_id -> state value for number entities
        number_states: dict[str, str] = {}
        for s in states:
            if s.get("entity_id", "").startswith("number."):
                number_states[s["entity_id"]] = s.get("state", "")

        def _get_number(plant_id: str, suffix: str) -> float | None:
            val = number_states.get(f"number.{plant_id}_{suffix}")
            try:
                return float(val) if val is not None else None
            except (ValueError, TypeError):
                return None

        def _plant_id(name: str) -> str:
            return name.lower().replace(" ", "_")

        plants = []
        for plant_name, plant in raw_plants.items():
            pid = _plant_id(plant_name)

            # Soil moisture
            mval_raw = plant.get("moisture")
            try:
                mval = float(mval_raw) if mval_raw not in (None, "unknown", "unavailable") else None
            except (ValueError, TypeError):
                mval = None
            mzone_id = plant.get("moisture_entity_id", "").replace("sensor.", "").replace(f"{pid}_", "", 1) if plant.get("moisture_entity_id") else None
            mzone_state = next((s.get("state") for s in states if s.get("entity_id") == f"sensor.{pid}_soil_moisture_zone"), None)
            soil = {
                "value": f"{round(mval)}%" if mval is not None else None,
                "zone": mzone_state,
                "green_above": _get_number(pid, "soil_moisture_yellow_threshold"),
                "red_below": _get_number(pid, "soil_moisture_red_threshold"),
            }

            # Air humidity
            hval_raw = plant.get("humidity")
            try:
                hval = float(hval_raw) if hval_raw not in (None, "unknown", "unavailable") else None
            except (ValueError, TypeError):
                hval = None
            hzone_state = next((s.get("state") for s in states if s.get("entity_id") == f"sensor.{pid}_air_humidity_zone"), None)
            humidity = {
                "value": f"{round(hval)}%" if hval is not None else None,
                "zone": hzone_state,
                "needed_min": _get_number(pid, "air_humidity_min"),
                "needed_max": _get_number(pid, "air_humidity_max"),
            }

            # Air temperature
            tval_raw = plant.get("air_temperature")
            try:
                tval = float(tval_raw) if tval_raw not in (None, "unknown", "unavailable") else None
            except (ValueError, TypeError):
                tval = None
            tzone_state = next((s.get("state") for s in states if s.get("entity_id") == f"sensor.{pid}_air_temperature_zone"), None)
            temperature = {
                "value": f"{tval}°F" if tval is not None else None,
                "zone": tzone_state,
                "needed_min_f": _get_number(pid, "air_temperature_min"),
                "needed_max_f": _get_number(pid, "air_temperature_max"),
            }

            water_meta = watering_entities.get(plant_name, {})
            auto_id = water_meta.get("auto")
            manual_watering_id = water_meta.get("manual")
            manual_watering_button_id = water_meta.get("manual_button")

            shower_meta = shower_entities.get(plant_name, {})
            manual_shower_id = shower_meta.get("manual")
            manual_shower_button_id = shower_meta.get("manual_button")

            events: list[dict[str, Any]] = []
            if auto_id:
                events.extend(
                    _build_auto_watering_events(
                        history_by_entity.get(auto_id, []),
                        "auto_watering",
                    )
                )
            if manual_watering_id:
                events.extend(
                    _build_manual_watering_events(
                        history_by_entity.get(manual_watering_id, []),
                    )
                )
                events.extend(
                    _build_manual_watering_logbook_events(
                        logbook_by_entity.get(manual_watering_id, []),
                    )
                )
            if manual_watering_button_id:
                events.extend(
                    _build_manual_watering_button_events(
                        history_by_entity.get(manual_watering_button_id, []),
                    )
                )
            if manual_shower_id:
                events.extend(
                    _build_manual_shower_events(
                        history_by_entity.get(manual_shower_id, []),
                    )
                )
                events.extend(
                    _build_manual_shower_logbook_events(
                        logbook_by_entity.get(manual_shower_id, []),
                    )
                )
            if manual_shower_button_id:
                events.extend(
                    _build_manual_shower_button_events(
                        history_by_entity.get(manual_shower_button_id, []),
                    )
                )
            events = _dedupe_events(events)
            events.sort(key=lambda item: item.get("start") or "", reverse=True)

            plants.append({
                "name": plant_name,
                "soil_moisture": soil,
                "air_humidity": humidity,
                "air_temperature": temperature,
                "care_history": _group_care_events_by_day(events),
            })
        plants.sort(key=lambda plant: plant.get("name", ""))

        # Collect time data
        la_tz = ZoneInfo("America/Los_Angeles")
        time_data = {
            "current": datetime.now(la_tz).isoformat(),
            "sunrise": None,
            "sunset": None,
        }

        weather_whitelist = {
            "sensor.openweathermap_temperature",
            "sensor.openweathermap_humidity",
            "sensor.openweathermap_condition",
        }
        weather: dict[str, Any] = {}
        for state in states:
            entity_id = state.get("entity_id", "")
            if not entity_id:
                continue
            attributes = state.get("attributes", {})
            if entity_id == "sun.sun":
                if "next_rising" in attributes:
                    sunrise_utc = _parse_timestamp(attributes.get("next_rising"))
                    if sunrise_utc:
                        time_data["sunrise"] = sunrise_utc.astimezone(la_tz).isoformat()
                if "next_setting" in attributes:
                    sunset_utc = _parse_timestamp(attributes.get("next_setting"))
                    if sunset_utc:
                        time_data["sunset"] = sunset_utc.astimezone(la_tz).isoformat()
                continue
            if entity_id in weather_whitelist:
                unit = attributes.get("unit_of_measurement") or ""
                value = state.get("state")
                key = entity_id.replace("sensor.openweathermap_", "")
                weather[key] = f"{value} {unit}".strip() if value is not None else None

        state_by_id: dict[str, str] = {s.get("entity_id", ""): s.get("state", "") for s in states}
        attrs_by_id: dict[str, dict] = {s.get("entity_id", ""): (s.get("attributes") or {}) for s in states}

        thermostat_sensor = next(
            (s for s in states if s.get("entity_id", "").startswith("sensor.thermostat_") and s.get("entity_id", "").endswith("_state")),
            None,
        )
        thermostat_info: dict = {"status": "unknown"}
        if thermostat_sensor:
            climate_eid = (thermostat_sensor.get("attributes") or {}).get("climate_entity_id")
            if climate_eid:
                _, climate_state, _ = await ha_request("GET", f"/api/states/{climate_eid}")
                if isinstance(climate_state, dict):
                    climate_attrs = climate_state.get("attributes") or {}
                    thermostat_info = {
                        "climate_entity_id": climate_eid,
                        "hvac_mode": climate_state.get("state"),
                        "hvac_action": climate_attrs.get("hvac_action"),
                        "current_temperature_f": climate_attrs.get("current_temperature"),
                        "target_temperature_f": climate_attrs.get("temperature"),
                        "min_temp_f": climate_attrs.get("min_temp"),
                        "max_temp_f": climate_attrs.get("max_temp"),
                        "hvac_modes": climate_attrs.get("hvac_modes"),
                    }

        devices = {
            "horizontal_grow_light": {
                "state": "on" if state_by_id.get("sensor.horizontal_grow_light_state") == "Light is on" else "off",
                "entity_id": "switch.horizontal_grow_light_control",
            },
            "vertical_grow_light": {
                "state": "on" if state_by_id.get("sensor.vertical_grow_light_state") == "Light is on" else "off",
                "entity_id": "switch.vertical_grow_light_control",
            },
            "humidifier": {
                "state": state_by_id.get("sensor.humidifier_status", "unknown").lower(),
                "entity_id": "switch.humidifier_control",
            },
            "thermostat": thermostat_info,
        }

        # Indoor climate: current + 2h history at 15min steps
        indoor_temp_now = state_by_id.get("sensor.gw1200b_indoor_temperature")
        indoor_humidity_now = state_by_id.get("sensor.gw1200b_indoor_humidity")

        indoor_history: list[dict[str, Any]] = []
        try:
            from datetime import timedelta
            hist_start = datetime.now(ZoneInfo("UTC")) - timedelta(hours=2)
            _, hist_data, hist_err = await ha_request(
                "GET",
                f"/api/history/period/{hist_start.isoformat()}",
                params={
                    "filter_entity_id": "sensor.gw1200b_indoor_temperature,sensor.gw1200b_indoor_humidity",
                    "minimal_response": "true",
                },
            )
            if not hist_err and isinstance(hist_data, list):
                temp_series: list[dict] = []
                humidity_series: list[dict] = []
                for group in hist_data:
                    if not group:
                        continue
                    eid = group[0].get("entity_id", "")
                    if "temperature" in eid:
                        temp_series = group
                    elif "humidity" in eid:
                        humidity_series = group

                def _bucket_series(series: list[dict]) -> dict[str, str]:
                    buckets: dict[str, str] = {}
                    for item in series:
                        ts_str = item.get("last_changed") or item.get("last_updated") or ""
                        ts = _parse_timestamp(ts_str)
                        if not ts:
                            continue
                        minute = (ts.minute // 15) * 15
                        bucket_key = ts.replace(minute=minute, second=0, microsecond=0).astimezone(ZoneInfo("America/Los_Angeles")).strftime("%H:%M")
                        buckets[bucket_key] = item.get("state", "")
                    return buckets

                temp_buckets = _bucket_series(temp_series)
                hum_buckets = _bucket_series(humidity_series)
                all_keys = sorted(set(temp_buckets) | set(hum_buckets))
                for key in all_keys:
                    indoor_history.append({
                        "time": key,
                        "temp_f": temp_buckets.get(key),
                        "humidity_pct": hum_buckets.get(key),
                    })
        except Exception:
            pass

        indoor_climate = {
            "current": {
                "temp_f": indoor_temp_now,
                "humidity_pct": indoor_humidity_now,
            },
            "history_2h_15min": indoor_history,
        }

        return {
            "status": "success",
            "time": time_data,
            "weather": weather,
            "devices": devices,
            "indoor_climate": indoor_climate,
            "plants": plants,
        }

