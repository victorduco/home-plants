"""Sensor platform for Plants."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .data import AutoWaterersData, GrowLightsData, HumidifiersData, MeterLocationsData, PlantsData


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
    elif entry_type == "auto_waterers":
        for waterer_id in data.auto_waterers:
            entities.append(AutoWatererStateSensor(hass, data, waterer_id))
    else:
        # plants
        for plant_id in data.plants:
            entities.append(PlantMoistureSensor(data, plant_id))
            entities.append(PlantHumiditySensor(data, plant_id))
            entities.append(PlantAirTemperatureSensor(data, plant_id))
            entities.append(PlantAutoWateringStateSensor(hass, data, plant_id))

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
        return {"air_humidity_entity_id": location.air_humidity_entity_id}


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
        return {"air_temperature_entity_id": location.air_temperature_entity_id}
