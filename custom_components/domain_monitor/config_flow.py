import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN


class DomainMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DomainMonitorOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        schema = vol.Schema({
            vol.Required("host"): str,
            vol.Required("type", default="https"): vol.In(["https", "http", "tcp"]),
            vol.Optional("port", default=443): int,
            vol.Optional("keyword"): str,
        })

        if user_input is not None:
            host = user_input["host"].strip()
            check_type = user_input["type"]
            port = user_input.get("port", 443)
            keyword = user_input.get("keyword", "").strip()

            if check_type in ["http", "https"]:
                if keyword:
                    service = f"{host}:{check_type}:{keyword}"
                    display_title = f"{host} ({check_type} + Regex)"
                else:
                    service = f"{host}:{check_type}"
                    display_title = f"{host} ({check_type})"
            else:
                service = f"{host}:tcp:{port}"
                display_title = f"{host} (Port {port})"

            return self.async_create_entry(
                title=display_title,
                data={"services": service}
            )

        return self.async_show_form(step_id="user", data_schema=schema)


class DomainMonitorOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            services_str = user_input.get("services", "")
            services_list = [s.strip() for s in services_str.split(",") if s.strip()]
            
            if not services_list:
                title = "Domain Monitor"
            elif len(services_list) == 1:
                # Schönere Titel-Logik auch hier anwenden
                parts = services_list[0].split(":")
                host = parts[0]
                if len(parts) >= 2:
                    proto = parts[1]
                    if proto in ["http", "https"]:
                        title = f"{host} ({proto}{' + Regex' if len(parts) > 2 else ''})"
                    else:
                        title = f"{host} (Port {parts[2]})"
                else:
                    title = host
            else:
                title = f"{services_list[0].split(':')[0]} (+{len(services_list)-1} weitere)"

            self.hass.config_entries.async_update_entry(
                self._entry, title=title
            )
            
            return self.async_create_entry(title="", data=user_input)

        current_services = self._entry.options.get(
            "services", self._entry.data.get("services", "")
        )

        schema = vol.Schema({
            vol.Required("services", default=current_services): str
        })

        return self.async_show_form(step_id="init", data_schema=schema)