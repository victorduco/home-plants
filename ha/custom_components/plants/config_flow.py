"""Config flow for Plants."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN
from .data import MeterLocationsData, PlantsData


class PlantsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Plants."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        entry_type = config_entry.data.get("entry_type", "plants")
        if entry_type == "meter_locations":
            return MeterLocationsOptionsFlow()
        return PlantsOptionsFlow()

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required("entry_type"): vol.In(
                        {
                            "plants": "Plants",
                            "meter_locations": "Meter Locations",
                        }
                    )
                }
            )
            return self.async_show_form(step_id="user", data_schema=schema)
        entry_type = user_input["entry_type"]
        for existing in self._async_current_entries():
            if existing.data.get("entry_type", "plants") == entry_type:
                reason = (
                    "plants_instance_allowed"
                    if entry_type == "plants"
                    else "meter_locations_instance_allowed"
                )
                return self.async_abort(reason=reason)
        title = "Plants" if entry_type == "plants" else "Meter Locations"
        return self.async_create_entry(title=title, data={"entry_type": entry_type})


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
            data: PlantsData = self.hass.data[DOMAIN][self.config_entry.entry_id][
                "data"
            ]
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
        data: PlantsData = self.hass.data[DOMAIN][self.config_entry.entry_id]["data"]
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
        data: PlantsData = self.hass.data[DOMAIN][self.config_entry.entry_id]["data"]
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
        data: PlantsData = self.hass.data[DOMAIN][self.config_entry.entry_id]["data"]
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
                    selector.EntitySelectorConfig(domain=["switch"])
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


class MeterLocationsOptionsFlow(config_entries.OptionsFlow):
    """Handle meter location options."""

    async def async_step_init(self, user_input=None):
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_meter_location",
                "remove_meter_location",
            ],
        )

    async def async_step_add_meter_location(self, user_input=None):
        """Add a meter location device."""
        if user_input is not None:
            air_temperature = user_input.get("air_temperature_entity_id")
            air_humidity = user_input.get("air_humidity_entity_id")
            if not air_temperature and not air_humidity:
                return self.async_show_form(
                    step_id="add_meter_location",
                    data_schema=self._meter_location_schema(),
                    errors={"base": "select_at_least_one"},
                )
            data: MeterLocationsData = self.hass.data[DOMAIN][
                self.config_entry.entry_id
            ]["data"]
            data.add_meter_location(
                name=user_input["name"],
                air_temperature_entity_id=air_temperature,
                air_humidity_entity_id=air_humidity,
                description=user_input.get("description"),
                comments=user_input.get("comments"),
            )
            await data.async_save()
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="add_meter_location",
            data_schema=self._meter_location_schema(),
        )

    async def async_step_remove_meter_location(self, user_input=None):
        """Remove a meter location device."""
        data: MeterLocationsData = self.hass.data[DOMAIN][self.config_entry.entry_id][
            "data"
        ]
        labels, label_to_id = self._meter_location_label_maps(data)

        if user_input is not None:
            label = user_input["location_label"]
            location_id = label_to_id.get(label)
            if location_id:
                data.remove_meter_location(location_id)
                await data.async_save()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("location_label"): vol.In(labels),
            }
        )
        return self.async_show_form(
            step_id="remove_meter_location",
            data_schema=schema,
        )

    @staticmethod
    def _meter_location_label_maps(
        data: MeterLocationsData,
    ) -> tuple[list[str], dict[str, str]]:
        labels: list[str] = []
        label_to_id: dict[str, str] = {}
        for location_id, location in data.meter_locations.items():
            label = location.name
            labels.append(label)
            label_to_id[label] = location_id
        labels.sort()
        return labels, label_to_id

    @staticmethod
    def _meter_location_schema() -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("air_temperature_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "number", "input_number"]
                    )
                ),
                vol.Optional("air_humidity_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "number", "input_number"]
                    )
                ),
                vol.Optional("description"): str,
                vol.Optional("comments"): str,
            }
        )
