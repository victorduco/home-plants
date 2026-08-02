"""Sensor platform for Plants."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STALE_AFTER
from .data import AutoWaterersData, GrowLightsData, HumidifiersData, MeterLocationsData, PlantsData, ThermostatsData

STORAGE_AGENT_LOG = "plants_agent_log"


def _is_stale(state) -> bool:
    """Return True if the state's last update is older than STALE_AFTER."""
    if state is None or state.last_updated is None:
        return False
    return (datetime.now(timezone.utc) - state.last_updated) > STALE_AFTER


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants sensors from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    entry_type = entry_data["type"]
    data = entry_data["data"]
    entities: list[SensorEntity] = []

    if entry_type == "meter_locations":
        for location_id in data.meter_locations:
            entities.append(LocationAirHumiditySensor(data, location_id))
            entities.append(LocationAirTemperatureSensor(data, location_id))
    elif entry_type == "grow_lights":
        for grow_light_id in data.grow_lights:
            entities.append(GrowLightStateSensor(data, grow_light_id))
    elif entry_type == "humidifiers":
        for humidifier_id in data.humidifiers:
            entities.append(HumidifierStateSensor(data, humidifier_id))
    elif entry_type == "thermostats":
        for thermostat_id in data.thermostats:
            entities.append(ThermostatStateSensor(data, thermostat_id))
    elif entry_type == "auto_waterers":
        for waterer_id in data.auto_waterers:
            entities.append(AutoWatererStateSensor(hass, data, waterer_id))
    elif entry_type == "agent_log":
        store = Store(hass, 1, STORAGE_AGENT_LOG)
        raw = await store.async_load() or {}
        issues_sensor = AgentLogSensor(store, "plant_check_issues", "Plant Check Issues", "mdi:alert-circle-outline", raw)
        actions_sensor = AgentLogSensor(store, "plant_check_actions", "Plant Check Actions", "mdi:robot", raw)
        entities.extend([issues_sensor, actions_sensor])

        async def async_handle_update_agent_log(call) -> None:
            field = call.data["field"]
            items = call.data["items"]
            sensor = issues_sensor if field == "plant_check_issues" else actions_sensor
            await sensor.async_update_items(items)

        import voluptuous as vol
        import homeassistant.helpers.config_validation as cv
        hass.services.async_register(
            DOMAIN,
            "update_agent_log",
            async_handle_update_agent_log,
            schema=vol.Schema({
                vol.Required("field"): vol.In(["plant_check_issues", "plant_check_actions"]),
                vol.Required("items"): [cv.string],
            }),
        )
    else:
        # plants
        for plant_id in data.plants:
            entities.append(PlantMoistureSensor(data, plant_id))
            entities.append(PlantHumiditySensor(data, plant_id))
            entities.append(PlantAirTemperatureSensor(data, plant_id))
            entities.append(PlantAutoWateringStateSensor(hass, data, plant_id))
            entities.append(PlantMoistureZoneSensor(data, plant_id))
            entities.append(PlantHumidityZoneSensor(data, plant_id))
            entities.append(PlantTemperatureZoneSensor(data, plant_id))

    if entities:
        async_add_entities(entities)


# ---------------------------------------------------------------------------
# Plant sensors
# ---------------------------------------------------------------------------


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
        if _is_stale(state):
            return "Stale"
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
        attrs: dict = {"moisture_entity_id": plant.moisture_entity_id}
        if plant.moisture_entity_id and self.hass:
            state = self.hass.states.get(plant.moisture_entity_id)
            if state is not None:
                attrs["is_stale"] = _is_stale(state)
                attrs["source_last_updated"] = state.last_updated.isoformat()
        return attrs

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.plants[self._plant_id].moisture_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)

        @callback
        def _refresh(_now) -> None:
            self.async_write_ha_state()

        async_call_later(self.hass, 5, _refresh)


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
        air_humidity_entity_id = self._data.plants[self._plant_id].air_humidity_entity_id
        if not air_humidity_entity_id or not self.hass:
            return "No air humidity meter near the plant."
        state = self.hass.states.get(air_humidity_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "No air humidity meter near the plant."
        if _is_stale(state):
            return "Stale"
        try:
            return float(state.state)
        except ValueError:
            return state.state

    @property
    def native_unit_of_measurement(self):
        air_humidity_entity_id = self._data.plants[self._plant_id].air_humidity_entity_id
        if not air_humidity_entity_id or not self.hass:
            return None
        state = self.hass.states.get(air_humidity_entity_id)
        if not state:
            return None
        return state.attributes.get("unit_of_measurement")

    @property
    def extra_state_attributes(self) -> dict:
        plant = self._data.plants[self._plant_id]
        attrs: dict = {"air_humidity_entity_id": plant.air_humidity_entity_id}
        if plant.air_humidity_entity_id and self.hass:
            state = self.hass.states.get(plant.air_humidity_entity_id)
            if state is not None:
                attrs["is_stale"] = _is_stale(state)
                attrs["source_last_updated"] = state.last_updated.isoformat()
        return attrs

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.plants[self._plant_id].air_humidity_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)

        @callback
        def _refresh(_now) -> None:
            self.async_write_ha_state()

        async_call_later(self.hass, 5, _refresh)


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
        if _is_stale(state):
            return "Stale"
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
        attrs: dict = {"air_temperature_entity_id": plant.air_temperature_entity_id}
        if plant.air_temperature_entity_id and self.hass:
            state = self.hass.states.get(plant.air_temperature_entity_id)
            if state is not None:
                attrs["is_stale"] = _is_stale(state)
                attrs["source_last_updated"] = state.last_updated.isoformat()
        return attrs

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.plants[self._plant_id].air_temperature_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)

        @callback
        def _refresh(_now) -> None:
            self.async_write_ha_state()

        async_call_later(self.hass, 5, _refresh)


class PlantMoistureZoneSensor(SensorEntity):
    """Sensor returning red/yellow/green zone for soil moisture."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Soil Moisture Zone"
        self._attr_unique_id = f"plant_{plant_id}_moisture_zone"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> str:
        plant = self._data.plants[self._plant_id]
        if not plant.moisture_entity_id or not self.hass:
            return "unknown"
        state = self.hass.states.get(plant.moisture_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "unknown"
        if _is_stale(state):
            return "stale"
        try:
            moisture = float(state.state)
        except ValueError:
            return "unknown"
        red = plant.moisture_red_threshold if plant.moisture_red_threshold is not None else 15.0
        yellow = plant.moisture_yellow_threshold if plant.moisture_yellow_threshold is not None else 30.0
        if moisture < red:
            return "red"
        if moisture < yellow:
            return "yellow"
        return "green"

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.plants[self._plant_id].moisture_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)

        @callback
        def _refresh(_now) -> None:
            self.async_write_ha_state()

        async_call_later(self.hass, 5, _refresh)


class PlantHumidityZoneSensor(SensorEntity):
    """Sensor returning red/yellow/green zone for air humidity."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Humidity Zone"
        self._attr_unique_id = f"plant_{plant_id}_humidity_zone"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> str:
        plant = self._data.plants[self._plant_id]
        if not plant.air_humidity_entity_id or not self.hass:
            return "unknown"
        state = self.hass.states.get(plant.air_humidity_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "unknown"
        if _is_stale(state):
            return "stale"
        try:
            humidity = float(state.state)
        except ValueError:
            return "unknown"
        h_min = plant.humidity_min if plant.humidity_min is not None else 40.0
        h_max = plant.humidity_max if plant.humidity_max is not None else 70.0
        if humidity < h_min or humidity > h_max:
            return "red"
        return "green"

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.plants[self._plant_id].air_humidity_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)

        @callback
        def _refresh(_now) -> None:
            self.async_write_ha_state()

        async_call_later(self.hass, 5, _refresh)


class PlantTemperatureZoneSensor(SensorEntity):
    """Sensor returning red/yellow/green zone for air temperature."""

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = f"{plant.name} Air Temperature Zone"
        self._attr_unique_id = f"plant_{plant_id}_temperature_zone"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )

    @property
    def native_value(self) -> str:
        plant = self._data.plants[self._plant_id]
        if not plant.air_temperature_entity_id or not self.hass:
            return "unknown"
        state = self.hass.states.get(plant.air_temperature_entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "unknown"
        if _is_stale(state):
            return "stale"
        try:
            temp = float(state.state)
        except ValueError:
            return "unknown"
        t_min = plant.temperature_min if plant.temperature_min is not None else 60.0
        t_max = plant.temperature_max if plant.temperature_max is not None else 85.0
        if temp < t_min or temp > t_max:
            return "red"
        return "green"

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.plants[self._plant_id].air_temperature_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)

        @callback
        def _refresh(_now) -> None:
            self.async_write_ha_state()

        async_call_later(self.hass, 5, _refresh)


class PlantAutoWateringStateSensor(SensorEntity):
    """Sensor showing whether an AutoWaterer is currently watering this plant.

    Looks up all auto_waterer entries in hass.data to find ones that include
    this plant_id in their plant_ids list, then reads the water_entity_id state.
    """

    def __init__(self, hass: HomeAssistant, data: PlantsData, plant_id: str) -> None:
        self._hass = hass
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

    def _find_waterer_entity_id(self) -> str | None:
        """Scan hass.data for auto_waterer entries that include this plant."""
        domain_data = self._hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            if not isinstance(entry_data, dict):
                continue
            if entry_data.get("type") != "auto_waterers":
                continue
            aw_data: AutoWaterersData = entry_data["data"]
            for aw in aw_data.auto_waterers.values():
                if self._plant_id in aw.plant_ids and aw.water_entity_id:
                    return aw.water_entity_id
        return None

    @property
    def native_value(self):
        water_entity_id = self._find_waterer_entity_id()
        if not water_entity_id:
            return "No auto waterer installed"
        state = self._hass.states.get(water_entity_id)
        if not state:
            return "No auto waterer installed"
        raw_state = state.state.lower()
        if raw_state in ("on", "open", "opening"):
            return "Watering"
        if raw_state in ("off", "closed", "closing"):
            return "Not watering"
        if raw_state == "unavailable":
            return "Device unavailable"
        return raw_state

    async def async_added_to_hass(self) -> None:
        # Track state changes on the waterer entity if one is configured.
        # We schedule a deferred check so that auto_waterer entries (loaded
        # in parallel) are fully available before we look them up.
        water_entity_id = self._find_waterer_entity_id()
        if not water_entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(
            self.hass, [water_entity_id], _handle_state_change
        )


# ---------------------------------------------------------------------------
# GrowLight sensors
# ---------------------------------------------------------------------------


class GrowLightStateSensor(SensorEntity):
    """Sensor mirroring the grow light outlet state."""

    def __init__(self, data: GrowLightsData, grow_light_id: str) -> None:
        self._data = data
        self._grow_light_id = grow_light_id
        gl = data.grow_lights[grow_light_id]
        self._attr_name = f"{gl.name} State"
        self._attr_unique_id = f"grow_light_{grow_light_id}_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"grow_light_{grow_light_id}")},
            name=gl.name,
            manufacturer="Custom",
            model="Grow Light",
        )

    @property
    def native_value(self):
        entity_id = self._data.grow_lights[self._grow_light_id].light_entity_id
        if not entity_id or not self.hass:
            return "No light source configured"
        state = self.hass.states.get(entity_id)
        if not state:
            return "No light source configured"
        raw = state.state.lower()
        if raw == "on":
            return "Light is on"
        if raw == "off":
            return "Light is off"
        if raw == "unavailable":
            return "Light device unavailable"
        return raw

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.grow_lights[self._grow_light_id].light_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)


# ---------------------------------------------------------------------------
# Humidifier sensors
# ---------------------------------------------------------------------------


class HumidifierStateSensor(SensorEntity):
    """Sensor mirroring the humidifier device state."""

    def __init__(self, data: HumidifiersData, humidifier_id: str) -> None:
        self._data = data
        self._humidifier_id = humidifier_id
        hd = data.humidifiers[humidifier_id]
        self._attr_name = f"{hd.name} State"
        self._attr_unique_id = f"humidifier_{humidifier_id}_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"humidifier_{humidifier_id}")},
            name=hd.name,
            manufacturer="Custom",
            model="Humidifier",
        )

    @property
    def native_value(self):
        entity_id = self._data.humidifiers[self._humidifier_id].humidifier_entity_id
        if not entity_id or not self.hass:
            return "No humidifier source configured"
        state = self.hass.states.get(entity_id)
        if not state:
            return "No humidifier source configured"
        raw = state.state.lower()
        if raw == "on":
            return "Humidifier is on"
        if raw == "off":
            return "Humidifier is off"
        if raw == "unavailable":
            return "Humidifier device unavailable"
        return raw

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.humidifiers[self._humidifier_id].humidifier_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)


# ---------------------------------------------------------------------------
# Thermostat sensors
# ---------------------------------------------------------------------------


class ThermostatStateSensor(SensorEntity):
    """Sensor mirroring the thermostat climate entity state."""

    def __init__(self, data: ThermostatsData, thermostat_id: str) -> None:
        self._data = data
        self._thermostat_id = thermostat_id
        td = data.thermostats[thermostat_id]
        self._attr_name = f"{td.name} State"
        self._attr_unique_id = f"thermostat_{thermostat_id}_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"thermostat_{thermostat_id}")},
            name=td.name,
            manufacturer="Custom",
            model="Thermostat",
        )

    @property
    def native_value(self):
        entity_id = self._data.thermostats[self._thermostat_id].climate_entity_id
        if not entity_id or not self.hass:
            return "No thermostat configured"
        state = self.hass.states.get(entity_id)
        if not state:
            return "No thermostat configured"
        if state.state == "unavailable":
            return "Thermostat unavailable"
        attrs = state.attributes
        current = attrs.get("current_temperature")
        action = attrs.get("hvac_action", state.state)
        if current is not None:
            return f"{current}°F | {action}"
        return action

    @property
    def extra_state_attributes(self) -> dict:
        entity_id = self._data.thermostats[self._thermostat_id].climate_entity_id
        if not entity_id or not self.hass:
            return {"climate_entity_id": entity_id}
        state = self.hass.states.get(entity_id)
        if not state:
            return {"climate_entity_id": entity_id}
        attrs = state.attributes
        return {
            "climate_entity_id": entity_id,
            "hvac_mode": state.state,
            "hvac_action": attrs.get("hvac_action"),
            "current_temperature": attrs.get("current_temperature"),
            "target_temperature": attrs.get("temperature"),
            "min_temp": attrs.get("min_temp"),
            "max_temp": attrs.get("max_temp"),
            "hvac_modes": attrs.get("hvac_modes"),
        }

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.thermostats[self._thermostat_id].climate_entity_id
        if not entity_id:
            return

        @callback
        def _handle_state_change(event) -> None:
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)

        @callback
        def _refresh(_now) -> None:
            self.async_write_ha_state()

        async_call_later(self.hass, 5, _refresh)


# ---------------------------------------------------------------------------
# AutoWaterer sensors
# ---------------------------------------------------------------------------


class AutoWatererStateSensor(SensorEntity):
    """Sensor mirroring the auto waterer valve/switch state.

    When state changes to ON (watering starts), fires the auto_watering event
    on every plant listed in this waterer's plant_ids.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        data: AutoWaterersData,
        waterer_id: str,
    ) -> None:
        self._hass = hass
        self._data = data
        self._waterer_id = waterer_id
        aw = data.auto_waterers[waterer_id]
        self._attr_name = f"{aw.name} State"
        self._attr_unique_id = f"auto_waterer_{waterer_id}_state"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"auto_waterer_{waterer_id}")},
            name=aw.name,
            manufacturer="Custom",
            model="Auto Waterer",
        )
        self._previous_on: bool = False

    @property
    def native_value(self):
        entity_id = self._data.auto_waterers[self._waterer_id].water_entity_id
        if not entity_id or not self.hass:
            return "No water source configured"
        state = self.hass.states.get(entity_id)
        if not state:
            return "No water source configured"
        raw = state.state.lower()
        if raw in ("on", "open", "opening"):
            return "Watering"
        if raw in ("off", "closed", "closing"):
            return "Not watering"
        if raw == "unavailable":
            return "Device unavailable"
        return raw

    def _is_currently_on(self) -> bool:
        entity_id = self._data.auto_waterers[self._waterer_id].water_entity_id
        if not entity_id:
            return False
        state = self._hass.states.get(entity_id)
        if not state:
            return False
        return state.state.lower() in ("on", "open", "opening")

    def _fire_auto_watering_events(self) -> None:
        """Fire PlantAutoWateringEvent for all plants linked to this waterer."""
        aw = self._data.auto_waterers[self._waterer_id]
        for entry_data in self._hass.data.get(DOMAIN, {}).values():
            if not isinstance(entry_data, dict):
                continue
            if entry_data.get("type") != "plants":
                continue
            plants_data: PlantsData = entry_data["data"]
            for plant_id in aw.plant_ids:
                if plant_id not in plants_data.plants:
                    continue
                # Find and fire the PlantAutoWateringEvent entity.
                from homeassistant.helpers import entity_registry as er
                entity_registry = er.async_get(self._hass)
                event_entity_id = entity_registry.async_get_entity_id(
                    "event",
                    DOMAIN,
                    f"plant_{plant_id}_auto_watering",
                )
                if not event_entity_id:
                    continue
                for component in self._hass.data.get("entity_components", {}).values():
                    for candidate in getattr(component, "entities", []):
                        if getattr(candidate, "entity_id", None) == event_entity_id:
                            if hasattr(candidate, "record_auto_watering"):
                                candidate.record_auto_watering(
                                    waterer_name=aw.name
                                )
                            break

    async def async_added_to_hass(self) -> None:
        entity_id = self._data.auto_waterers[self._waterer_id].water_entity_id
        if not entity_id:
            return

        # Record current state so we can detect transitions.
        self._previous_on = self._is_currently_on()

        @callback
        def _handle_state_change(event) -> None:
            currently_on = self._is_currently_on()
            if currently_on and not self._previous_on:
                # Transition to ON — watering started.
                self._fire_auto_watering_events()
            self._previous_on = currently_on
            self.async_write_ha_state()

        async_track_state_change_event(self.hass, [entity_id], _handle_state_change)


# ---------------------------------------------------------------------------
# MeterLocation sensors
# ---------------------------------------------------------------------------


class LocationAirHumiditySensor(SensorEntity):
    """Sensor mirroring the configured air humidity meter for a location."""

    def __init__(self, data: MeterLocationsData, location_id: str) -> None:
        self._data = data
        self._location_id = location_id
        location = data.meter_locations[location_id]
        self._attr_name = f"{location.name} Air Humidity Meter"
        self._attr_unique_id = f"meter_location_{location_id}_air_humidity"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"meter_location_{location_id}")},
            name=location.name,
            manufacturer="Custom",
            model="Meter Location",
        )

    @property
    def native_value(self):
        entity_id = self._data.meter_locations[
            self._location_id
        ].air_humidity_entity_id
        if not entity_id or not self.hass:
            return "No air humidity meter for this location."
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "No air humidity meter for this location."
        if _is_stale(state):
            return "Stale"
        try:
            return float(state.state)
        except ValueError:
            return state.state

    @property
    def native_unit_of_measurement(self):
        entity_id = self._data.meter_locations[
            self._location_id
        ].air_humidity_entity_id
        if not entity_id or not self.hass:
            return None
        state = self.hass.states.get(entity_id)
        if not state:
            return None
        return state.attributes.get("unit_of_measurement")

    @property
    def extra_state_attributes(self) -> dict:
        location = self._data.meter_locations[self._location_id]
        attrs: dict = {"air_humidity_entity_id": location.air_humidity_entity_id}
        if location.air_humidity_entity_id and self.hass:
            state = self.hass.states.get(location.air_humidity_entity_id)
            if state is not None:
                attrs["is_stale"] = _is_stale(state)
                attrs["source_last_updated"] = state.last_updated.isoformat()
        return attrs


class LocationAirTemperatureSensor(SensorEntity):
    """Sensor mirroring the configured air temperature meter for a location."""

    def __init__(self, data: MeterLocationsData, location_id: str) -> None:
        self._data = data
        self._location_id = location_id
        location = data.meter_locations[location_id]
        self._attr_name = f"{location.name} Air Temperature Meter"
        self._attr_unique_id = f"meter_location_{location_id}_air_temperature"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"meter_location_{location_id}")},
            name=location.name,
            manufacturer="Custom",
            model="Meter Location",
        )

    @property
    def native_value(self):
        entity_id = self._data.meter_locations[
            self._location_id
        ].air_temperature_entity_id
        if not entity_id or not self.hass:
            return "No air temperature meter for this location."
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return "No air temperature meter for this location."
        if _is_stale(state):
            return "Stale"
        try:
            return float(state.state)
        except ValueError:
            return state.state

    @property
    def native_unit_of_measurement(self):
        entity_id = self._data.meter_locations[
            self._location_id
        ].air_temperature_entity_id
        if not entity_id or not self.hass:
            return None
        state = self.hass.states.get(entity_id)
        if not state:
            return None
        return state.attributes.get("unit_of_measurement")

    @property
    def extra_state_attributes(self) -> dict:
        location = self._data.meter_locations[self._location_id]
        attrs: dict = {"air_temperature_entity_id": location.air_temperature_entity_id}
        if location.air_temperature_entity_id and self.hass:
            state = self.hass.states.get(location.air_temperature_entity_id)
            if state is not None:
                attrs["is_stale"] = _is_stale(state)
                attrs["source_last_updated"] = state.last_updated.isoformat()
        return attrs


# ---------------------------------------------------------------------------
# Agent Log sensors (issues + actions)
# ---------------------------------------------------------------------------


class AgentLogSensor(SensorEntity):
    """Sensor storing agent log data in attributes — no length limit."""

    _attr_has_entity_name = True
    _attr_entity_category = None

    def __init__(
        self,
        store: Store,
        field_key: str,
        entity_name: str,
        icon: str,
        initial_data: dict,
    ) -> None:
        self._store = store
        self._field_key = field_key
        self._items: list[str] = self._parse(initial_data.get(field_key, ""))
        self._attr_name = entity_name
        self._attr_unique_id = f"agent_log_{field_key}_sensor"
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "agent_log")},
            name="Agent Log",
            manufacturer="Custom",
            model="Agent Log",
        )

    @staticmethod
    def _parse(raw: str) -> list[str]:
        if not raw:
            return []
        try:
            import json
            return json.loads(raw)
        except Exception:
            return [line for line in raw.splitlines() if line.strip()]

    @property
    def native_value(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"{len(self._items)} items • {ts}"

    @property
    def extra_state_attributes(self) -> dict:
        import json
        return {"items": self._items, "raw": json.dumps(self._items)}

    async def async_update_items(self, items: list[str]) -> None:
        import json
        self._items = items
        raw = await self._store.async_load() or {}
        raw[self._field_key] = json.dumps(items)
        await self._store.async_save(raw)
        self.async_write_ha_state()
