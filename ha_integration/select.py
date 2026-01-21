"""Select platform for Plants selectors."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .data import MeterLocationsData, PlantsData

OPTION_NONE = "None"
DEVICE_SOURCE_DOMAINS = ("switch",)
AUTO_WATERING_SOURCE_DOMAINS = ("valve",)
MOISTURE_DEVICE_DOMAINS = ("sensor", "number", "input_number")
HUMIDIFIER_DEVICE_DOMAINS = ("switch", "input_boolean")
HUMIDITY_DEVICE_DOMAINS = ("sensor", "number", "input_number")
AIR_TEMPERATURE_DEVICE_DOMAINS = ("sensor", "number", "input_number")


def _excluded_plants_entities(hass: HomeAssistant) -> set[str]:
    registry = er.async_get(hass)
    return {
        entry.entity_id
        for entry in registry.entities.values()
        if entry.platform == DOMAIN
    }


def _has_plug_label(state) -> bool:
    name = (state.attributes.get("friendly_name") or state.entity_id).lower()
    return "plug" in name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants select entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    entry_type = entry_data["type"]
    data = entry_data["data"]
    entities: list[SelectEntity] = []
    if entry_type == "meter_locations":
        for location_id in data.meter_locations:
            entities.append(LocationAirHumiditySelect(data, location_id))
            entities.append(LocationAirTemperatureSelect(data, location_id))
    else:
        for plant_id in data.plants:
            entities.append(PlantLightSelect(data, plant_id))
            entities.append(PlantWaterSelect(data, plant_id))
            entities.append(PlantMoistureSelect(data, plant_id))
            entities.append(PlantHumiditySelect(data, plant_id))
            entities.append(PlantAirTemperatureSelect(data, plant_id))
            entities.append(PlantHumidifierSelect(data, plant_id))
    if entities:
        async_add_entities(entities)


class PlantLightSelect(SelectEntity):
    """Select light outlet for a plant."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Grow Light Device Source"
        self._attr_unique_id = f"plant_{plant_id}_light_outlet"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        excluded = _excluded_plants_entities(self.hass)
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in DEVICE_SOURCE_DOMAINS
            and state.entity_id not in excluded
            and _has_plug_label(state)
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.plants[self._plant_id].light_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_plant_light(self._plant_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantMoistureSelect(SelectEntity):
    """Select moisture device for a plant."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Soil Moisture Device Source"
        self._attr_unique_id = f"plant_{plant_id}_moisture_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        excluded = _excluded_plants_entities(self.hass)
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in MOISTURE_DEVICE_DOMAINS
            and state.entity_id not in excluded
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.plants[self._plant_id].moisture_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_plant_moisture(self._plant_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantWaterSelect(SelectEntity):
    """Select water outlet for a plant."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Auto Watering Device Source"
        self._attr_unique_id = f"plant_{plant_id}_water_outlet"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        excluded = _excluded_plants_entities(self.hass)
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in AUTO_WATERING_SOURCE_DOMAINS
            and state.entity_id not in excluded
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.plants[self._plant_id].water_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_plant_water(self._plant_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantHumiditySelect(SelectEntity):
    """Select humidity meter for a plant."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Humidity Meter Source"
        self._attr_unique_id = f"plant_{plant_id}_humidity_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        excluded = _excluded_plants_entities(self.hass)
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in HUMIDITY_DEVICE_DOMAINS
            and state.entity_id not in excluded
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.plants[self._plant_id].humidity_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_plant_humidity(self._plant_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantHumidifierSelect(SelectEntity):
    """Select humidifier device for a plant."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Humidifier Device Source"
        self._attr_unique_id = f"plant_{plant_id}_humidifier_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        excluded = _excluded_plants_entities(self.hass)
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in HUMIDIFIER_DEVICE_DOMAINS
            and state.entity_id not in excluded
            and _has_plug_label(state)
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.plants[self._plant_id].humidifier_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_plant_humidifier(self._plant_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


class PlantAirTemperatureSelect(SelectEntity):
    """Select air temperature meter for a plant."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Temperature Meter Source"
        self._attr_unique_id = f"plant_{plant_id}_air_temperature_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        excluded = _excluded_plants_entities(self.hass)
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in AIR_TEMPERATURE_DEVICE_DOMAINS
            and state.entity_id not in excluded
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.plants[self._plant_id].air_temperature_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_plant_air_temperature(self._plant_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


class LocationAirHumiditySelect(SelectEntity):
    """Select air humidity meter for a location."""

    def __init__(self, data: MeterLocationsData, location_id: str) -> None:
        self._data = data
        self._location_id = location_id
        location = data.meter_locations[location_id]
        self._attr_name = f"{location.name} Air Humidity Meter Source"
        self._attr_unique_id = f"meter_location_{location_id}_air_humidity_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"meter_location_{location_id}")},
            name=location.name,
            manufacturer="Custom",
            model="Meter Location",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in HUMIDITY_DEVICE_DOMAINS
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.meter_locations[
            self._location_id
        ].air_humidity_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_meter_location_air_humidity(self._location_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


class LocationAirTemperatureSelect(SelectEntity):
    """Select air temperature meter for a location."""

    def __init__(self, data: MeterLocationsData, location_id: str) -> None:
        self._data = data
        self._location_id = location_id
        location = data.meter_locations[location_id]
        self._attr_name = f"{location.name} Air Temperature Meter Source"
        self._attr_unique_id = f"meter_location_{location_id}_air_temperature_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"meter_location_{location_id}")},
            name=location.name,
            manufacturer="Custom",
            model="Meter Location",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in AIR_TEMPERATURE_DEVICE_DOMAINS
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.meter_locations[
            self._location_id
        ].air_temperature_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_meter_location_air_temperature(self._location_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()
