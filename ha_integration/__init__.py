"""Plants integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .data import PlantsData

LEGACY_ENTITY_SUFFIXES: dict[str, tuple[str, ...]] = {
    "sensor": (
        "light_device",
        "auto_watering_device",
        "moisture_device",
        "humidifier_device",
        "moisture_state",
    ),
    "switch": ("moisture_device_control",),
}


def _cleanup_legacy_entities(
    entity_registry: er.EntityRegistry,
    plant_id: str,
) -> None:
    for domain, suffixes in LEGACY_ENTITY_SUFFIXES.items():
        for suffix in suffixes:
            unique_id = f"plant_{plant_id}_{suffix}"
            entity_id = entity_registry.async_get_entity_id(domain, DOMAIN, unique_id)
            if entity_id:
                entity_registry.async_remove(entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Plants from a config entry."""
    data = await PlantsData.async_load(hass)
    hass.data.setdefault(DOMAIN, {})["data"] = data
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    for plant in data.plants.values():
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"plant_{plant.plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        _cleanup_legacy_entities(entity_registry, plant.plant_id)
    services = hass.services.async_services()
    if DOMAIN not in services or "add_plant" not in services[DOMAIN]:
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
    services = hass.services.async_services()
    if DOMAIN not in services or "remove_plant" not in services[DOMAIN]:
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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Plants config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data.pop(DOMAIN, None)
    return unload_ok


async def _handle_add_plant(
    hass: HomeAssistant,
    entry: ConfigEntry,
    call,
) -> None:
    data: PlantsData = hass.data[DOMAIN]["data"]
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
    data: PlantsData = hass.data[DOMAIN]["data"]
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
