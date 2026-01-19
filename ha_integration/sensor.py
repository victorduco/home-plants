"""Sensor platform for Plants."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
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
    """Set up Plants sensors from a config entry."""
    data: PlantData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PlantStatusSensor(entry, data)])


class PlantStatusSensor(SensorEntity):
    """Simple sensor showing plant status."""

    _attr_native_value = "ready"

    def __init__(self, entry: ConfigEntry, data: PlantData) -> None:
        self._entry = entry
        self._data = data
        name = entry.data.get("name", "Plant")
        self._attr_name = f"{name} Status"
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="Custom",
            model="Plant",
        )
