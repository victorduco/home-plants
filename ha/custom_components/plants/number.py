"""Number platform for Plants — soil moisture thresholds."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .data import PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    if entry_data["type"] != "plants":
        return
    data: PlantsData = entry_data["data"]
    entities = []
    for plant_id in data.plants:
        entities.append(PlantMoistureYellowThreshold(data, plant_id))
        entities.append(PlantMoistureRedThreshold(data, plant_id))
        entities.append(PlantHumidityMin(data, plant_id))
        entities.append(PlantHumidityMax(data, plant_id))
        entities.append(PlantTemperatureMin(data, plant_id))
        entities.append(PlantTemperatureMax(data, plant_id))
    if entities:
        async_add_entities(entities)


class PlantMoistureYellowThreshold(NumberEntity):
    """Yellow (caution) threshold for soil moisture gauge."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Soil Moisture Yellow Threshold"
        self._attr_unique_id = f"plant_{plant_id}_moisture_yellow_threshold"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> float:
        return self._data.plants[self._plant_id].moisture_yellow_threshold or 30.0

    async def async_set_native_value(self, value: float) -> None:
        self._data.plants[self._plant_id].moisture_yellow_threshold = value
        await self._data.async_save()
        self.async_write_ha_state()


class PlantMoistureRedThreshold(NumberEntity):
    """Red (critical) threshold for soil moisture gauge."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Soil Moisture Red Threshold"
        self._attr_unique_id = f"plant_{plant_id}_moisture_red_threshold"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> float:
        return self._data.plants[self._plant_id].moisture_red_threshold or 15.0

    async def async_set_native_value(self, value: float) -> None:
        self._data.plants[self._plant_id].moisture_red_threshold = value
        await self._data.async_save()
        self.async_write_ha_state()


class PlantHumidityMin(NumberEntity):
    """Minimum recommended air humidity for a plant."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Humidity Min"
        self._attr_unique_id = f"plant_{plant_id}_humidity_min"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> float:
        return self._data.plants[self._plant_id].humidity_min or 40.0

    async def async_set_native_value(self, value: float) -> None:
        self._data.plants[self._plant_id].humidity_min = value
        await self._data.async_save()
        self.async_write_ha_state()


class PlantHumidityMax(NumberEntity):
    """Maximum recommended air humidity for a plant."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Humidity Max"
        self._attr_unique_id = f"plant_{plant_id}_humidity_max"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> float:
        return self._data.plants[self._plant_id].humidity_max or 70.0

    async def async_set_native_value(self, value: float) -> None:
        self._data.plants[self._plant_id].humidity_max = value
        await self._data.async_save()
        self.async_write_ha_state()


class PlantTemperatureMin(NumberEntity):
    """Minimum recommended air temperature for a plant."""

    _attr_native_min_value = 32
    _attr_native_max_value = 120
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "°F"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Temperature Min"
        self._attr_unique_id = f"plant_{plant_id}_temperature_min"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> float:
        return self._data.plants[self._plant_id].temperature_min or 60.0

    async def async_set_native_value(self, value: float) -> None:
        self._data.plants[self._plant_id].temperature_min = value
        await self._data.async_save()
        self.async_write_ha_state()


class PlantTemperatureMax(NumberEntity):
    """Maximum recommended air temperature for a plant."""

    _attr_native_min_value = 32
    _attr_native_max_value = 120
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "°F"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Temperature Max"
        self._attr_unique_id = f"plant_{plant_id}_temperature_max"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> float:
        return self._data.plants[self._plant_id].temperature_max or 85.0

    async def async_set_native_value(self, value: float) -> None:
        self._data.plants[self._plant_id].temperature_max = value
        await self._data.async_save()
        self.async_write_ha_state()
