"""Button platform for Plants manual watering and auto waterer trigger."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data import AutoWaterersData, PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants button entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    entry_type = entry_data["type"]
    data = entry_data["data"]
    entities: list[ButtonEntity] = []

    if entry_type == "plants":
        for plant_id in data.plants:
            entities.append(PlantManualWateringButton(hass, data, plant_id))
            entities.append(PlantManualShowerButton(hass, data, plant_id))
    elif entry_type == "auto_waterers":
        for waterer_id in data.auto_waterers:
            entities.append(AutoWatererTriggerButton(hass, data, waterer_id))

    if entities:
        async_add_entities(entities)


# ---------------------------------------------------------------------------
# Plant buttons
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# AutoWaterer buttons
# ---------------------------------------------------------------------------


class AutoWatererTriggerButton(ButtonEntity):
    """Button that manually triggers watering (turns on the water entity)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        data: AutoWaterersData,
        waterer_id: str,
    ) -> None:
        """Initialize the trigger button."""
        self.hass = hass
        self._data = data
        self._waterer_id = waterer_id
        aw = data.auto_waterers[waterer_id]

        self._attr_name = f"{aw.name} Trigger Watering"
        self._attr_unique_id = f"auto_waterer_{waterer_id}_trigger"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"auto_waterer_{waterer_id}")},
            name=aw.name,
            manufacturer="Custom",
            model="Auto Waterer",
        )

    async def async_press(self) -> None:
        """Turn on the water entity to trigger watering."""
        aw = self._data.auto_waterers[self._waterer_id]
        outlet = aw.water_entity_id
        if not outlet:
            return
        domain = outlet.split(".")[0]
        service = "open_valve" if domain == "valve" else "turn_on"
        await self.hass.services.async_call(
            domain, service, {"entity_id": outlet}, blocking=True
        )
