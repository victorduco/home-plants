"""State storage for Plants."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

from .const import (
    DOMAIN,
    STORAGE_AUTO_WATERERS,
    STORAGE_GROW_LIGHTS,
    STORAGE_HUMIDIFIERS,
    STORAGE_THERMOSTATS,
    STORAGE_VERSION,
)

DEFAULT_PLANTS = ["Rose", "Tulip", "Aloe", "Basil"]


@dataclass
class Plant:
    """Persisted plant data."""

    plant_id: str
    name: str
    moisture_entity_id: str | None
    air_humidity_entity_id: str | None
    air_temperature_entity_id: str | None
    air_temperature_recommendation: str | None
    air_humidity_recommendation: str | None
    other_recommendations: str | None
    todo_list: str | None
    moisture_yellow_threshold: float | None = None
    moisture_red_threshold: float | None = None
    humidity_min: float | None = None
    humidity_max: float | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None


@dataclass
class PlantsData:
    """Persisted integration data."""

    store: Store
    plants: dict[str, Plant]
    # Migration data: populated when loading existing plants that had device refs.
    # Maps plant_id -> entity_id for each device type.
    _migrated_light_entities: dict[str, str] = field(default_factory=dict)
    _migrated_water_entities: dict[str, str] = field(default_factory=dict)
    _migrated_humidifier_entities: dict[str, str] = field(default_factory=dict)
    # Runtime entity references for cross-platform linking (not persisted).
    custom_event_entities: dict[str, Any] = field(default_factory=dict)

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "PlantsData":
        """Load plants from storage."""
        store = Store(hass, STORAGE_VERSION, DOMAIN)
        raw = await store.async_load() or {}
        plants, migrated_light, migrated_water, migrated_humidifier = cls._parse_raw(raw)
        if not plants:
            for name in DEFAULT_PLANTS:
                plant_id = str(uuid4())
                plants[plant_id] = Plant(
                    plant_id=plant_id,
                    name=name,
                    moisture_entity_id=None,
                    air_humidity_entity_id=None,
                    air_temperature_entity_id=None,
                    watering_frequency_recommendation=None,

                    air_temperature_recommendation=None,
                    air_humidity_recommendation=None,
                    other_recommendations=None,
                    todo_list=None,
                )
            data = cls(store=store, plants=plants)
            await data.async_save()
            return data
        return cls(
            store=store,
            plants=plants,
            _migrated_light_entities=migrated_light,
            _migrated_water_entities=migrated_water,
            _migrated_humidifier_entities=migrated_humidifier,
        )

    @staticmethod
    def _parse_raw(
        raw: dict,
    ) -> tuple[
        dict[str, Plant],
        dict[str, str],
        dict[str, str],
        dict[str, str],
    ]:
        plants: dict[str, Plant] = {}
        migrated_light: dict[str, str] = {}
        migrated_water: dict[str, str] = {}
        migrated_humidifier: dict[str, str] = {}
        for item in raw.get("plants", []):
            plant_id = str(item.get("id"))
            if not plant_id:
                continue
            plants[plant_id] = Plant(
                plant_id=plant_id,
                name=item.get("name") or plant_id,
                moisture_entity_id=item.get("moisture_entity_id"),
                air_humidity_entity_id=item.get("air_humidity_entity_id"),
                air_temperature_entity_id=item.get("air_temperature_entity_id"),
                air_temperature_recommendation=item.get(
                    "air_temperature_recommendation"
                ),
                air_humidity_recommendation=item.get("air_humidity_recommendation"),
                other_recommendations=item.get("other_recommendations"),
                todo_list=item.get("todo_list"),
                moisture_yellow_threshold=item.get("moisture_yellow_threshold"),
                moisture_red_threshold=item.get("moisture_red_threshold"),
                humidity_min=item.get("humidity_min"),
                humidity_max=item.get("humidity_max"),
                temperature_min=item.get("temperature_min"),
                temperature_max=item.get("temperature_max"),
            )
            # Collect legacy device refs for migration tracking.
            if item.get("light_entity_id"):
                migrated_light[plant_id] = item["light_entity_id"]
            if item.get("water_entity_id"):
                migrated_water[plant_id] = item["water_entity_id"]
            if item.get("humidifier_entity_id"):
                migrated_humidifier[plant_id] = item["humidifier_entity_id"]
        return plants, migrated_light, migrated_water, migrated_humidifier

    async def async_save(self) -> None:
        """Persist plants (without legacy device fields)."""
        payload = {
            "plants": [
                {
                    "id": plant.plant_id,
                    "name": plant.name,
                    "moisture_entity_id": plant.moisture_entity_id,
                    "air_humidity_entity_id": plant.air_humidity_entity_id,
                    "air_temperature_entity_id": plant.air_temperature_entity_id,
                    "air_temperature_recommendation": (
                        plant.air_temperature_recommendation
                    ),
                    "air_humidity_recommendation": (
                        plant.air_humidity_recommendation
                    ),
                    "other_recommendations": plant.other_recommendations,
                    "todo_list": plant.todo_list,
                    "moisture_yellow_threshold": plant.moisture_yellow_threshold,
                    "moisture_red_threshold": plant.moisture_red_threshold,
                    "humidity_min": plant.humidity_min,
                    "humidity_max": plant.humidity_max,
                    "temperature_min": plant.temperature_min,
                    "temperature_max": plant.temperature_max,
                }
                for plant in self.plants.values()
            ],
        }
        await self.store.async_save(payload)

    def add_plant(
        self,
        name: str,
        moisture_entity_id: str | None = None,
    ) -> Plant:
        """Add a new plant."""
        plant_id = str(uuid4())
        plant = Plant(
            plant_id=plant_id,
            name=name,
            moisture_entity_id=moisture_entity_id,
            air_humidity_entity_id=None,
            air_temperature_entity_id=None,
            watering_frequency_recommendation=None,
            soil_moisture_recommendation=None,
            air_temperature_recommendation=None,
            air_humidity_recommendation=None,
            other_recommendations=None,
            todo_list=None,
        )
        self.plants[plant_id] = plant
        return plant

    def remove_plant(self, plant_id: str) -> bool:
        """Remove a plant."""
        return self.plants.pop(plant_id, None) is not None

    def set_plant_moisture(self, plant_id: str, entity_id: str | None) -> None:
        """Set plant moisture entity."""
        if plant_id in self.plants:
            self.plants[plant_id].moisture_entity_id = entity_id

    def set_plant_humidity(self, plant_id: str, entity_id: str | None) -> None:
        """Set plant humidity entity."""
        if plant_id in self.plants:
            self.plants[plant_id].air_humidity_entity_id = entity_id

    def set_plant_air_temperature(
        self,
        plant_id: str,
        entity_id: str | None,
    ) -> None:
        """Set plant air temperature entity."""
        if plant_id in self.plants:
            self.plants[plant_id].air_temperature_entity_id = entity_id


@dataclass
class MeterLocation:
    """Persisted meter location data."""

    location_id: str
    name: str
    air_temperature_entity_id: str | None
    air_humidity_entity_id: str | None
    description: str | None
    comments: str | None


@dataclass
class MeterLocationsData:
    """Persisted meter location data."""

    store: Store
    meter_locations: dict[str, MeterLocation]

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "MeterLocationsData":
        """Load meter locations from storage."""
        store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_meter_locations")
        raw = await store.async_load() or {}
        meter_locations = cls._parse_raw(raw)
        return cls(store=store, meter_locations=meter_locations)

    @staticmethod
    def _parse_raw(raw: dict) -> dict[str, MeterLocation]:
        meter_locations: dict[str, MeterLocation] = {}
        for item in raw.get("meter_locations", []):
            location_id = str(item.get("id"))
            if not location_id:
                continue
            meter_locations[location_id] = MeterLocation(
                location_id=location_id,
                name=item.get("name") or location_id,
                air_temperature_entity_id=item.get("air_temperature_entity_id"),
                air_humidity_entity_id=item.get("air_humidity_entity_id"),
                description=item.get("description"),
                comments=item.get("comments"),
            )
        return meter_locations

    async def async_save(self) -> None:
        """Persist meter locations."""
        payload = {
            "meter_locations": [
                {
                    "id": location.location_id,
                    "name": location.name,
                    "air_temperature_entity_id": location.air_temperature_entity_id,
                    "air_humidity_entity_id": location.air_humidity_entity_id,
                    "description": location.description,
                    "comments": location.comments,
                }
                for location in self.meter_locations.values()
            ],
        }
        await self.store.async_save(payload)

    def add_meter_location(
        self,
        name: str,
        air_temperature_entity_id: str | None = None,
        air_humidity_entity_id: str | None = None,
        description: str | None = None,
        comments: str | None = None,
    ) -> MeterLocation:
        """Add a new meter location."""
        location_id = str(uuid4())
        location = MeterLocation(
            location_id=location_id,
            name=name,
            air_temperature_entity_id=air_temperature_entity_id,
            air_humidity_entity_id=air_humidity_entity_id,
            description=description,
            comments=comments,
        )
        self.meter_locations[location_id] = location
        return location

    def remove_meter_location(self, location_id: str) -> bool:
        """Remove a meter location."""
        return self.meter_locations.pop(location_id, None) is not None

    def set_meter_location_air_temperature(
        self,
        location_id: str,
        entity_id: str | None,
    ) -> None:
        """Set meter location air temperature entity."""
        if location_id in self.meter_locations:
            self.meter_locations[location_id].air_temperature_entity_id = entity_id

    def set_meter_location_air_humidity(
        self,
        location_id: str,
        entity_id: str | None,
    ) -> None:
        """Set meter location air humidity entity."""
        if location_id in self.meter_locations:
            self.meter_locations[location_id].air_humidity_entity_id = entity_id

    def set_meter_location_description(
        self,
        location_id: str,
        value: str | None,
    ) -> None:
        """Set meter location description."""
        if location_id in self.meter_locations:
            self.meter_locations[location_id].description = value

    def set_meter_location_comments(
        self,
        location_id: str,
        value: str | None,
    ) -> None:
        """Set meter location comments."""
        if location_id in self.meter_locations:
            self.meter_locations[location_id].comments = value


# ---------------------------------------------------------------------------
# GrowLight
# ---------------------------------------------------------------------------


@dataclass
class GrowLight:
    """Persisted grow light data."""

    grow_light_id: str
    name: str
    light_entity_id: str | None
    nearby_plant_ids: list[str]


@dataclass
class GrowLightsData:
    """Persisted grow lights data."""

    store: Store
    grow_lights: dict[str, GrowLight]

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "GrowLightsData":
        """Load grow lights from storage."""
        store = Store(hass, STORAGE_VERSION, STORAGE_GROW_LIGHTS)
        raw = await store.async_load() or {}
        grow_lights = cls._parse_raw(raw)
        return cls(store=store, grow_lights=grow_lights)

    @staticmethod
    def _parse_raw(raw: dict) -> dict[str, GrowLight]:
        grow_lights: dict[str, GrowLight] = {}
        for item in raw.get("grow_lights", []):
            grow_light_id = str(item.get("id"))
            if not grow_light_id:
                continue
            grow_lights[grow_light_id] = GrowLight(
                grow_light_id=grow_light_id,
                name=item.get("name") or grow_light_id,
                light_entity_id=item.get("light_entity_id"),
                nearby_plant_ids=list(item.get("nearby_plant_ids") or []),
            )
        return grow_lights

    async def async_save(self) -> None:
        """Persist grow lights."""
        payload = {
            "grow_lights": [
                {
                    "id": gl.grow_light_id,
                    "name": gl.name,
                    "light_entity_id": gl.light_entity_id,
                    "nearby_plant_ids": gl.nearby_plant_ids,
                }
                for gl in self.grow_lights.values()
            ],
        }
        await self.store.async_save(payload)

    def add_grow_light(
        self,
        name: str,
        light_entity_id: str | None = None,
    ) -> GrowLight:
        """Add a new grow light."""
        grow_light_id = str(uuid4())
        gl = GrowLight(
            grow_light_id=grow_light_id,
            name=name,
            light_entity_id=light_entity_id,
            nearby_plant_ids=[],
        )
        self.grow_lights[grow_light_id] = gl
        return gl

    def remove_grow_light(self, grow_light_id: str) -> bool:
        """Remove a grow light."""
        return self.grow_lights.pop(grow_light_id, None) is not None

    def set_grow_light_source(
        self,
        grow_light_id: str,
        entity_id: str | None,
    ) -> None:
        """Set grow light source entity."""
        if grow_light_id in self.grow_lights:
            self.grow_lights[grow_light_id].light_entity_id = entity_id

    def set_grow_light_nearby_plants(
        self,
        grow_light_id: str,
        plant_ids: list[str],
    ) -> None:
        """Set nearby plant IDs for a grow light."""
        if grow_light_id in self.grow_lights:
            self.grow_lights[grow_light_id].nearby_plant_ids = plant_ids


# ---------------------------------------------------------------------------
# HumidifierDevice
# ---------------------------------------------------------------------------


@dataclass
class HumidifierDevice:
    """Persisted humidifier device data."""

    humidifier_id: str
    name: str
    humidifier_entity_id: str | None
    nearby_plant_ids: list[str]


@dataclass
class HumidifiersData:
    """Persisted humidifiers data."""

    store: Store
    humidifiers: dict[str, HumidifierDevice]

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "HumidifiersData":
        """Load humidifiers from storage."""
        store = Store(hass, STORAGE_VERSION, STORAGE_HUMIDIFIERS)
        raw = await store.async_load() or {}
        humidifiers = cls._parse_raw(raw)
        return cls(store=store, humidifiers=humidifiers)

    @staticmethod
    def _parse_raw(raw: dict) -> dict[str, HumidifierDevice]:
        humidifiers: dict[str, HumidifierDevice] = {}
        for item in raw.get("humidifiers", []):
            humidifier_id = str(item.get("id"))
            if not humidifier_id:
                continue
            humidifiers[humidifier_id] = HumidifierDevice(
                humidifier_id=humidifier_id,
                name=item.get("name") or humidifier_id,
                humidifier_entity_id=item.get("humidifier_entity_id"),
                nearby_plant_ids=list(item.get("nearby_plant_ids") or []),
            )
        return humidifiers

    async def async_save(self) -> None:
        """Persist humidifiers."""
        payload = {
            "humidifiers": [
                {
                    "id": hd.humidifier_id,
                    "name": hd.name,
                    "humidifier_entity_id": hd.humidifier_entity_id,
                    "nearby_plant_ids": hd.nearby_plant_ids,
                }
                for hd in self.humidifiers.values()
            ],
        }
        await self.store.async_save(payload)

    def add_humidifier(
        self,
        name: str,
        humidifier_entity_id: str | None = None,
    ) -> HumidifierDevice:
        """Add a new humidifier device."""
        humidifier_id = str(uuid4())
        hd = HumidifierDevice(
            humidifier_id=humidifier_id,
            name=name,
            humidifier_entity_id=humidifier_entity_id,
            nearby_plant_ids=[],
        )
        self.humidifiers[humidifier_id] = hd
        return hd

    def remove_humidifier(self, humidifier_id: str) -> bool:
        """Remove a humidifier device."""
        return self.humidifiers.pop(humidifier_id, None) is not None

    def set_humidifier_source(
        self,
        humidifier_id: str,
        entity_id: str | None,
    ) -> None:
        """Set humidifier source entity."""
        if humidifier_id in self.humidifiers:
            self.humidifiers[humidifier_id].humidifier_entity_id = entity_id

    def set_humidifier_nearby_plants(
        self,
        humidifier_id: str,
        plant_ids: list[str],
    ) -> None:
        """Set nearby plant IDs for a humidifier."""
        if humidifier_id in self.humidifiers:
            self.humidifiers[humidifier_id].nearby_plant_ids = plant_ids


# ---------------------------------------------------------------------------
# Thermostat
# ---------------------------------------------------------------------------


@dataclass
class ThermostatDevice:
    """Persisted thermostat device data."""

    thermostat_id: str
    name: str
    climate_entity_id: str | None


@dataclass
class ThermostatsData:
    """Persisted thermostats data."""

    store: Store
    thermostats: dict[str, ThermostatDevice]

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "ThermostatsData":
        store = Store(hass, STORAGE_VERSION, STORAGE_THERMOSTATS)
        raw = await store.async_load() or {}
        thermostats = cls._parse_raw(raw)
        return cls(store=store, thermostats=thermostats)

    @staticmethod
    def _parse_raw(raw: dict) -> dict[str, ThermostatDevice]:
        thermostats: dict[str, ThermostatDevice] = {}
        for item in raw.get("thermostats", []):
            thermostat_id = str(item.get("id"))
            if not thermostat_id:
                continue
            thermostats[thermostat_id] = ThermostatDevice(
                thermostat_id=thermostat_id,
                name=item.get("name") or thermostat_id,
                climate_entity_id=item.get("climate_entity_id"),
            )
        return thermostats

    async def async_save(self) -> None:
        payload = {
            "thermostats": [
                {
                    "id": td.thermostat_id,
                    "name": td.name,
                    "climate_entity_id": td.climate_entity_id,
                }
                for td in self.thermostats.values()
            ],
        }
        await self.store.async_save(payload)

    def add_thermostat(
        self,
        name: str,
        climate_entity_id: str | None = None,
    ) -> ThermostatDevice:
        thermostat_id = str(uuid4())
        td = ThermostatDevice(
            thermostat_id=thermostat_id,
            name=name,
            climate_entity_id=climate_entity_id,
        )
        self.thermostats[thermostat_id] = td
        return td

    def remove_thermostat(self, thermostat_id: str) -> bool:
        return self.thermostats.pop(thermostat_id, None) is not None

    def set_thermostat_entity(
        self,
        thermostat_id: str,
        entity_id: str | None,
    ) -> None:
        if thermostat_id in self.thermostats:
            self.thermostats[thermostat_id].climate_entity_id = entity_id


# ---------------------------------------------------------------------------
# AutoWaterer
# ---------------------------------------------------------------------------


@dataclass
class AutoWaterer:
    """Persisted auto waterer data."""

    waterer_id: str
    name: str
    water_entity_id: str | None
    plant_ids: list[str]


@dataclass
class AutoWaterersData:
    """Persisted auto waterers data."""

    store: Store
    auto_waterers: dict[str, AutoWaterer]

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "AutoWaterersData":
        """Load auto waterers from storage."""
        store = Store(hass, STORAGE_VERSION, STORAGE_AUTO_WATERERS)
        raw = await store.async_load() or {}
        auto_waterers = cls._parse_raw(raw)
        return cls(store=store, auto_waterers=auto_waterers)

    @staticmethod
    def _parse_raw(raw: dict) -> dict[str, AutoWaterer]:
        auto_waterers: dict[str, AutoWaterer] = {}
        for item in raw.get("auto_waterers", []):
            waterer_id = str(item.get("id"))
            if not waterer_id:
                continue
            auto_waterers[waterer_id] = AutoWaterer(
                waterer_id=waterer_id,
                name=item.get("name") or waterer_id,
                water_entity_id=item.get("water_entity_id"),
                plant_ids=list(item.get("plant_ids") or []),
            )
        return auto_waterers

    async def async_save(self) -> None:
        """Persist auto waterers."""
        payload = {
            "auto_waterers": [
                {
                    "id": aw.waterer_id,
                    "name": aw.name,
                    "water_entity_id": aw.water_entity_id,
                    "plant_ids": aw.plant_ids,
                }
                for aw in self.auto_waterers.values()
            ],
        }
        await self.store.async_save(payload)

    def add_auto_waterer(
        self,
        name: str,
        water_entity_id: str | None = None,
    ) -> AutoWaterer:
        """Add a new auto waterer."""
        waterer_id = str(uuid4())
        aw = AutoWaterer(
            waterer_id=waterer_id,
            name=name,
            water_entity_id=water_entity_id,
            plant_ids=[],
        )
        self.auto_waterers[waterer_id] = aw
        return aw

    def remove_auto_waterer(self, waterer_id: str) -> bool:
        """Remove an auto waterer."""
        return self.auto_waterers.pop(waterer_id, None) is not None

    def set_auto_waterer_source(
        self,
        waterer_id: str,
        entity_id: str | None,
    ) -> None:
        """Set auto waterer source entity."""
        if waterer_id in self.auto_waterers:
            self.auto_waterers[waterer_id].water_entity_id = entity_id

    def set_auto_waterer_plants(
        self,
        waterer_id: str,
        plant_ids: list[str],
    ) -> None:
        """Set plant IDs for an auto waterer."""
        if waterer_id in self.auto_waterers:
            self.auto_waterers[waterer_id].plant_ids = plant_ids
