from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import DOMAIN
from .protocol import PORT, PocketHomeClient


class PocketHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                name = await PocketHomeClient(user_input[CONF_HOST], user_input[CONF_PORT]).info()
            except (ConnectionError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(name)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=name, data=user_input)
        schema = vol.Schema({vol.Required(CONF_HOST): str, vol.Required(CONF_PORT, default=PORT): int})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
