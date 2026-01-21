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
    entities: list[SensorEntity] = []
    for plant_id in data.plants:
        entities.append(PlantMoistureSensor(data, plant_id))
        entities.append(PlantHumiditySensor(data, plant_id))
        entities.append(PlantAirTemperatureSensor(data, plant_id))
        entities.append(PlantLightStateSensor(data, plant_id))
        entities.append(PlantAutoWateringStateSensor(data, plant_id))
        entities.append(PlantHumidifierStateSensor(data, plant_id))
    if entities:
        async_add_entities(entities)


class PlantMoistureSensor(SensorEntity):
    """Sensor mirroring the configured moisture state."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Soil Moisture State"
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
            return "No soil moisture meter near the plant."
        state = self.hass.states.get(moisture_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "No soil moisture meter near the plant."
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


class PlantHumiditySensor(SensorEntity):
    """Sensor mirroring the configured humidity meter state."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Humidity Meter"
        self._attr_unique_id = f"plant_{plant_id}_humidity"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self):
        humidity_entity_id = self._data.plants[self._plant_id].humidity_entity_id
        if not humidity_entity_id or not self.hass:
            return "No air humidity meter near the plant."
        state = self.hass.states.get(humidity_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "No air humidity meter near the plant."
        try:
            return float(state.state)
        except ValueError:
            return state.state

    @property
    def native_unit_of_measurement(self):
        humidity_entity_id = self._data.plants[self._plant_id].humidity_entity_id
        if not humidity_entity_id or not self.hass:
            return None
        state = self.hass.states.get(humidity_entity_id)
        if not state:
            return None
        return state.attributes.get("unit_of_measurement")

    @property
    def extra_state_attributes(self) -> dict:
        plant = self._data.plants[self._plant_id]
        return {"humidity_entity_id": plant.humidity_entity_id}


class PlantLightStateSensor(SensorEntity):
    """Sensor describing the current light state."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Grow Light State"
        self._attr_unique_id = f"plant_{plant_id}_light_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self):
        outlet_entity_id = self._data.plants[self._plant_id].light_entity_id
        if not outlet_entity_id or not self.hass:
            return "No grow light near the plant."
        state = self.hass.states.get(outlet_entity_id)
        if not state:
            return "No grow light near the plant."
        return state.state


class PlantAutoWateringStateSensor(SensorEntity):
    """Sensor describing the automatic watering state."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Auto Watering State"
        self._attr_unique_id = f"plant_{plant_id}_auto_watering_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self):
        outlet_entity_id = self._data.plants[self._plant_id].water_entity_id
        if not outlet_entity_id or not self.hass:
            return (
                "Device not installed. Watering can only be done manually by the user."
            )
        state = self.hass.states.get(outlet_entity_id)
        if not state:
            return (
                "Device not installed. Watering can only be done manually by the user."
            )
        return state.state


class PlantHumidifierStateSensor(SensorEntity):
    """Sensor describing the humidifier state."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Humidifier State"
        self._attr_unique_id = f"plant_{plant_id}_humidifier_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self):
        humidifier_entity_id = self._data.plants[self._plant_id].humidifier_entity_id
        if not humidifier_entity_id or not self.hass:
            return "No air humidifier near the plant."
        state = self.hass.states.get(humidifier_entity_id)
        if not state:
            return "No air humidifier near the plant."
        return state.state


class PlantAirTemperatureSensor(SensorEntity):
    """Sensor mirroring the configured air temperature meter state."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Temperature Meter"
        self._attr_unique_id = f"plant_{plant_id}_air_temperature"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self):
        entity_id = self._data.plants[self._plant_id].air_temperature_entity_id
        if not entity_id or not self.hass:
            return "No air temperature meter near the plant."
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "No air temperature meter near the plant."
        try:
            return float(state.state)
        except ValueError:
            return state.state

    @property
    def native_unit_of_measurement(self):
        entity_id = self._data.plants[self._plant_id].air_temperature_entity_id
        if not entity_id or not self.hass:
            return None
        state = self.hass.states.get(entity_id)
        if not state:
            return None
        return state.attributes.get("unit_of_measurement")

    @property
    def extra_state_attributes(self) -> dict:
        plant = self._data.plants[self._plant_id]
        return {"air_temperature_entity_id": plant.air_temperature_entity_id}
