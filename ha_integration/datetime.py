"""Datetime platform for Plants."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data import PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants datetime entities from a config entry."""
    data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities(
        [PlantLastWateredDateTime(entry, data, plant_id) for plant_id in data.plants]
    )


class PlantLastWateredDateTime(DateTimeEntity):
    """Last watered datetime."""

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, plant_id: str
    ) -> None:
        self._entry = entry
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Last Watered"
        self._attr_unique_id = f"{entry.entry_id}_plant_{plant_id}_last_watered"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> datetime | None:
        return self._data.plants[self._plant_id].last_watered

    async def async_set_value(self, value: datetime) -> None:
        self._data.plants[self._plant_id].last_watered = value
        await self._data.async_save()
        self.async_write_ha_state()
