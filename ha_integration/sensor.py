"""Sensor platform for Plants."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data import PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants sensors from a config entry."""
    data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
    plant_entities = [
        PlantStatusSensor(entry, data, plant_id) for plant_id in data.plants
    ]
    lamp_entities = [
        LampPlantsSensor(entry, data, lamp_id) for lamp_id in data.lamps
    ]
    async_add_entities(plant_entities + lamp_entities)


class PlantStatusSensor(SensorEntity):
    """Simple sensor showing plant status."""

    _attr_native_value = "ready"

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, plant_id: str
    ) -> None:
        self._entry = entry
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Status"
        self._attr_unique_id = f"{entry.entry_id}_plant_{plant_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )


class LampPlantsSensor(SensorEntity):
    """Sensor listing plants controlled by a lamp."""

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, lamp_id: str
    ) -> None:
        self._entry = entry
        self._data = data
        self._lamp_id = lamp_id
        lamp = data.lamps[lamp_id]
        self._attr_name = f"{lamp.name} Plants"
        self._attr_unique_id = f"{entry.entry_id}_lamp_{lamp_id}_plants"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"lamp_{lamp_id}")},
            name=lamp.name,
            manufacturer="Custom",
            model="Grow Lamp",
        )

    @property
    def native_value(self) -> str:
        plant_names = [
            self._data.plants[plant_id].name
            for plant_id in self._data.lamps[self._lamp_id].plant_ids
            if plant_id in self._data.plants
        ]
        return ", ".join(plant_names) if plant_names else "none"

    @property
    def extra_state_attributes(self) -> dict:
        lamp = self._data.lamps[self._lamp_id]
        return {
            "plant_ids": lamp.plant_ids,
            "plant_names": [
                self._data.plants[plant_id].name
                for plant_id in lamp.plant_ids
                if plant_id in self._data.plants
            ],
            "outlet_entity_id": lamp.outlet_entity_id,
        }
