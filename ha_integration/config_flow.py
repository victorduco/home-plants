"""Config flow for Plants."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN


class PlantsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Plants."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            name = user_input["name"].strip()
            if not name:
                errors["name"] = "required"
            else:
                return self.async_create_entry(title=name, data={"name": name})

        schema = vol.Schema({vol.Required("name"): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


@callback
def async_get_options_flow(config_entry):
    """No options flow for now."""
    return None
