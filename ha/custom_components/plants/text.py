"""Text platform for Plants recommendations and device nearby-plants config."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .data import MeterLocationsData, PlantsData

STORAGE_AGENT_LOG = "plants_agent_log"

MAX_RECOMMENDATION_LENGTH = 120

# Format: (field_key, entity_name, friendly_name_with_example, max_length)
FIELDS: list[tuple[str, str, str, int | None]] = [
    (
        "other_recommendations",
        "Other Recommendations",
        "Other Recommendations (e.g., - rotate weekly; - avoid drafts;)",
        None,
    ),
    (
        "todo_list",
        "Todo List",
        "Todo List (e.g., - repot in spring; - prune dry leaves;)",
        None,
    ),
]

LOCATION_FIELDS: list[tuple[str, str, int | None]] = [
    ("description", "Location Description", None),
    ("comments", "Location Comments", None),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants text entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    entry_type = entry_data["type"]
    data = entry_data["data"]
    entities: list[TextEntity] = []

    if entry_type == "meter_locations":
        for location_id in data.meter_locations:
            for field_key, label, max_length in LOCATION_FIELDS:
                entities.append(
                    LocationNoteText(data, location_id, field_key, label, max_length)
                )
    elif entry_type in ("grow_lights", "humidifiers", "auto_waterers"):
        pass  # plant slots handled by select platform
    elif entry_type == "agent_log":
        store = Store(hass, 1, STORAGE_AGENT_LOG)
        raw = await store.async_load() or {}
        entities.append(AgentLogText(hass, store, "plant_check_issues", "Plant Check Issues", raw))
        entities.append(AgentLogText(hass, store, "plant_check_actions", "Plant Check Actions", raw))
    else:
        # plants
        for plant_id in data.plants:
            for field_key, entity_name, friendly_name, max_length in FIELDS:
                entities.append(
                    PlantRecommendationText(
                        data, plant_id, field_key, entity_name, friendly_name, max_length
                    )
                )
            entities.append(PlantCustomEventNoteText(data, plant_id))

    if entities:
        async_add_entities(entities)


# ---------------------------------------------------------------------------
# Plant recommendation texts (unchanged)
# ---------------------------------------------------------------------------


class PlantRecommendationText(TextEntity):
    """Text entity for plant recommendations."""

    _attr_has_entity_name = True

    def __init__(
        self,
        data: PlantsData,
        plant_id: str,
        field_key: str,
        entity_name: str,
        friendly_name: str,
        max_length: int | None,
    ) -> None:
        self._data = data
        self._plant_id = plant_id
        self._field_key = field_key
        plant = data.plants[plant_id]
        self._attr_name = entity_name
        self._attr_extra_state_attributes = {
            "example": friendly_name.split("(e.g., ")[-1].rstrip(")")
            if "(e.g., " in friendly_name
            else None
        }
        self._attr_unique_id = f"plant_{plant_id}_{field_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if max_length is not None:
            self._attr_native_max = max_length

    @property
    def native_value(self) -> str:
        value = getattr(self._data.plants[self._plant_id], self._field_key)
        return value or ""

    async def async_set_value(self, value: str) -> None:
        setattr(self._data.plants[self._plant_id], self._field_key, value)
        await self._data.async_save()
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Custom event note text (input for Add Custom Event button)
# ---------------------------------------------------------------------------


class PlantCustomEventNoteText(TextEntity):
    """Text entity for logging a custom plant care event.

    Saving a non-empty value fires the custom event and clears the field.
    """

    _attr_has_entity_name = True

    def __init__(self, data: PlantsData, plant_id: str) -> None:
        self._data = data
        self._plant_id = plant_id
        plant = data.plants[plant_id]
        self._attr_name = "Log Custom Event"
        self._attr_unique_id = f"plant_{plant_id}_custom_event_note"
        self._attr_icon = "mdi:note-plus"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._note: str = ""

    @property
    def native_value(self) -> str:
        return self._note

    async def async_set_value(self, value: str) -> None:
        note = value.strip()
        if not note:
            return
        event_entity = self._data.custom_event_entities.get(self._plant_id)
        if event_entity:
            plant_name = self._data.plants[self._plant_id].name
            event_entity.record_custom_event(
                hass=self.hass,
                plant_name=plant_name,
                notes=note,
            )
        self._note = ""
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# GrowLight / Humidifier / AutoWaterer nearby-plants texts
# ---------------------------------------------------------------------------
# MeterLocation note texts
# ---------------------------------------------------------------------------


class LocationNoteText(TextEntity):
    """Text entity for meter location notes."""

    def __init__(
        self,
        data: MeterLocationsData,
        location_id: str,
        field_key: str,
        label: str,
        max_length: int | None,
    ) -> None:
        self._data = data
        self._location_id = location_id
        self._field_key = field_key
        location = data.meter_locations[location_id]
        self._attr_name = f"{location.name} {label}"
        self._attr_unique_id = f"meter_location_{location_id}_{field_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"meter_location_{location_id}")},
            name=location.name,
            manufacturer="Custom",
            model="Meter Location",
        )
        self._attr_entity_category = EntityCategory.CONFIG
        if max_length is not None:
            self._attr_native_max = max_length

    @property
    def native_value(self) -> str:
        value = getattr(self._data.meter_locations[self._location_id], self._field_key)
        return value or ""

    async def async_set_value(self, value: str) -> None:
        location = self._data.meter_locations[self._location_id]
        setattr(location, self._field_key, value)
        await self._data.async_save()
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Agent Log texts (plant_check_issues, plant_check_actions)
# ---------------------------------------------------------------------------


class AgentLogText(TextEntity):
    """Text entity for agent log fields — writable via HA API by the runner."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        store: Store,
        field_key: str,
        entity_name: str,
        initial_data: dict,
    ) -> None:
        self._hass = hass
        self._store = store
        self._field_key = field_key
        self._value: str = initial_data.get(field_key, "")
        self._attr_name = entity_name
        self._attr_unique_id = f"agent_log_{field_key}"
        self._attr_icon = "mdi:robot" if field_key == "plant_check_actions" else "mdi:alert-circle-outline"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "agent_log")},
            name="Agent Log",
            manufacturer="Custom",
            model="Agent Log",
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_max = 1000

    @property
    def native_value(self) -> str:
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        raw = await self._store.async_load() or {}
        raw[self._field_key] = value
        await self._store.async_save(raw)
        self.async_write_ha_state()
