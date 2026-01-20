"""Config flow for Plants."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN
from .data import PlantsData


class PlantsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Plants."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return PlantsOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(title="Plants", data={})


class PlantsOptionsFlow(config_entries.OptionsFlow):
    """Handle Plants options."""

    async def async_step_init(self, user_input=None):
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_plant",
                "remove_plant",
                "set_moisture_entity",
                "set_light_entity",
            ],
        )

    async def async_step_add_plant(self, user_input=None):
        """Add a plant device."""
        if user_input is not None:
            data: PlantsData = self.hass.data[DOMAIN]["data"]
            data.add_plant(
                name=user_input["name"],
                moisture_entity_id=user_input.get("moisture_entity_id"),
            )
            await data.async_save()
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("moisture_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(step_id="add_plant", data_schema=schema)

    async def async_step_remove_plant(self, user_input=None):
        """Remove a plant device."""
        data: PlantsData = self.hass.data[DOMAIN]["data"]
        plant_labels, plant_label_to_id = self._plant_label_maps(data)

        if user_input is not None:
            label = user_input["plant_label"]
            plant_id = plant_label_to_id.get(label)
            if plant_id:
                data.remove_plant(plant_id)
                await data.async_save()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("plant_label"): vol.In(plant_labels),
            }
        )
        return self.async_show_form(step_id="remove_plant", data_schema=schema)

    async def async_step_set_moisture_entity(self, user_input=None):
        """Set plant moisture entity."""
        data: PlantsData = self.hass.data[DOMAIN]["data"]
        plant_labels, plant_label_to_id = self._plant_label_maps(data)

        if user_input is not None:
            label = user_input["plant_label"]
            plant_id = plant_label_to_id.get(label)
            if plant_id:
                data.set_plant_moisture(
                    plant_id, user_input.get("moisture_entity_id")
                )
                await data.async_save()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("plant_label"): vol.In(plant_labels),
                vol.Optional("moisture_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(step_id="set_moisture_entity", data_schema=schema)

    async def async_step_set_light_entity(self, user_input=None):
        """Set plant light entity."""
        data: PlantsData = self.hass.data[DOMAIN]["data"]
        plant_labels, plant_label_to_id = self._plant_label_maps(data)

        if user_input is not None:
            label = user_input["plant_label"]
            plant_id = plant_label_to_id.get(label)
            if plant_id:
                data.set_plant_light(plant_id, user_input.get("light_entity_id"))
                await data.async_save()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("plant_label"): vol.In(plant_labels),
                vol.Optional("light_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["light", "switch"])
                ),
            }
        )
        return self.async_show_form(step_id="set_light_entity", data_schema=schema)

    @staticmethod
    def _plant_label_maps(data: PlantsData) -> tuple[list[str], dict[str, str]]:
        labels: list[str] = []
        label_to_id: dict[str, str] = {}
        for plant_id, plant in data.plants.items():
            label = plant.name
            labels.append(label)
            label_to_id[label] = plant_id
        labels.sort()
        return labels, label_to_id
