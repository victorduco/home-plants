"""Select platform for Plants selectors."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .data import (
    AutoWaterersData,
    GrowLightsData,
    HumidifiersData,
    MeterLocationsData,
    PlantsData,
)

OPTION_NONE = "None"
DEVICE_SOURCE_DOMAINS = ("switch",)
MOISTURE_DEVICE_DOMAINS = ("sensor", "number", "input_number")
HUMIDITY_DEVICE_DOMAINS = ("sensor", "number", "input_number")
AIR_TEMPERATURE_DEVICE_DOMAINS = ("sensor", "number", "input_number")
WATER_SOURCE_DOMAINS = ("valve", "switch")


def _is_plants_entity(hass: HomeAssistant, entity_id: str) -> bool:
    """Return whether one source candidate belongs to Plants in O(1)."""
    entry = er.async_get(hass).async_get(entity_id)
    return entry is not None and entry.platform == DOMAIN


def _has_plug_label(state) -> bool:
    name = (state.attributes.get("friendly_name") or state.entity_id).lower()
    return "plug" in name


def _has_moisture_label(state) -> bool:
    name = (state.attributes.get("friendly_name") or state.entity_id).lower()
    return "moisture" in name


def _has_temperature_label(state) -> bool:
    name = (state.attributes.get("friendly_name") or state.entity_id).lower()
    return "temperature" in name


def _has_humidity_label(state) -> bool:
    name = (state.attributes.get("friendly_name") or state.entity_id).lower()
    return "humidity" in name


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
    elif entry_type == "grow_lights":
        for grow_light_id in data.grow_lights:
            entities.append(GrowLightSourceSelect(data, grow_light_id))
            for slot in range(20):
                entities.append(GrowLightPlantSlotSelect(data, grow_light_id, slot))
    elif entry_type == "humidifiers":
        for humidifier_id in data.humidifiers:
            entities.append(HumidifierSourceSelect(data, humidifier_id))
            for slot in range(20):
                entities.append(HumidifierPlantSlotSelect(data, humidifier_id, slot))
    elif entry_type == "auto_waterers":
        for waterer_id in data.auto_waterers:
            entities.append(AutoWatererSourceSelect(data, waterer_id))
            for slot in range(20):
                entities.append(AutoWatererPlantSlotSelect(data, waterer_id, slot))
    elif entry_type == "plants":
        for plant_id in data.plants:
            entities.append(PlantMoistureSelect(data, plant_id))
            entities.append(PlantHumiditySelect(data, plant_id))
            entities.append(PlantAirTemperatureSelect(data, plant_id))

    if entities:
        async_add_entities(entities)


# ---------------------------------------------------------------------------
# Plant selects (sensor sources only)
# ---------------------------------------------------------------------------


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
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in MOISTURE_DEVICE_DOMAINS
            and _has_moisture_label(state)
            and not _is_plants_entity(self.hass, state.entity_id)
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
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in HUMIDITY_DEVICE_DOMAINS
            and _has_humidity_label(state)
            and not _is_plants_entity(self.hass, state.entity_id)
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.plants[self._plant_id].air_humidity_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_plant_humidity(self._plant_id, entity_id)
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
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in AIR_TEMPERATURE_DEVICE_DOMAINS
            and _has_temperature_label(state)
            and not _is_plants_entity(self.hass, state.entity_id)
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


# ---------------------------------------------------------------------------
# GrowLight selects
# ---------------------------------------------------------------------------


class GrowLightSourceSelect(SelectEntity):
    """Select grow light source entity."""

    def __init__(self, data: GrowLightsData, grow_light_id: str) -> None:
        self._data = data
        self._grow_light_id = grow_light_id
        gl = data.grow_lights[grow_light_id]
        self._attr_name = f"{gl.name} Source"
        self._attr_unique_id = f"grow_light_{grow_light_id}_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"grow_light_{grow_light_id}")},
            name=gl.name,
            manufacturer="Custom",
            model="Grow Light",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in DEVICE_SOURCE_DOMAINS
            and _has_plug_label(state)
            and not _is_plants_entity(self.hass, state.entity_id)
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.grow_lights[self._grow_light_id].light_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_grow_light_source(self._grow_light_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Humidifier selects
# ---------------------------------------------------------------------------


class HumidifierSourceSelect(SelectEntity):
    """Select humidifier source entity."""

    def __init__(self, data: HumidifiersData, humidifier_id: str) -> None:
        self._data = data
        self._humidifier_id = humidifier_id
        hd = data.humidifiers[humidifier_id]
        self._attr_name = f"{hd.name} Source"
        self._attr_unique_id = f"humidifier_{humidifier_id}_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"humidifier_{humidifier_id}")},
            name=hd.name,
            manufacturer="Custom",
            model="Humidifier",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in DEVICE_SOURCE_DOMAINS
            and _has_plug_label(state)
            and not _is_plants_entity(self.hass, state.entity_id)
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.humidifiers[self._humidifier_id].humidifier_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_humidifier_source(self._humidifier_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# AutoWaterer selects
# ---------------------------------------------------------------------------


class AutoWatererSourceSelect(SelectEntity):
    """Select auto waterer valve/switch source entity."""

    def __init__(self, data: AutoWaterersData, waterer_id: str) -> None:
        self._data = data
        self._waterer_id = waterer_id
        aw = data.auto_waterers[waterer_id]
        self._attr_name = f"{aw.name} Source"
        self._attr_unique_id = f"auto_waterer_{waterer_id}_source"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"auto_waterer_{waterer_id}")},
            name=aw.name,
            manufacturer="Custom",
            model="Auto Waterer",
        )
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        options = [
            state.entity_id
            for state in self.hass.states.async_all()
            if state.domain in WATER_SOURCE_DOMAINS
            and not _is_plants_entity(self.hass, state.entity_id)
        ]
        options.sort()
        return [OPTION_NONE, *options]

    @property
    def current_option(self) -> str | None:
        entity_id = self._data.auto_waterers[self._waterer_id].water_entity_id
        return entity_id or OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        entity_id = None if option == OPTION_NONE else option
        self._data.set_auto_waterer_source(self._waterer_id, entity_id)
        await self._data.async_save()
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Plant slot selects (20 slots per device)
# ---------------------------------------------------------------------------


def _plant_options(hass: HomeAssistant) -> list[str]:
    """Return [OPTION_NONE, plant_name, ...] sorted by name."""
    # Read from hass.data plants entry
    from .const import DOMAIN as _DOMAIN
    plants_data = None
    for entry_data in hass.data.get(_DOMAIN, {}).values():
        if entry_data.get("type") == "plants":
            plants_data = entry_data["data"]
            break
    if plants_data is None:
        return [OPTION_NONE]
    names = sorted(p.name for p in plants_data.plants.values())
    return [OPTION_NONE, *names]


def _name_to_id(hass: HomeAssistant, name: str) -> str | None:
    from .const import DOMAIN as _DOMAIN
    for entry_data in hass.data.get(_DOMAIN, {}).values():
        if entry_data.get("type") == "plants":
            for p in entry_data["data"].plants.values():
                if p.name == name:
                    return p.plant_id
    return None


def _id_to_name(hass: HomeAssistant, plant_id: str) -> str | None:
    from .const import DOMAIN as _DOMAIN
    for entry_data in hass.data.get(_DOMAIN, {}).values():
        if entry_data.get("type") == "plants":
            p = entry_data["data"].plants.get(plant_id)
            return p.name if p else None
    return None


class GrowLightPlantSlotSelect(SelectEntity):
    """One plant slot (0-based) for a grow light."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, data: GrowLightsData, grow_light_id: str, slot: int) -> None:
        self._data = data
        self._grow_light_id = grow_light_id
        self._slot = slot
        gl = data.grow_lights[grow_light_id]
        self._attr_name = f"Plant {slot + 1}"
        self._attr_unique_id = f"grow_light_{grow_light_id}_plant_slot_{slot}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"grow_light_{grow_light_id}")},
            name=gl.name,
            manufacturer="Custom",
            model="Grow Light",
        )

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        return _plant_options(self.hass)

    @property
    def current_option(self) -> str:
        ids = self._data.grow_lights[self._grow_light_id].nearby_plant_ids
        if self._slot < len(ids):
            name = _id_to_name(self.hass, ids[self._slot]) if self.hass else None
            return name or OPTION_NONE
        return OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        ids = list(self._data.grow_lights[self._grow_light_id].nearby_plant_ids)
        # Extend list if needed
        while len(ids) <= self._slot:
            ids.append("")
        if option == OPTION_NONE:
            ids[self._slot] = ""
        else:
            plant_id = _name_to_id(self.hass, option) if self.hass else None
            ids[self._slot] = plant_id or ""
        # Strip trailing empty slots
        while ids and not ids[-1]:
            ids.pop()
        self._data.set_grow_light_nearby_plants(self._grow_light_id, ids)
        await self._data.async_save()
        self.async_write_ha_state()


class HumidifierPlantSlotSelect(SelectEntity):
    """One plant slot (0-based) for a humidifier."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, data: HumidifiersData, humidifier_id: str, slot: int) -> None:
        self._data = data
        self._humidifier_id = humidifier_id
        self._slot = slot
        hd = data.humidifiers[humidifier_id]
        self._attr_name = f"Plant {slot + 1}"
        self._attr_unique_id = f"humidifier_{humidifier_id}_plant_slot_{slot}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"humidifier_{humidifier_id}")},
            name=hd.name,
            manufacturer="Custom",
            model="Humidifier",
        )

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        return _plant_options(self.hass)

    @property
    def current_option(self) -> str:
        ids = self._data.humidifiers[self._humidifier_id].nearby_plant_ids
        if self._slot < len(ids):
            name = _id_to_name(self.hass, ids[self._slot]) if self.hass else None
            return name or OPTION_NONE
        return OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        ids = list(self._data.humidifiers[self._humidifier_id].nearby_plant_ids)
        while len(ids) <= self._slot:
            ids.append("")
        if option == OPTION_NONE:
            ids[self._slot] = ""
        else:
            plant_id = _name_to_id(self.hass, option) if self.hass else None
            ids[self._slot] = plant_id or ""
        while ids and not ids[-1]:
            ids.pop()
        self._data.set_humidifier_nearby_plants(self._humidifier_id, ids)
        await self._data.async_save()
        self.async_write_ha_state()


class AutoWatererPlantSlotSelect(SelectEntity):
    """One plant slot (0-based) for an auto waterer."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, data: AutoWaterersData, waterer_id: str, slot: int) -> None:
        self._data = data
        self._waterer_id = waterer_id
        self._slot = slot
        aw = data.auto_waterers[waterer_id]
        self._attr_name = f"Plant {slot + 1}"
        self._attr_unique_id = f"auto_waterer_{waterer_id}_plant_slot_{slot}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"auto_waterer_{waterer_id}")},
            name=aw.name,
            manufacturer="Custom",
            model="Auto Waterer",
        )

    @property
    def options(self) -> list[str]:
        if not self.hass:
            return [OPTION_NONE]
        return _plant_options(self.hass)

    @property
    def current_option(self) -> str:
        ids = self._data.auto_waterers[self._waterer_id].plant_ids
        if self._slot < len(ids):
            name = _id_to_name(self.hass, ids[self._slot]) if self.hass else None
            return name or OPTION_NONE
        return OPTION_NONE

    async def async_select_option(self, option: str) -> None:
        ids = list(self._data.auto_waterers[self._waterer_id].plant_ids)
        while len(ids) <= self._slot:
            ids.append("")
        if option == OPTION_NONE:
            ids[self._slot] = ""
        else:
            plant_id = _name_to_id(self.hass, option) if self.hass else None
            ids[self._slot] = plant_id or ""
        while ids and not ids[-1]:
            ids.pop()
        self._data.set_auto_waterer_plants(self._waterer_id, ids)
        await self._data.async_save()
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# MeterLocation selects (unchanged)
# ---------------------------------------------------------------------------


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
            and _has_humidity_label(state)
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
            and _has_temperature_label(state)
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
