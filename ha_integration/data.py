"""State storage for Plants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_LAMP_POSITION_X,
    DEFAULT_LAMP_POSITION_Y,
    DEFAULT_LOCATION_X,
    DEFAULT_LOCATION_Y,
    DEFAULT_SOIL_MOISTURE,
    DOMAIN,
    STORAGE_VERSION,
)


@dataclass
class Plant:
    """Persisted plant data."""

    plant_id: str
    name: str
    last_watered: datetime | None
    soil_moisture: float
    location_x: float
    location_y: float


@dataclass
class Lamp:
    """Persisted lamp data."""

    lamp_id: str
    name: str
    outlet_entity_id: str | None
    position_x: float
    position_y: float
    plant_ids: list[str] = field(default_factory=list)


@dataclass
class PlantsData:
    """Persisted integration data."""

    store: Store
    plants: dict[str, Plant]
    lamps: dict[str, Lamp]

    @classmethod
    async def async_load(
        cls,
        hass: HomeAssistant,
        entry_id: str,
        default_plant_name: str | None,
    ) -> "PlantsData":
        """Load plants and lamps from storage."""
        store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}")
        raw = await store.async_load() or {}
        plants: dict[str, Plant] = {}
        lamps: dict[str, Lamp] = {}

        if not raw:
            name = default_plant_name or "Plant"
            plant_id = str(uuid4())
            plants[plant_id] = Plant(
                plant_id=plant_id,
                name=name,
                last_watered=None,
                soil_moisture=DEFAULT_SOIL_MOISTURE,
                location_x=DEFAULT_LOCATION_X,
                location_y=DEFAULT_LOCATION_Y,
            )
        elif "plants" in raw or "lamps" in raw:
            for item in raw.get("plants", []):
                plant_id = str(item.get("id") or uuid4())
                name = item.get("name") or default_plant_name or "Plant"
                last_watered = None
                if item.get("last_watered"):
                    last_watered = dt_util.parse_datetime(item["last_watered"])
                plants[plant_id] = Plant(
                    plant_id=plant_id,
                    name=name,
                    last_watered=last_watered,
                    soil_moisture=float(
                        item.get("soil_moisture", DEFAULT_SOIL_MOISTURE)
                    ),
                    location_x=float(item.get("location_x", DEFAULT_LOCATION_X)),
                    location_y=float(item.get("location_y", DEFAULT_LOCATION_Y)),
                )

            for item in raw.get("lamps", []):
                lamp_id = str(item.get("id") or uuid4())
                name = item.get("name") or f"Lamp {lamp_id[:4]}"
                plant_ids = [str(pid) for pid in item.get("plant_ids", []) if pid]
                lamps[lamp_id] = Lamp(
                    lamp_id=lamp_id,
                    name=name,
                    outlet_entity_id=item.get("outlet_entity_id"),
                    position_x=float(
                        item.get("position_x", DEFAULT_LAMP_POSITION_X)
                    ),
                    position_y=float(
                        item.get("position_y", DEFAULT_LAMP_POSITION_Y)
                    ),
                    plant_ids=plant_ids,
                )
        elif raw:
            name = default_plant_name or "Plant"
            last_watered = None
            if raw.get("last_watered"):
                last_watered = dt_util.parse_datetime(raw["last_watered"])
            plant_id = str(uuid4())
            plants[plant_id] = Plant(
                plant_id=plant_id,
                name=name,
                last_watered=last_watered,
                soil_moisture=float(raw.get("soil_moisture", DEFAULT_SOIL_MOISTURE)),
                location_x=float(raw.get("location_x", DEFAULT_LOCATION_X)),
                location_y=float(raw.get("location_y", DEFAULT_LOCATION_Y)),
            )

        return cls(store=store, plants=plants, lamps=lamps)

    async def async_save(self) -> None:
        """Persist plants and lamps."""
        payload = {
            "plants": [
                {
                    "id": plant.plant_id,
                    "name": plant.name,
                    "last_watered": plant.last_watered.isoformat()
                    if plant.last_watered
                    else None,
                    "soil_moisture": plant.soil_moisture,
                    "location_x": plant.location_x,
                    "location_y": plant.location_y,
                }
                for plant in self.plants.values()
            ],
            "lamps": [
                {
                    "id": lamp.lamp_id,
                    "name": lamp.name,
                    "outlet_entity_id": lamp.outlet_entity_id,
                    "position_x": lamp.position_x,
                    "position_y": lamp.position_y,
                    "plant_ids": lamp.plant_ids,
                }
                for lamp in self.lamps.values()
            ],
        }
        await self.store.async_save(payload)

    def add_plant(
        self,
        name: str,
        soil_moisture: float | None = None,
        location_x: float | None = None,
        location_y: float | None = None,
    ) -> Plant:
        """Add a new plant."""
        plant_id = str(uuid4())
        soil_value = (
            DEFAULT_SOIL_MOISTURE
            if soil_moisture is None
            else float(soil_moisture)
        )
        location_x_value = (
            DEFAULT_LOCATION_X if location_x is None else float(location_x)
        )
        location_y_value = (
            DEFAULT_LOCATION_Y if location_y is None else float(location_y)
        )
        plant = Plant(
            plant_id=plant_id,
            name=name,
            last_watered=None,
            soil_moisture=soil_value,
            location_x=location_x_value,
            location_y=location_y_value,
        )
        self.plants[plant_id] = plant
        return plant

    def remove_plant(self, plant_id: str) -> bool:
        """Remove a plant and unlink it from lamps."""
        removed = self.plants.pop(plant_id, None) is not None
        if removed:
            for lamp in self.lamps.values():
                lamp.plant_ids = [pid for pid in lamp.plant_ids if pid != plant_id]
        return removed

    def add_lamp(
        self,
        name: str,
        outlet_entity_id: str | None = None,
        position_x: float | None = None,
        position_y: float | None = None,
        plant_ids: list[str] | None = None,
    ) -> Lamp:
        """Add a new lamp."""
        lamp_id = str(uuid4())
        position_x_value = (
            DEFAULT_LAMP_POSITION_X if position_x is None else float(position_x)
        )
        position_y_value = (
            DEFAULT_LAMP_POSITION_Y if position_y is None else float(position_y)
        )
        lamp = Lamp(
            lamp_id=lamp_id,
            name=name,
            outlet_entity_id=outlet_entity_id,
            position_x=position_x_value,
            position_y=position_y_value,
            plant_ids=plant_ids or [],
        )
        self.lamps[lamp_id] = lamp
        return lamp

    def remove_lamp(self, lamp_id: str) -> bool:
        """Remove a lamp."""
        return self.lamps.pop(lamp_id, None) is not None

    def link_lamp_plants(self, lamp_id: str, plant_ids: list[str]) -> None:
        """Replace lamp plant links."""
        if lamp_id in self.lamps:
            self.lamps[lamp_id].plant_ids = plant_ids

    def set_lamp_outlet(self, lamp_id: str, outlet_entity_id: str) -> None:
        """Set lamp outlet entity."""
        if lamp_id in self.lamps:
            self.lamps[lamp_id].outlet_entity_id = outlet_entity_id
