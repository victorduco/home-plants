"""Event platform for Plants manual watering."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity, EventDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .data import PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants event entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    if entry_data["type"] == "meter_locations":
        return
    data: PlantsData = entry_data["data"]
    entities = [
        PlantManualWateringEvent(data, plant_id) for plant_id in data.plants
    ]
    if entities:
        async_add_entities(entities)


class PlantManualWateringEvent(EventEntity):
    """Event entity for manual plant watering tracking."""

    _attr_has_entity_name = True
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = ["watered"]

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        """Initialize the event entity."""
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]

        self._attr_name = "Manual Watering"
        self._attr_unique_id = f"plant_{plant_id}_manual_watering"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    def record_watering(
        self,
        duration_minutes: int | None = None,
        amount_ml: int | None = None,
        notes: str | None = None,
    ) -> None:
        """Record a manual watering event."""
        now = dt_util.utcnow()
        event_data: dict[str, Any] = {"timestamp": now.isoformat()}

        if duration_minutes is not None:
            event_data["duration_minutes"] = duration_minutes
        if amount_ml is not None:
            event_data["amount_ml"] = amount_ml
        if notes:
            event_data["notes"] = notes

        self._attr_event_type = "watered"
        self._attr_extra_state_attributes = {"event_data": event_data}
        self._trigger_event("watered", event_data)
        self.async_write_ha_state()
