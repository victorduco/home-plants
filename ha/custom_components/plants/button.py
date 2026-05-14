"""Button platform for Plants manual watering and auto waterer trigger."""

from __future__ import annotations

import asyncio

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data import AutoWaterersData, PlantsData

WATER_DURATIONS = [5, 10, 15, 30, 45, 60]


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
            for duration in WATER_DURATIONS:
                entities.append(AutoWatererWaterButton(hass, data, waterer_id, duration))

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


class AutoWatererWaterButton(ButtonEntity):
    """Button that waters for a fixed number of seconds."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        data: AutoWaterersData,
        waterer_id: str,
        duration_seconds: int,
    ) -> None:
        self.hass = hass
        self._data = data
        self._waterer_id = waterer_id
        self._duration = duration_seconds
        aw = data.auto_waterers[waterer_id]

        self._attr_name = f"Water {duration_seconds}s"
        self._attr_unique_id = f"auto_waterer_{waterer_id}_water_{duration_seconds}s"
        self._attr_icon = "mdi:water"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"auto_waterer_{waterer_id}")},
            name=aw.name,
            manufacturer="Custom",
            model="Auto Waterer",
        )

    async def async_press(self) -> None:
        """Turn on the outlet, wait duration, turn off — non-blocking."""
        aw = self._data.auto_waterers[self._waterer_id]
        outlet = aw.water_entity_id
        if not outlet:
            return
        domain = outlet.split(".")[0]
        on_service = "open_valve" if domain == "valve" else "turn_on"
        off_service = "close_valve" if domain == "valve" else "turn_off"

        async def _run() -> None:
            await self.hass.services.async_call(
                domain, on_service, {"entity_id": outlet}, blocking=True
            )
            await asyncio.sleep(self._duration)
            await self.hass.services.async_call(
                domain, off_service, {"entity_id": outlet}, blocking=True
            )

        self.hass.async_create_task(_run())
