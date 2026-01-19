"""Switch platform for Plants lamps."""

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
    data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
    async_add_entities(
        [LampPowerSwitch(entry, data, lamp_id) for lamp_id in data.lamps]
    )


class LampPowerSwitch(SwitchEntity):
    """Proxy switch for a lamp outlet entity."""

    def __init__(
        self, entry: ConfigEntry, data: PlantsData, lamp_id: str
    ) -> None:
        self._entry = entry
        self._data = data
        self._lamp_id = lamp_id
        lamp = data.lamps[lamp_id]
        self._attr_name = f"{lamp.name} Power"
        self._attr_unique_id = f"{entry.entry_id}_lamp_{lamp_id}_power"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"lamp_{lamp_id}")},
            name=lamp.name,
            manufacturer="Custom",
            model="Grow Lamp",
        )

    @property
    def _outlet_entity_id(self) -> str | None:
        return self._data.lamps[self._lamp_id].outlet_entity_id

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
