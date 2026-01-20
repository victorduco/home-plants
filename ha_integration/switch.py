"""Switch platform for Plants light control."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
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
    """Set up Plants switch entities from a config entry."""
    data: PlantsData = hass.data[DOMAIN]["data"]
    entities = []
    for plant_id in data.plants:
        entities.append(PlantLightSwitch(data, plant_id))
        entities.append(PlantWaterSwitch(data, plant_id))
    if entities:
        async_add_entities(entities)


class PlantLightSwitch(SwitchEntity):
    """Proxy switch for a plant light outlet."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Light Power"
        self._attr_unique_id = f"plant_{plant_id}_light_power"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def _outlet_entity_id(self) -> str | None:
        return self._data.plants[self._plant_id].light_entity_id

    @property
    def available(self) -> bool:
        outlet = self._outlet_entity_id
        return bool(outlet and self.hass.states.get(outlet))

    @property
    def is_on(self) -> bool:
        outlet = self._outlet_entity_id
        if not outlet:
            return False
        state = self.hass.states.get(outlet)
        if state is None:
            return False
        return state.state == STATE_ON

    async def async_turn_on(self, **kwargs) -> None:
        outlet = self._outlet_entity_id
        if not outlet:
            return
        domain = outlet.split(".")[0]
        await self.hass.services.async_call(
            domain, "turn_on", {"entity_id": outlet}, blocking=True
        )

    async def async_turn_off(self, **kwargs) -> None:
        outlet = self._outlet_entity_id
        if not outlet:
            return
        domain = outlet.split(".")[0]
        await self.hass.services.async_call(
            domain, "turn_off", {"entity_id": outlet}, blocking=True
        )

    async def async_added_to_hass(self) -> None:
        outlet = self._outlet_entity_id
        if not outlet:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [outlet], _handle_state_change)


class PlantWaterSwitch(SwitchEntity):
    """Proxy switch for a plant water outlet."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Water Power"
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
        return bool(outlet and self.hass.states.get(outlet))

    @property
    def is_on(self) -> bool:
        outlet = self._outlet_entity_id
        if not outlet:
            return False
        state = self.hass.states.get(outlet)
        if state is None:
            return False
        return state.state == STATE_ON

    async def async_turn_on(self, **kwargs) -> None:
        outlet = self._outlet_entity_id
        if not outlet:
            return
        domain = outlet.split(".")[0]
        await self.hass.services.async_call(
            domain, "turn_on", {"entity_id": outlet}, blocking=True
        )

    async def async_turn_off(self, **kwargs) -> None:
        outlet = self._outlet_entity_id
        if not outlet:
            return
        domain = outlet.split(".")[0]
        await self.hass.services.async_call(
            domain, "turn_off", {"entity_id": outlet}, blocking=True
        )

    async def async_added_to_hass(self) -> None:
        outlet = self._outlet_entity_id
        if not outlet:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [outlet], _handle_state_change)
