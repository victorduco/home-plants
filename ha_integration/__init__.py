"""Plants integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS
from .data import PlantsData


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Plants from a config entry."""
    data = await PlantsData.async_load(hass)
    hass.data.setdefault(DOMAIN, {})["data"] = data
    device_registry = dr.async_get(hass)
    for plant in data.plants.values():
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"plant_{plant.plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Plants config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data.pop(DOMAIN, None)
    return unload_ok
