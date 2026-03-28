import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN

class DomainMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="Domain Monitor",
                data=user_input
            )

        schema = vol.Schema({
            vol.Required("domains"): str
        })

        return self.async_show_form(step_id="user", data_schema=schema)
