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
    data: PlantsData = hass.data[DOMAIN]["data"]
    entities = [PlantMoistureSensor(data, plant_id) for plant_id in data.plants]
    if entities:
        async_add_entities(entities)


class PlantMoistureSensor(SensorEntity):
    """Sensor mirroring the configured moisture entity."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Moisture"
        self._attr_unique_id = f"plant_{plant_id}_moisture"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self):
        moisture_entity_id = self._data.plants[self._plant_id].moisture_entity_id
        if not moisture_entity_id or not self.hass:
            return None
        state = self.hass.states.get(moisture_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except ValueError:
            return state.state

    @property
    def native_unit_of_measurement(self):
        moisture_entity_id = self._data.plants[self._plant_id].moisture_entity_id
        if not moisture_entity_id or not self.hass:
            return None
        state = self.hass.states.get(moisture_entity_id)
        if not state:
            return None
        return state.attributes.get("unit_of_measurement")

    @property
    def extra_state_attributes(self) -> dict:
        plant = self._data.plants[self._plant_id]
        return {"moisture_entity_id": plant.moisture_entity_id}
