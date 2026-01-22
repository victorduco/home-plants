"""Switch platform for Plants light control."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .data import PlantsData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants switch entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    if entry_data["type"] == "meter_locations":
        return
    data: PlantsData = entry_data["data"]
    entities = []
    for plant_id in data.plants:
        entities.append(PlantLightSwitch(data, plant_id))
        entities.append(PlantHumidifierSwitch(data, plant_id))
        entities.append(PlantWaterSwitch(data, plant_id))
        entities.append(PlantManualWateringSwitch(data, plant_id))
    if entities:
        async_add_entities(entities)

CONTROL_DOMAINS = ("switch", "light", "input_boolean")
WATER_CONTROL_DOMAINS = ("valve", "switch")
HUMIDIFIER_CONTROL_DOMAINS = ("switch", "input_boolean")


class PlantLightSwitch(SwitchEntity):
    """Proxy switch for a plant light outlet."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Grow Light Control"
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
    """Proxy switch for a plant water outlet (valve or switch)."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Auto Watering Control"
        self._attr_unique_id = f"plant_{plant_id}_auto_watering_control"
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
        if not outlet or outlet == "None" or not self.hass:
            return False
        domain = outlet.split(".")[0]
        if domain not in WATER_CONTROL_DOMAINS:
            return False
        state = self.hass.states.get(outlet)
        return state is not None

    @property
    def is_on(self) -> bool:
        outlet = self._outlet_entity_id
        if not outlet or not self.hass:
            return False
        state = self.hass.states.get(outlet)
        if state is None:
            return False
        # Support both valve (open/opening) and switch (on) states
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

        async_track_state_change_event(self.hass, [outlet], _handle_state_change)


class PlantManualWateringSwitch(SwitchEntity, RestoreEntity):
    """Manual watering switch for a plant."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        self._is_on = False
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Manual Watering Control"
        self._attr_unique_id = f"plant_{plant_id}_manual_watering"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        state = await self.async_get_last_state()
        if state is not None:
            self._is_on = state.state == STATE_ON


class PlantHumidifierSwitch(SwitchEntity):
    """Proxy switch for a plant humidifier device."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Humidifier Control"
        self._attr_unique_id = f"plant_{plant_id}_humidifier_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def _control_entity_id(self) -> str | None:
        return self._data.plants[self._plant_id].humidifier_entity_id

    @property
    def available(self) -> bool:
        entity_id = self._control_entity_id
        if not entity_id or not self.hass:
            return False
        domain = entity_id.split(".")[0]
        if domain not in HUMIDIFIER_CONTROL_DOMAINS:
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
        if domain not in HUMIDIFIER_CONTROL_DOMAINS:
            return
        await self.hass.services.async_call(
            domain, "turn_on", {"entity_id": entity_id}, blocking=True
        )

    async def async_turn_off(self, **kwargs) -> None:
        entity_id = self._control_entity_id
        if not entity_id or not self.hass:
            return
        domain = entity_id.split(".")[0]
        if domain not in HUMIDIFIER_CONTROL_DOMAINS:
            return
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

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)
