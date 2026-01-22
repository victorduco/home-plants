"""Shared helpers for Plants MCP tools."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
from typing import Any, Iterable
import uuid

import httpx

PLANT_SUFFIXES = {
    "moisture": "Soil Moisture State",
    "moisture_source": "Soil Moisture Device Source",
    "humidity": "Air Humidity Meter",
    "humidity_source": "Air Humidity Meter Source",
    "air_temperature": "Air Temperature Meter",
    "air_temperature_source": "Air Temperature Meter Source",
    "light_outlet": "Grow Light Device Source",
    "water_outlet": "Auto Watering Device Source",
    "light_power": "Grow Light Control",
    "water_power": "Auto Watering Control",
    "manual_watering": "Manual Watering Control",
    "light_state": "Grow Light State",
    "auto_watering_state": "Auto Watering State",
    "humidifier_state": "Air Humidifier State",
    "humidifier_control": "Air Humidifier Control",
    "humidifier_source": "Air Humidifier Device Source",
    "watering_frequency_recommendation": "Watering Frequency Recommendation (e.g., once a week)",
    "soil_moisture_recommendation": "Minimum Soil Moisture for Watering Recommendation (e.g., 25%)",
    "air_temperature_recommendation": "Air Temperature Recommendation (e.g., 20-24 C)",
    "air_humidity_recommendation": "Air Humidity Recommendation (e.g., 50-60%)",
    "other_recommendations": "Other Recommendations (e.g., - rotate weekly; - avoid drafts;)",
    "todo_list": "Todo List (e.g., - repot in spring; - prune dry leaves;)",
}


def _get_ha_config() -> tuple[str, str] | None:
    ha_token = os.getenv("HA_TOKEN", "")
    ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123").rstrip("/")
    if not ha_token:
        return None
    return ha_url, ha_token


async def ha_request(
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


async def get_states_list() -> tuple[list[dict[str, Any]], str | None]:
    _, data, error = await ha_request("GET", "/api/states")
    if error:
        return [], error
    if not isinstance(data, list):
        return [], "Unexpected states response"
    return data, None


def match_plant_name(names: Iterable[str], identifier: str) -> str | None:
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


def sanitize_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    if "options" not in attributes:
        return attributes
    cleaned = dict(attributes)
    cleaned.pop("options", None)
    return cleaned


def parse_plants_from_states(
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
                "attributes": sanitize_attributes(attributes),
            }
        )
        plant_info[f"{matched_key}_entity_id"] = entity_id
        plant_info[matched_key] = state.get("state")
    return plants


def collect_entity_ids(payload: Any) -> set[str]:
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
                entity_ids.update(collect_entity_ids(value))
    elif isinstance(payload, list):
        for item in payload:
            entity_ids.update(collect_entity_ids(item))
    return entity_ids


async def select_option(entity_id: str, option: str) -> str | None:
    _, _, error = await ha_request(
        "POST",
        "/api/services/select/select_option",
        json={"entity_id": entity_id, "option": option},
    )
    return error


def new_automation_id(value: str) -> str:
    trimmed = value.strip()
    return trimmed or uuid.uuid4().hex


def history_window(days: int) -> tuple[datetime, datetime]:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    return start_time, end_time


async def delay(seconds: int) -> None:
    await asyncio.sleep(seconds)
