"""Number platform for Plants."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DEFAULT_LAMP_POSITION_X,
    DEFAULT_LAMP_POSITION_Y,
    DEFAULT_LOCATION_X,
    DEFAULT_LOCATION_Y,
    DEFAULT_SOIL_MOISTURE,
    DOMAIN,
)
from .data import PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants number entities from a config entry."""
    data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
    plant_entities: list[NumberEntity] = []
    for plant_id in data.plants:
        plant_entities.extend(
            [
                PlantSoilMoistureNumber(entry, data, plant_id),
                PlantLocationXNumber(entry, data, plant_id),
                PlantLocationYNumber(entry, data, plant_id),
            ]
        )
    lamp_entities: list[NumberEntity] = []
    for lamp_id in data.lamps:
        lamp_entities.extend(
            [
                LampPositionXNumber(entry, data, lamp_id),
                LampPositionYNumber(entry, data, lamp_id),
            ]
        )
    async_add_entities(plant_entities + lamp_entities)


class PlantNumberBase(NumberEntity):
    """Base class for plant number entities."""

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, plant_id: str
    ) -> None:
        self._entry = entry
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
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

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, plant_id: str
    ) -> None:
        super().__init__(entry, data, plant_id)
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Soil Moisture"
        self._attr_unique_id = f"{entry.entry_id}_plant_{plant_id}_soil_moisture"
        if plant.soil_moisture is None:
            plant.soil_moisture = DEFAULT_SOIL_MOISTURE

    @property
    def native_value(self) -> float:
        return float(self._data.plants[self._plant_id].soil_moisture)

    async def async_set_value(self, value: float) -> None:
        self._data.plants[self._plant_id].soil_moisture = float(value)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantLocationXNumber(PlantNumberBase):
    """Plant X coordinate."""

    _attr_native_min_value = -1000.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 0.1

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, plant_id: str
    ) -> None:
        super().__init__(entry, data, plant_id)
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Location X"
        self._attr_unique_id = f"{entry.entry_id}_plant_{plant_id}_location_x"
        if plant.location_x is None:
            plant.location_x = DEFAULT_LOCATION_X

    @property
    def native_value(self) -> float:
        return float(self._data.plants[self._plant_id].location_x)

    async def async_set_value(self, value: float) -> None:
        self._data.plants[self._plant_id].location_x = float(value)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantLocationYNumber(PlantNumberBase):
    """Plant Y coordinate."""

    _attr_native_min_value = -1000.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 0.1

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, plant_id: str
    ) -> None:
        super().__init__(entry, data, plant_id)
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Location Y"
        self._attr_unique_id = f"{entry.entry_id}_plant_{plant_id}_location_y"
        if plant.location_y is None:
            plant.location_y = DEFAULT_LOCATION_Y

    @property
    def native_value(self) -> float:
        return float(self._data.plants[self._plant_id].location_y)

    async def async_set_value(self, value: float) -> None:
        self._data.plants[self._plant_id].location_y = float(value)
        await self._data.async_save()
        self.async_write_ha_state()


class LampNumberBase(NumberEntity):
    """Base class for lamp number entities."""

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, lamp_id: str
    ) -> None:
        self._entry = entry
        self._data = data
        self._lamp_id = lamp_id
        lamp = data.lamps[lamp_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"lamp_{lamp_id}")},
            name=lamp.name,
            manufacturer="Custom",
            model="Grow Lamp",
        )


class LampPositionXNumber(LampNumberBase):
    """Lamp X position."""

    _attr_native_min_value = -1000.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 0.1

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, lamp_id: str
    ) -> None:
        super().__init__(entry, data, lamp_id)
        lamp = data.lamps[lamp_id]
        self._attr_name = f"{lamp.name} Position X"
        self._attr_unique_id = f"{entry.entry_id}_lamp_{lamp_id}_position_x"
        if lamp.position_x is None:
            lamp.position_x = DEFAULT_LAMP_POSITION_X

    @property
    def native_value(self) -> float:
        return float(self._data.lamps[self._lamp_id].position_x)

    async def async_set_value(self, value: float) -> None:
        self._data.lamps[self._lamp_id].position_x = float(value)
        await self._data.async_save()
        self.async_write_ha_state()


class LampPositionYNumber(LampNumberBase):
    """Lamp Y position."""

    _attr_native_min_value = -1000.0
    _attr_native_max_value = 1000.0
    _attr_native_step = 0.1

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, lamp_id: str
    ) -> None:
        super().__init__(entry, data, lamp_id)
        lamp = data.lamps[lamp_id]
        self._attr_name = f"{lamp.name} Position Y"
        self._attr_unique_id = f"{entry.entry_id}_lamp_{lamp_id}_position_y"
        if lamp.position_y is None:
            lamp.position_y = DEFAULT_LAMP_POSITION_Y

    @property
    def native_value(self) -> float:
        return float(self._data.lamps[self._lamp_id].position_y)

    async def async_set_value(self, value: float) -> None:
        self._data.lamps[self._lamp_id].position_y = float(value)
        await self._data.async_save()
        self.async_write_ha_state()
