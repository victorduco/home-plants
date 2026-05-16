"""Config flow for Plants."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN
from .data import (
    AutoWaterersData,
    GrowLightsData,
    HumidifiersData,
    MeterLocationsData,
    PlantsData,
    ThermostatsData,
)


class PlantsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Plants."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        entry_type = config_entry.data.get("entry_type", "plants")
        if entry_type == "meter_locations":
            return MeterLocationsOptionsFlow()
        if entry_type == "grow_lights":
            return GrowLightsOptionsFlow()
        if entry_type == "humidifiers":
            return HumidifiersOptionsFlow()
        if entry_type == "thermostats":
            return ThermostatsOptionsFlow()
        if entry_type == "auto_waterers":
            return AutoWaterersOptionsFlow()
        if entry_type == "agent_log":
            return AgentLogOptionsFlow()
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
                            "grow_lights": "Grow Lights",
                            "humidifiers": "Humidifiers",
                            "thermostats": "Thermostats",
                            "auto_waterers": "Auto Waterers",
                            "agent_log": "Agent Log",
                        }
                    )
                }
            )
            return self.async_show_form(step_id="user", data_schema=schema)
        entry_type = user_input["entry_type"]
        for existing in self._async_current_entries():
            if existing.data.get("entry_type", "plants") == entry_type:
                return self.async_abort(reason=f"{entry_type}_instance_allowed")
        titles = {
            "plants": "Plants",
            "meter_locations": "Meter Locations",
            "grow_lights": "Grow Lights",
            "humidifiers": "Humidifiers",
            "thermostats": "Thermostats",
            "auto_waterers": "Auto Waterers",
            "agent_log": "Agent Log",
        }
        title = titles.get(entry_type, entry_type.replace("_", " ").title())
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


class GrowLightsOptionsFlow(config_entries.OptionsFlow):
    """Handle Grow Lights options."""

    async def async_step_init(self, user_input=None):
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_grow_light",
                "remove_grow_light",
            ],
        )

    async def async_step_add_grow_light(self, user_input=None):
        """Add a grow light device."""
        if user_input is not None:
            data: GrowLightsData = self.hass.data[DOMAIN][self.config_entry.entry_id][
                "data"
            ]
            data.add_grow_light(
                name=user_input["name"],
                light_entity_id=user_input.get("light_entity_id"),
            )
            await data.async_save()
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("light_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch"])
                ),
            }
        )
        return self.async_show_form(step_id="add_grow_light", data_schema=schema)

    async def async_step_remove_grow_light(self, user_input=None):
        """Remove a grow light device."""
        data: GrowLightsData = self.hass.data[DOMAIN][self.config_entry.entry_id][
            "data"
        ]
        labels, label_to_id = self._label_maps(data)

        if user_input is not None:
            label = user_input["grow_light_label"]
            grow_light_id = label_to_id.get(label)
            if grow_light_id:
                data.remove_grow_light(grow_light_id)
                await data.async_save()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("grow_light_label"): vol.In(labels),
            }
        )
        return self.async_show_form(step_id="remove_grow_light", data_schema=schema)

    @staticmethod
    def _label_maps(data: GrowLightsData) -> tuple[list[str], dict[str, str]]:
        labels: list[str] = []
        label_to_id: dict[str, str] = {}
        for grow_light_id, gl in data.grow_lights.items():
            labels.append(gl.name)
            label_to_id[gl.name] = grow_light_id
        labels.sort()
        return labels, label_to_id


class HumidifiersOptionsFlow(config_entries.OptionsFlow):
    """Handle Humidifiers options."""

    async def async_step_init(self, user_input=None):
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_humidifier",
                "remove_humidifier",
            ],
        )

    async def async_step_add_humidifier(self, user_input=None):
        """Add a humidifier device."""
        if user_input is not None:
            data: HumidifiersData = self.hass.data[DOMAIN][self.config_entry.entry_id][
                "data"
            ]
            data.add_humidifier(
                name=user_input["name"],
                humidifier_entity_id=user_input.get("humidifier_entity_id"),
            )
            await data.async_save()
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("humidifier_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch"])
                ),
            }
        )
        return self.async_show_form(step_id="add_humidifier", data_schema=schema)

    async def async_step_remove_humidifier(self, user_input=None):
        """Remove a humidifier device."""
        data: HumidifiersData = self.hass.data[DOMAIN][self.config_entry.entry_id][
            "data"
        ]
        labels, label_to_id = self._label_maps(data)

        if user_input is not None:
            label = user_input["humidifier_label"]
            humidifier_id = label_to_id.get(label)
            if humidifier_id:
                data.remove_humidifier(humidifier_id)
                await data.async_save()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("humidifier_label"): vol.In(labels),
            }
        )
        return self.async_show_form(step_id="remove_humidifier", data_schema=schema)

    @staticmethod
    def _label_maps(data: HumidifiersData) -> tuple[list[str], dict[str, str]]:
        labels: list[str] = []
        label_to_id: dict[str, str] = {}
        for humidifier_id, hd in data.humidifiers.items():
            labels.append(hd.name)
            label_to_id[hd.name] = humidifier_id
        labels.sort()
        return labels, label_to_id


class ThermostatsOptionsFlow(config_entries.OptionsFlow):
    """Handle Thermostats options."""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_thermostat", "remove_thermostat"],
        )

    async def async_step_add_thermostat(self, user_input=None):
        if user_input is not None:
            data: ThermostatsData = self.hass.data[DOMAIN][self.config_entry.entry_id]["data"]
            data.add_thermostat(
                name=user_input["name"],
                climate_entity_id=user_input.get("climate_entity_id"),
            )
            await data.async_save()
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("climate_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["climate"])
                ),
            }
        )
        return self.async_show_form(step_id="add_thermostat", data_schema=schema)

    async def async_step_remove_thermostat(self, user_input=None):
        data: ThermostatsData = self.hass.data[DOMAIN][self.config_entry.entry_id]["data"]
        labels, label_to_id = self._label_maps(data)

        if user_input is not None:
            label = user_input["thermostat_label"]
            thermostat_id = label_to_id.get(label)
            if thermostat_id:
                data.remove_thermostat(thermostat_id)
                await data.async_save()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema({vol.Required("thermostat_label"): vol.In(labels)})
        return self.async_show_form(step_id="remove_thermostat", data_schema=schema)

    @staticmethod
    def _label_maps(data: ThermostatsData) -> tuple[list[str], dict[str, str]]:
        labels: list[str] = []
        label_to_id: dict[str, str] = {}
        for thermostat_id, td in data.thermostats.items():
            labels.append(td.name)
            label_to_id[td.name] = thermostat_id
        labels.sort()
        return labels, label_to_id


class AutoWaterersOptionsFlow(config_entries.OptionsFlow):
    """Handle Auto Waterers options."""

    async def async_step_init(self, user_input=None):
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_auto_waterer",
                "remove_auto_waterer",
            ],
        )

    async def async_step_add_auto_waterer(self, user_input=None):
        """Add an auto waterer device."""
        if user_input is not None:
            data: AutoWaterersData = self.hass.data[DOMAIN][
                self.config_entry.entry_id
            ]["data"]
            data.add_auto_waterer(
                name=user_input["name"],
                water_entity_id=user_input.get("water_entity_id"),
            )
            await data.async_save()
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("water_entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["switch", "valve"])
                ),
            }
        )
        return self.async_show_form(step_id="add_auto_waterer", data_schema=schema)

    async def async_step_remove_auto_waterer(self, user_input=None):
        """Remove an auto waterer device."""
        data: AutoWaterersData = self.hass.data[DOMAIN][self.config_entry.entry_id][
            "data"
        ]
        labels, label_to_id = self._label_maps(data)

        if user_input is not None:
            label = user_input["auto_waterer_label"]
            waterer_id = label_to_id.get(label)
            if waterer_id:
                data.remove_auto_waterer(waterer_id)
                await data.async_save()
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required("auto_waterer_label"): vol.In(labels),
            }
        )
        return self.async_show_form(step_id="remove_auto_waterer", data_schema=schema)

    @staticmethod
    def _label_maps(data: AutoWaterersData) -> tuple[list[str], dict[str, str]]:
        labels: list[str] = []
        label_to_id: dict[str, str] = {}
        for waterer_id, aw in data.auto_waterers.items():
            labels.append(aw.name)
            label_to_id[aw.name] = waterer_id
        labels.sort()
        return labels, label_to_id


class AgentLogOptionsFlow(config_entries.OptionsFlow):
    """No configurable options for Agent Log."""

    async def async_step_init(self, user_input=None):
        return self.async_create_entry(title="", data={})
