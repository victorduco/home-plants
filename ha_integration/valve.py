"""Valve platform for Plants auto watering control."""

from __future__ import annotations

from homeassistant.components.valve import ValveEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .data import PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants valve entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    if entry_data["type"] == "meter_locations":
        return
    data: PlantsData = entry_data["data"]
    entities = [PlantWaterValve(data, plant_id) for plant_id in data.plants]
    if entities:
        async_add_entities(entities)


class PlantWaterValve(ValveEntity):
    """Proxy valve for a plant water outlet."""

    _attr_supported_features = 0

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Auto Watering Control"
        self._attr_unique_id = f"plant_{plant_id}_water_power"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def _outlet_entity_id(self) -> str | None:
        return self._data.plants[self._plant_id].water_entity_id

    @property
    def available(self) -> bool:
        outlet = self._outlet_entity_id
        return bool(outlet and self.hass and self.hass.states.get(outlet))

    @property
    def is_open(self) -> bool | None:
        outlet = self._outlet_entity_id
        if not outlet or not self.hass:
            return None
        state = self.hass.states.get(outlet)
        if state is None:
            return None
        return state.state in ("open", "opening", "on")

    async def async_open_valve(self, **kwargs) -> None:
        outlet = self._outlet_entity_id
        if not outlet:
            return
        domain = outlet.split(".")[0]
        service = "open_valve" if domain == "valve" else "turn_on"
        await self.hass.services.async_call(
            domain, service, {"entity_id": outlet}, blocking=True
        )

    async def async_close_valve(self, **kwargs) -> None:
        outlet = self._outlet_entity_id
        if not outlet:
            return
        domain = outlet.split(".")[0]
        service = "close_valve" if domain == "valve" else "turn_off"
        await self.hass.services.async_call(
            domain, service, {"entity_id": outlet}, blocking=True
        )

    async def async_added_to_hass(self) -> None:
        outlet = self._outlet_entity_id
        if not outlet or not self.hass:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [outlet], _handle_state_change)
