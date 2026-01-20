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
    light_entity_id: str | None
    water_entity_id: str | None


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
                light_entity_id=None,
                water_entity_id=None,
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
                light_entity_id=item.get("light_entity_id"),
                water_entity_id=item.get("water_entity_id"),
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
                    "light_entity_id": plant.light_entity_id,
                    "water_entity_id": plant.water_entity_id,
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
            light_entity_id=None,
            water_entity_id=None,
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

    def set_plant_light(self, plant_id: str, entity_id: str | None) -> None:
        """Set plant light entity."""
        if plant_id in self.plants:
            self.plants[plant_id].light_entity_id = entity_id

    def set_plant_water(self, plant_id: str, entity_id: str | None) -> None:
        """Set plant water entity."""
        if plant_id in self.plants:
            self.plants[plant_id].water_entity_id = entity_id
