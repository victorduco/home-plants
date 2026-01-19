"""Plants integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN, PLATFORMS
from .data import PlantsData

SERVICE_ADD_PLANT = "add_plant"
SERVICE_REMOVE_PLANT = "remove_plant"
SERVICE_ADD_LAMP = "add_lamp"
SERVICE_REMOVE_LAMP = "remove_lamp"
SERVICE_LINK_LAMP_PLANTS = "link_lamp_plants"
SERVICE_SET_LAMP_OUTLET = "set_lamp_outlet"

SERVICE_ENTRY_ID = "entry_id"
SERVICE_NAME = "name"
SERVICE_PLANT_ID = "plant_id"
SERVICE_LAMP_ID = "lamp_id"
SERVICE_OUTLET_ENTITY_ID = "outlet_entity_id"
SERVICE_SOIL_MOISTURE = "soil_moisture"
SERVICE_LOCATION_X = "location_x"
SERVICE_LOCATION_Y = "location_y"
SERVICE_POSITION_X = "position_x"
SERVICE_POSITION_Y = "position_y"
SERVICE_PLANT_IDS = "plant_ids"

PLANT_ADD_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_ENTRY_ID): str,
        vol.Required(SERVICE_NAME): str,
        vol.Optional(SERVICE_SOIL_MOISTURE): vol.Coerce(float),
        vol.Optional(SERVICE_LOCATION_X): vol.Coerce(float),
        vol.Optional(SERVICE_LOCATION_Y): vol.Coerce(float),
    }
)

PLANT_REMOVE_SCHEMA = vol.Schema(
    {vol.Optional(SERVICE_ENTRY_ID): str, vol.Required(SERVICE_PLANT_ID): str}
)

LAMP_ADD_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_ENTRY_ID): str,
        vol.Required(SERVICE_NAME): str,
        vol.Optional(SERVICE_OUTLET_ENTITY_ID): str,
        vol.Optional(SERVICE_POSITION_X): vol.Coerce(float),
        vol.Optional(SERVICE_POSITION_Y): vol.Coerce(float),
        vol.Optional(SERVICE_PLANT_IDS): [str],
    }
)

LAMP_REMOVE_SCHEMA = vol.Schema(
    {vol.Optional(SERVICE_ENTRY_ID): str, vol.Required(SERVICE_LAMP_ID): str}
)

LAMP_LINK_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_ENTRY_ID): str,
        vol.Required(SERVICE_LAMP_ID): str,
        vol.Required(SERVICE_PLANT_IDS): [str],
    }
)

LAMP_OUTLET_SCHEMA = vol.Schema(
    {
        vol.Optional(SERVICE_ENTRY_ID): str,
        vol.Required(SERVICE_LAMP_ID): str,
        vol.Required(SERVICE_OUTLET_ENTITY_ID): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Plants from a config entry."""
    hass.data.setdefault(DOMAIN, {"entries": {}, "services_registered": False})
    hass.data[DOMAIN]["entries"][entry.entry_id] = await PlantsData.async_load(
        hass, entry.entry_id, entry.data.get("name")
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.data[DOMAIN]["services_registered"]:
        _register_services(hass)
        hass.data[DOMAIN]["services_registered"] = True

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Plants config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN]["entries"].pop(entry.entry_id, None)
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def _resolve_entry(call_data: dict) -> ConfigEntry:
        entry_id = call_data.get(SERVICE_ENTRY_ID)
        if entry_id:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="entry_not_found",
                )
            return entry
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
            )
        return entries[0]

    async def _handle_add_plant(call):
        entry = await _resolve_entry(call.data)
        data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
        data.add_plant(
            name=call.data[SERVICE_NAME],
            soil_moisture=call.data.get(SERVICE_SOIL_MOISTURE),
            location_x=call.data.get(SERVICE_LOCATION_X),
            location_y=call.data.get(SERVICE_LOCATION_Y),
        )
        await data.async_save()
        await hass.config_entries.async_reload(entry.entry_id)

    async def _handle_remove_plant(call):
        entry = await _resolve_entry(call.data)
        data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
        removed = data.remove_plant(call.data[SERVICE_PLANT_ID])
        if not removed:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="plant_not_found",
            )
        await data.async_save()
        await hass.config_entries.async_reload(entry.entry_id)

    async def _handle_add_lamp(call):
        entry = await _resolve_entry(call.data)
        data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
        plant_ids = [
            plant_id
            for plant_id in call.data.get(SERVICE_PLANT_IDS, [])
            if plant_id in data.plants
        ]
        data.add_lamp(
            name=call.data[SERVICE_NAME],
            outlet_entity_id=call.data.get(SERVICE_OUTLET_ENTITY_ID),
            position_x=call.data.get(SERVICE_POSITION_X),
            position_y=call.data.get(SERVICE_POSITION_Y),
            plant_ids=plant_ids,
        )
        await data.async_save()
        await hass.config_entries.async_reload(entry.entry_id)

    async def _handle_remove_lamp(call):
        entry = await _resolve_entry(call.data)
        data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
        removed = data.remove_lamp(call.data[SERVICE_LAMP_ID])
        if not removed:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="lamp_not_found",
            )
        await data.async_save()
        await hass.config_entries.async_reload(entry.entry_id)

    async def _handle_link_lamp_plants(call):
        entry = await _resolve_entry(call.data)
        data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
        plant_ids = [
            plant_id
            for plant_id in call.data.get(SERVICE_PLANT_IDS, [])
            if plant_id in data.plants
        ]
        if call.data[SERVICE_LAMP_ID] not in data.lamps:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="lamp_not_found",
            )
        data.link_lamp_plants(call.data[SERVICE_LAMP_ID], plant_ids)
        await data.async_save()
        await hass.config_entries.async_reload(entry.entry_id)

    async def _handle_set_lamp_outlet(call):
        entry = await _resolve_entry(call.data)
        data: PlantsData = hass.data[DOMAIN]["entries"][entry.entry_id]
        if call.data[SERVICE_LAMP_ID] not in data.lamps:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="lamp_not_found",
            )
        data.set_lamp_outlet(
            call.data[SERVICE_LAMP_ID], call.data[SERVICE_OUTLET_ENTITY_ID]
        )
        await data.async_save()
        await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PLANT,
        _handle_add_plant,
        schema=PLANT_ADD_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_PLANT,
        _handle_remove_plant,
        schema=PLANT_REMOVE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_LAMP,
        _handle_add_lamp,
        schema=LAMP_ADD_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_LAMP,
        _handle_remove_lamp,
        schema=LAMP_REMOVE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LINK_LAMP_PLANTS,
        _handle_link_lamp_plants,
        schema=LAMP_LINK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_LAMP_OUTLET,
        _handle_set_lamp_outlet,
        schema=LAMP_OUTLET_SCHEMA,
    )
