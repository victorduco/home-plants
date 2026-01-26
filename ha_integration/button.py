"""Button platform for Plants manual watering."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data import PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants button entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    if entry_data["type"] == "meter_locations":
        return
    data: PlantsData = entry_data["data"]
    entities = []
    for plant_id in data.plants:
        entities.append(PlantManualWateringButton(hass, data, plant_id))
        entities.append(PlantManualShowerButton(hass, data, plant_id))
    if entities:
        async_add_entities(entities)


class PlantManualWateringButton(ButtonEntity):
    """Button entity for recording manual plant watering."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        data: PlantsData,
        plant_id: str,
    ) -> None:
        """Initialize the button entity."""
        self.hass = hass
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]

        self._attr_name = "Add Manual Watering"
        self._attr_unique_id = f"plant_{plant_id}_manual_watering_button"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    async def async_press(self) -> None:
        """Record a manual watering event."""
        entity_registry = er.async_get(self.hass)
        event_entity_id = entity_registry.async_get_entity_id(
            "event",
            DOMAIN,
            f"plant_{self._plant_id}_manual_watering",
        )
        if not event_entity_id:
            return

        entity = None
        for component in self.hass.data.get("entity_components", {}).values():
            for candidate in getattr(component, "entities", []):
                if getattr(candidate, "entity_id", None) == event_entity_id:
                    entity = candidate
                    break
            if entity is not None:
                break

        if entity and hasattr(entity, "record_watering"):
            entity.record_watering()


class PlantManualShowerButton(ButtonEntity):
    """Button entity for recording manual plant shower."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        data: PlantsData,
        plant_id: str,
    ) -> None:
        """Initialize the button entity."""
        self.hass = hass
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]

        self._attr_name = "Add Manual Shower"
        self._attr_unique_id = f"plant_{plant_id}_manual_shower_button"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    async def async_press(self) -> None:
        """Record a manual shower event."""
        entity_registry = er.async_get(self.hass)
        event_entity_id = entity_registry.async_get_entity_id(
            "event",
            DOMAIN,
            f"plant_{self._plant_id}_manual_shower",
        )
        if not event_entity_id:
            return

        entity = None
        for component in self.hass.data.get("entity_components", {}).values():
            for candidate in getattr(component, "entities", []):
                if getattr(candidate, "entity_id", None) == event_entity_id:
                    entity = candidate
                    break
            if entity is not None:
                break

        if entity and hasattr(entity, "record_shower"):
            entity.record_shower()
