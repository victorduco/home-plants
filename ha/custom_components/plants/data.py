"""State storage for Plants."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION

DEFAULT_PLANTS = ["Rose", "Tulip", "Aloe", "Basil"]


@dataclass
class Plant:
    """Persisted plant data."""

    plant_id: str
    name: str
    moisture_entity_id: str | None
    humidity_entity_id: str | None
    air_temperature_entity_id: str | None
    light_entity_id: str | None
    water_entity_id: str | None
    humidifier_entity_id: str | None
    watering_frequency_recommendation: str | None
    soil_moisture_recommendation: str | None
    air_temperature_recommendation: str | None
    air_humidity_recommendation: str | None
    other_recommendations: str | None
    todo_list: str | None


@dataclass
class PlantsData:
    """Persisted integration data."""

    store: Store
    plants: dict[str, Plant]

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "PlantsData":
        """Load plants from storage."""
        store = Store(hass, STORAGE_VERSION, DOMAIN)
        raw = await store.async_load() or {}
        plants = cls._parse_raw(raw)
        if not plants:
            for name in DEFAULT_PLANTS:
                plant_id = str(uuid4())
                plants[plant_id] = Plant(
                    plant_id=plant_id,
                    name=name,
                    moisture_entity_id=None,
                    humidity_entity_id=None,
                    air_temperature_entity_id=None,
                    light_entity_id=None,
                    water_entity_id=None,
                    humidifier_entity_id=None,
                    watering_frequency_recommendation=None,
                    soil_moisture_recommendation=None,
                    air_temperature_recommendation=None,
                    air_humidity_recommendation=None,
                    other_recommendations=None,
                    todo_list=None,
                )
            data = cls(store=store, plants=plants)
            await data.async_save()
            return data
        return cls(store=store, plants=plants)

    @staticmethod
    def _parse_raw(raw: dict) -> dict[str, Plant]:
        plants: dict[str, Plant] = {}
        for item in raw.get("plants", []):
            plant_id = str(item.get("id"))
            if not plant_id:
                continue
            plants[plant_id] = Plant(
                plant_id=plant_id,
                name=item.get("name") or plant_id,
                moisture_entity_id=item.get("moisture_entity_id"),
                humidity_entity_id=item.get("humidity_entity_id"),
                air_temperature_entity_id=item.get("air_temperature_entity_id"),
                light_entity_id=item.get("light_entity_id"),
                water_entity_id=item.get("water_entity_id"),
                humidifier_entity_id=item.get("humidifier_entity_id"),
                watering_frequency_recommendation=item.get(
                    "watering_frequency_recommendation"
                ),
                soil_moisture_recommendation=item.get(
                    "soil_moisture_recommendation"
                ),
                air_temperature_recommendation=item.get(
                    "air_temperature_recommendation"
                ),
                air_humidity_recommendation=item.get("air_humidity_recommendation"),
                other_recommendations=item.get("other_recommendations"),
                todo_list=item.get("todo_list"),
            )
        return plants

    async def async_save(self) -> None:
        """Persist plants."""
        payload = {
            "plants": [
                {
                    "id": plant.plant_id,
                    "name": plant.name,
                    "moisture_entity_id": plant.moisture_entity_id,
                    "humidity_entity_id": plant.humidity_entity_id,
                    "air_temperature_entity_id": plant.air_temperature_entity_id,
                    "light_entity_id": plant.light_entity_id,
                    "water_entity_id": plant.water_entity_id,
                    "humidifier_entity_id": plant.humidifier_entity_id,
                    "watering_frequency_recommendation": (
                        plant.watering_frequency_recommendation
                    ),
                    "soil_moisture_recommendation": (
                        plant.soil_moisture_recommendation
                    ),
                    "air_temperature_recommendation": (
                        plant.air_temperature_recommendation
                    ),
                    "air_humidity_recommendation": (
                        plant.air_humidity_recommendation
                    ),
                    "other_recommendations": plant.other_recommendations,
                    "todo_list": plant.todo_list,
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
            humidity_entity_id=None,
            air_temperature_entity_id=None,
            light_entity_id=None,
            water_entity_id=None,
            humidifier_entity_id=None,
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
            self.plants[plant_id].humidity_entity_id = entity_id

    def set_plant_air_temperature(
        self,
        plant_id: str,
        entity_id: str | None,
    ) -> None:
        """Set plant air temperature entity."""
        if plant_id in self.plants:
            self.plants[plant_id].air_temperature_entity_id = entity_id

    def set_plant_light(self, plant_id: str, entity_id: str | None) -> None:
        """Set plant light entity."""
        if plant_id in self.plants:
            self.plants[plant_id].light_entity_id = entity_id

    def set_plant_water(self, plant_id: str, entity_id: str | None) -> None:
        """Set plant water entity."""
        if plant_id in self.plants:
            self.plants[plant_id].water_entity_id = entity_id

    def set_plant_humidifier(self, plant_id: str, entity_id: str | None) -> None:
        """Set plant humidifier entity."""
        if plant_id in self.plants:
            self.plants[plant_id].humidifier_entity_id = entity_id

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
