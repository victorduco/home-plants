"""Switch platform for Plants device control."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .data import AutoWaterersData, GrowLightsData, HumidifiersData

WATER_CONTROL_DOMAINS = ("valve", "switch")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants switch entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    entry_type = entry_data["type"]
    data = entry_data["data"]
    entities: list[SwitchEntity] = []

    if entry_type == "grow_lights":
        for grow_light_id in data.grow_lights:
            entities.append(GrowLightSwitch(data, grow_light_id))
    elif entry_type == "humidifiers":
        for humidifier_id in data.humidifiers:
            entities.append(HumidifierSwitch(data, humidifier_id))
    elif entry_type == "auto_waterers":
        for waterer_id in data.auto_waterers:
            entities.append(AutoWatererSwitch(data, waterer_id))

    if entities:
        async_add_entities(entities)


# ---------------------------------------------------------------------------
# GrowLight switch
# ---------------------------------------------------------------------------


class GrowLightSwitch(SwitchEntity):
    """Proxy switch for a grow light outlet."""

    def __init__(self, data: GrowLightsData, grow_light_id: str) -> None:
        self._data = data
        self._grow_light_id = grow_light_id
        gl = data.grow_lights[grow_light_id]
        self._attr_name = f"{gl.name} Control"
        self._attr_unique_id = f"grow_light_{grow_light_id}_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"grow_light_{grow_light_id}")},
            name=gl.name,
            manufacturer="Custom",
            model="Grow Light",
        )

    @property
    def _outlet_entity_id(self) -> str | None:
        return self._data.grow_lights[self._grow_light_id].light_entity_id

    @property
    def available(self) -> bool:
        outlet = self._outlet_entity_id
        return bool(outlet and self.hass and self.hass.states.get(outlet))

    @property
    def is_on(self) -> bool:
        outlet = self._outlet_entity_id
        if not outlet or not self.hass:
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

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [outlet], _handle_state_change
            )
        )


# ---------------------------------------------------------------------------
# Humidifier switch
# ---------------------------------------------------------------------------


class HumidifierSwitch(SwitchEntity):
    """Proxy switch for a humidifier device."""

    def __init__(self, data: HumidifiersData, humidifier_id: str) -> None:
        self._data = data
        self._humidifier_id = humidifier_id
        hd = data.humidifiers[humidifier_id]
        self._attr_name = f"{hd.name} Control"
        self._attr_unique_id = f"humidifier_{humidifier_id}_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"humidifier_{humidifier_id}")},
            name=hd.name,
            manufacturer="Custom",
            model="Humidifier",
        )

    @property
    def _control_entity_id(self) -> str | None:
        return self._data.humidifiers[self._humidifier_id].humidifier_entity_id

    @property
    def available(self) -> bool:
        entity_id = self._control_entity_id
        if not entity_id or not self.hass:
            return False
        return bool(self.hass.states.get(entity_id))

    @property
    def is_on(self) -> bool:
        entity_id = self._control_entity_id
        if not entity_id or not self.hass:
            return False
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        return state.state == STATE_ON

    async def async_turn_on(self, **kwargs) -> None:
        entity_id = self._control_entity_id
        if not entity_id or not self.hass:
            return
        domain = entity_id.split(".")[0]
        await self.hass.services.async_call(
            domain, "turn_on", {"entity_id": entity_id}, blocking=True
        )

    async def async_turn_off(self, **kwargs) -> None:
        entity_id = self._control_entity_id
        if not entity_id or not self.hass:
            return
        domain = entity_id.split(".")[0]
        await self.hass.services.async_call(
            domain, "turn_off", {"entity_id": entity_id}, blocking=True
        )

    async def async_added_to_hass(self) -> None:
        entity_id = self._control_entity_id
        if not entity_id or not self.hass:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [entity_id], _handle_state_change
            )
        )


# ---------------------------------------------------------------------------
# AutoWaterer switch
# ---------------------------------------------------------------------------


class AutoWatererSwitch(SwitchEntity):
    """Proxy switch for an auto waterer valve/switch."""

    def __init__(self, data: AutoWaterersData, waterer_id: str) -> None:
        self._data = data
        self._waterer_id = waterer_id
        aw = data.auto_waterers[waterer_id]
        self._attr_name = f"{aw.name} Control"
        self._attr_unique_id = f"auto_waterer_{waterer_id}_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"auto_waterer_{waterer_id}")},
            name=aw.name,
            manufacturer="Custom",
            model="Auto Waterer",
        )

    @property
    def _outlet_entity_id(self) -> str | None:
        return self._data.auto_waterers[self._waterer_id].water_entity_id

    @property
    def available(self) -> bool:
        outlet = self._outlet_entity_id
        if not outlet or not self.hass:
            return False
        domain = outlet.split(".")[0]
        if domain not in WATER_CONTROL_DOMAINS:
            return False
        return bool(self.hass.states.get(outlet))

    @property
    def is_on(self) -> bool:
        outlet = self._outlet_entity_id
        if not outlet or not self.hass:
            return False
        state = self.hass.states.get(outlet)
        if state is None:
            return False
        return state.state in ("on", "open", "opening")

    async def async_turn_on(self, **kwargs) -> None:
        outlet = self._outlet_entity_id
        if not outlet or not self.hass:
            return
        domain = outlet.split(".")[0]
        service = "open_valve" if domain == "valve" else "turn_on"
        await self.hass.services.async_call(
            domain, service, {"entity_id": outlet}, blocking=True
        )

    async def async_turn_off(self, **kwargs) -> None:
        outlet = self._outlet_entity_id
        if not outlet or not self.hass:
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

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [outlet], _handle_state_change
            )
        )
