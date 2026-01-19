"""Datetime platform for Plants."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data import PlantData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants datetime entities from a config entry."""
    data: PlantData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PlantLastWateredDateTime(entry, data)])


class PlantLastWateredDateTime(DateTimeEntity):
    """Last watered datetime."""

    def __init__(self, entry: ConfigEntry, data: PlantData) -> None:
        self._entry = entry
        self._data = data
        name = entry.data.get("name", "Plant")
        self._attr_name = f"{name} Last Watered"
        self._attr_unique_id = f"{entry.entry_id}_last_watered"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> datetime | None:
        return self._data.last_watered

    async def async_set_value(self, value: datetime) -> None:
        self._data.last_watered = value
        await self._data.async_save()
        self.async_write_ha_state()
