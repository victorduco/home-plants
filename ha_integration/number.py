"""Number platform for Plants."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    DEFAULT_LOCATION_X,
    DEFAULT_LOCATION_Y,
    DEFAULT_SOIL_MOISTURE,
)
from .data import PlantData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants number entities from a config entry."""
    data: PlantData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PlantSoilMoistureNumber(entry, data),
            PlantLocationXNumber(entry, data),
            PlantLocationYNumber(entry, data),
        ]
    )


class PlantNumberBase(NumberEntity):
    """Base class for plant number entities."""

    def __init__(self, entry: ConfigEntry, data: PlantData) -> None:
        self._entry = entry
        self._data = data
        name = entry.data.get("name", "Plant")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=name,
            manufacturer="Custom",
            model="Plant",
        )


class PlantSoilMoistureNumber(PlantNumberBase):
    """Soil moisture percentage."""

    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = NumberDeviceClass.HUMIDITY

    def __init__(self, entry: ConfigEntry, data: PlantData) -> None:
        super().__init__(entry, data)
        name = entry.data.get("name", "Plant")
        self._attr_name = f"{name} Soil Moisture"
        self._attr_unique_id = f"{entry.entry_id}_soil_moisture"
        if data.soil_moisture is None:
            data.soil_moisture = DEFAULT_SOIL_MOISTURE

    @property
    def native_value(self) -> float:
        return float(self._data.soil_moisture)

    async def async_set_value(self, value: float) -> None:
        self._data.soil_moisture = float(value)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantLocationXNumber(PlantNumberBase):
    """Plant X coordinate."""

    _attr_native_min_value = -1000.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 0.1

    def __init__(self, entry: ConfigEntry, data: PlantData) -> None:
        super().__init__(entry, data)
        name = entry.data.get("name", "Plant")
        self._attr_name = f"{name} Location X"
        self._attr_unique_id = f"{entry.entry_id}_location_x"
        if data.location_x is None:
            data.location_x = DEFAULT_LOCATION_X

    @property
    def native_value(self) -> float:
        return float(self._data.location_x)

    async def async_set_value(self, value: float) -> None:
        self._data.location_x = float(value)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantLocationYNumber(PlantNumberBase):
    """Plant Y coordinate."""

    _attr_native_min_value = -1000.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 0.1

    def __init__(self, entry: ConfigEntry, data: PlantData) -> None:
        super().__init__(entry, data)
        name = entry.data.get("name", "Plant")
        self._attr_name = f"{name} Location Y"
        self._attr_unique_id = f"{entry.entry_id}_location_y"
        if data.location_y is None:
            data.location_y = DEFAULT_LOCATION_Y

    @property
    def native_value(self) -> float:
        return float(self._data.location_y)

    async def async_set_value(self, value: float) -> None:
        self._data.location_y = float(value)
        await self._data.async_save()
        self.async_write_ha_state()
