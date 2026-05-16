"""Plants integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .data import (
    AutoWaterersData,
    GrowLightsData,
    HumidifiersData,
    MeterLocationsData,
    PlantsData,
    ThermostatsData,
)

# Legacy unique_id suffixes that must be removed on upgrade.
# Format: { entity_domain: (suffix, ...) }
LEGACY_ENTITY_SUFFIXES: dict[str, tuple[str, ...]] = {
    "sensor": (
        "light_device",
        "auto_watering_device",
        "moisture_device",
        "humidifier_device",
        "moisture_state",
        "last_manual_watering",
        # Removed plant-level device sensors (moved to dedicated device entries)
        "light_state",
        "humidifier_state",
    ),
    "switch": (
        "moisture_device_control",
        "water_power",
        # Removed plant-level proxy switches
        "light_power",
        "humidifier_control",
        "auto_watering_control",
    ),
    "select": (
        # Removed plant-level device selects
        "light_outlet",
        "water_outlet",
        "humidifier_source",
    ),
    "text": ("manual_watering_comment",),
    "button": (
        "custom_event_note",
        "custom_event",
        "add_custom_event",
        "custom_event_button",
    ),
}


def _cleanup_legacy_entities(
    entity_registry: er.EntityRegistry,
    plant_id: str,
) -> None:
    """Remove legacy entities for a given plant_id."""
    # Remove entities with known legacy unique_id suffixes.
    for domain, suffixes in LEGACY_ENTITY_SUFFIXES.items():
        for suffix in suffixes:
            unique_id = f"plant_{plant_id}_{suffix}"
            entity_id = entity_registry.async_get_entity_id(domain, DOMAIN, unique_id)
            if entity_id:
                entity_registry.async_remove(entity_id)

    # Remove any surviving valve entities (migrated back to switch platform).
    for unique_id_suffix in ("water_power", "auto_watering_control"):
        unique_id = f"plant_{plant_id}_{unique_id_suffix}"
        valve_entity_id = entity_registry.async_get_entity_id(
            "valve",
            DOMAIN,
            unique_id,
        )
        if valve_entity_id:
            entity_registry.async_remove(valve_entity_id)

    # Remove old text entities whose entity_id was generated with example text.
    old_recommendation_patterns = [
        "_recommendation_e_g_",
        "_todo_list_e_g_",
        "_other_recommendations_e_g_",
    ]
    for entry in list(entity_registry.entities.values()):
        if entry.platform != DOMAIN:
            continue
        if not entry.entity_id.startswith("text."):
            continue
        should_remove = any(
            pattern in entry.entity_id for pattern in old_recommendation_patterns
        )
        if entry.unique_id and entry.unique_id.startswith("plant_") and (
            "_recommendation" in entry.unique_id
            or "todo_list" in entry.unique_id
            or "other_recommendations" in entry.unique_id
        ):
            should_remove = True
        if should_remove:
            entity_registry.async_remove(entry.entity_id)

    # Remove old manual watering switch entities (migrated to event platform).
    manual_watering_switch_id = f"plant_{plant_id}_manual_watering"
    old_manual_switch = entity_registry.async_get_entity_id(
        "switch",
        DOMAIN,
        manual_watering_switch_id,
    )
    if old_manual_switch:
        entity_registry.async_remove(old_manual_switch)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Plants from a config entry."""
    entry_type = entry.data.get("entry_type", "plants")
    hass.data.setdefault(DOMAIN, {})
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    if entry_type == "meter_locations":
        data = await MeterLocationsData.async_load(hass)
        hass.data[DOMAIN][entry.entry_id] = {"type": entry_type, "data": data}
        for location in data.meter_locations.values():
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"meter_location_{location.location_id}")},
                name=location.name,
                manufacturer="Custom",
                model="Meter Location",
            )

    elif entry_type == "grow_lights":
        data = await GrowLightsData.async_load(hass)
        hass.data[DOMAIN][entry.entry_id] = {"type": entry_type, "data": data}
        for gl in data.grow_lights.values():
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"grow_light_{gl.grow_light_id}")},
                name=gl.name,
                manufacturer="Custom",
                model="Grow Light",
            )

    elif entry_type == "humidifiers":
        data = await HumidifiersData.async_load(hass)
        hass.data[DOMAIN][entry.entry_id] = {"type": entry_type, "data": data}
        for hd in data.humidifiers.values():
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"humidifier_{hd.humidifier_id}")},
                name=hd.name,
                manufacturer="Custom",
                model="Humidifier",
            )

    elif entry_type == "thermostats":
        data = await ThermostatsData.async_load(hass)
        hass.data[DOMAIN][entry.entry_id] = {"type": entry_type, "data": data}
        for td in data.thermostats.values():
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"thermostat_{td.thermostat_id}")},
                name=td.name,
                manufacturer="Custom",
                model="Thermostat",
            )

    elif entry_type == "auto_waterers":
        data = await AutoWaterersData.async_load(hass)
        hass.data[DOMAIN][entry.entry_id] = {"type": entry_type, "data": data}
        for aw in data.auto_waterers.values():
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"auto_waterer_{aw.waterer_id}")},
                name=aw.name,
                manufacturer="Custom",
                model="Auto Waterer",
            )

    elif entry_type == "agent_log":
        hass.data[DOMAIN][entry.entry_id] = {"type": entry_type, "data": None}
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, "agent_log")},
            name="Agent Log",
            manufacturer="Custom",
            model="Agent Log",
        )


    else:
        # plants (default)
        data = await PlantsData.async_load(hass)
        hass.data[DOMAIN][entry.entry_id] = {"type": "plants", "data": data}
        known_identifiers = {
            (DOMAIN, f"plant_{plant.plant_id}") for plant in data.plants.values()
        }
        for device in list(device_registry.devices.values()):
            if entry.entry_id not in device.config_entries:
                continue
            if any(id in known_identifiers for id in device.identifiers):
                continue
            for entity_entry in er.async_entries_for_device(
                entity_registry, device.id, include_disabled_entities=True
            ):
                entity_registry.async_remove(entity_entry.entity_id)
            device_registry.async_remove_device(device.id)

        for plant in data.plants.values():
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"plant_{plant.plant_id}")},
                name=plant.name,
                manufacturer="Custom",
                model="Plant",
            )
            _cleanup_legacy_entities(entity_registry, plant.plant_id)

        # Always re-register services so the closure captures the current entry
        # after a reload (stale entry reference would silently do nothing).
        async def async_handle_add(call) -> None:
            await _handle_add_plant(hass, entry, call)

        hass.services.async_register(
            DOMAIN,
            "add_plant",
            async_handle_add,
            schema=vol.Schema(
                {
                    vol.Required("name"): cv.string,
                    vol.Optional("moisture_entity_id"): cv.entity_id,
                }
            ),
        )

        async def async_handle_remove(call) -> None:
            await _handle_remove_plant(hass, entry, call)

        hass.services.async_register(
            DOMAIN,
            "remove_plant",
            async_handle_remove,
            schema=vol.Schema(
                {
                    vol.Required("name"): cv.string,
                }
            ),
        )

        async def async_handle_record_watering(call) -> None:
            await _handle_record_watering(hass, entry, call)

        hass.services.async_register(
            DOMAIN,
            "record_watering",
            async_handle_record_watering,
            schema=vol.Schema(
                {
                    vol.Required("plant"): cv.string,
                    vol.Optional("duration_minutes"): cv.positive_int,
                    vol.Optional("amount_ml"): cv.positive_int,
                    vol.Optional("notes"): cv.string,
                }
            ),
        )

        async def async_handle_record_shower(call) -> None:
            await _handle_record_shower(hass, entry, call)

        hass.services.async_register(
            DOMAIN,
            "record_shower",
            async_handle_record_shower,
            schema=vol.Schema(
                {
                    vol.Required("plant"): cv.string,
                    vol.Optional("duration_minutes"): cv.positive_int,
                    vol.Optional("notes"): cv.string,
                }
            ),
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Plants config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


# ---------------------------------------------------------------------------
# Service handlers
# ---------------------------------------------------------------------------


async def _handle_add_plant(
    hass: HomeAssistant,
    entry: ConfigEntry,
    call,
) -> None:
    data: PlantsData = hass.data[DOMAIN][entry.entry_id]["data"]
    data.add_plant(
        name=call.data["name"],
        moisture_entity_id=call.data.get("moisture_entity_id"),
    )
    await data.async_save()
    await hass.config_entries.async_reload(entry.entry_id)


async def _handle_remove_plant(
    hass: HomeAssistant,
    entry: ConfigEntry,
    call,
) -> None:
    data: PlantsData = hass.data[DOMAIN][entry.entry_id]["data"]
    name = call.data["name"].strip().lower()
    plant_id = None
    for pid, plant in data.plants.items():
        if plant.name.lower() == name:
            plant_id = pid
            break
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    if plant_id:
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, f"plant_{plant_id}")}
        )
        if device:
            for entry_item in er.async_entries_for_device(
                entity_registry,
                device.id,
                include_disabled_entities=True,
            ):
                entity_registry.async_remove(entry_item.entity_id)
            device_registry.async_remove_device(device.id)
        data.remove_plant(plant_id)
        await data.async_save()
        await hass.config_entries.async_reload(entry.entry_id)
        return

    # If storage is already missing the plant, still clean stale registry entries.
    for device in device_registry.devices.values():
        if device.name and device.name.lower() == name:
            if any(identifier[0] == DOMAIN for identifier in device.identifiers):
                for entry_item in er.async_entries_for_device(
                    entity_registry,
                    device.id,
                    include_disabled_entities=True,
                ):
                    entity_registry.async_remove(entry_item.entity_id)
                device_registry.async_remove_device(device.id)


async def _handle_record_watering(
    hass: HomeAssistant,
    entry: ConfigEntry,
    call,
) -> None:
    """Handle recording a manual watering event."""
    data: PlantsData = hass.data[DOMAIN][entry.entry_id]["data"]
    plant_name = call.data["plant"].strip().lower()
    plant_id = None
    for pid, plant in data.plants.items():
        if plant.name.lower() == plant_name:
            plant_id = pid
            break
    if not plant_id:
        return

    entity_registry = er.async_get(hass)
    event_entity_id = entity_registry.async_get_entity_id(
        "event",
        DOMAIN,
        f"plant_{plant_id}_manual_watering",
    )
    if not event_entity_id:
        return

    entity = None
    for component in hass.data.get("entity_components", {}).values():
        for candidate in getattr(component, "entities", []):
            if getattr(candidate, "entity_id", None) == event_entity_id:
                entity = candidate
                break
        if entity is not None:
            break

    if entity and hasattr(entity, "record_watering"):
        entity.record_watering(
            duration_minutes=call.data.get("duration_minutes"),
            amount_ml=call.data.get("amount_ml"),
            notes=call.data.get("notes"),
        )


async def _handle_record_shower(
    hass: HomeAssistant,
    entry: ConfigEntry,
    call,
) -> None:
    """Handle recording a manual shower event."""
    data: PlantsData = hass.data[DOMAIN][entry.entry_id]["data"]
    plant_name = call.data["plant"].strip().lower()
    plant_id = None
    for pid, plant in data.plants.items():
        if plant.name.lower() == plant_name:
            plant_id = pid
            break
    if not plant_id:
        return

    entity_registry = er.async_get(hass)
    event_entity_id = entity_registry.async_get_entity_id(
        "event",
        DOMAIN,
        f"plant_{plant_id}_manual_shower",
    )
    if not event_entity_id:
        return

    entity = None
    for component in hass.data.get("entity_components", {}).values():
        for candidate in getattr(component, "entities", []):
            if getattr(candidate, "entity_id", None) == event_entity_id:
                entity = candidate
                break
        if entity is not None:
            break

    if entity and hasattr(entity, "record_shower"):
        entity.record_shower(
            duration_minutes=call.data.get("duration_minutes"),
            notes=call.data.get("notes"),
        )
