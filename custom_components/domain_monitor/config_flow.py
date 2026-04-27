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
            vol.Optional("port"): int,
            vol.Optional("keyword"): str,
        })

        if user_input is not None:
            host = user_input["host"].strip()
            check_type = user_input["type"]
            keyword = user_input.get("keyword", "").strip()
            
            # Default ports if not specified
            port = user_input.get("port")
            if not port:
                if check_type == "https":
                    port = 443
                elif check_type == "http":
                    port = 80
                else:
                    port = 0

            if check_type in ["http", "https"]:
                # Save as host:type:port:keyword
                service = f"{host}:{check_type}:{port}:{keyword}"
                if keyword:
                    display_title = f"{host} ({check_type} + Regex)"
                else:
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
            host = user_input["host"].strip()
            check_type = user_input["type"]
            keyword = user_input.get("keyword", "").strip()
            
            port = user_input.get("port")
            if not port:
                if check_type == "https":
                    port = 443
                elif check_type == "http":
                    port = 80

            if check_type in ["http", "https"]:
                service = f"{host}:{check_type}:{port}:{keyword}"
                title = f"{host} ({check_type}{' + Regex' if keyword else ''})"
            else:
                service = f"{host}:tcp:{port}"
                title = f"{host} (Port {port})"

            self.hass.config_entries.async_update_entry(
                self._entry, title=title
            )

            return self.async_create_entry(title="", data={"services": service})

        current_services = self._entry.options.get(
            "services", self._entry.data.get("services", "")
        )

        # Parse existing service
        first_service = current_services.split(",")[0].strip()
        parts = first_service.split(":", 3)

        host = parts[0]
        check_type = "https"
        port = 443
        keyword = ""

        if len(parts) >= 2:
            check_type = parts[1]
            if check_type in ["http", "https"]:
                if len(parts) == 3:
                    # Legacy format: host:type:keyword
                    keyword = parts[2]
                    port = 443 if check_type == "https" else 80
                elif len(parts) == 4:
                    # New format: host:type:port:keyword
                    try:
                        port = int(parts[2])
                    except ValueError:
                        port = 443 if check_type == "https" else 80
                    keyword = parts[3]
            elif check_type == "tcp" and len(parts) >= 3:
                try:
                    port = int(parts[2])
                except ValueError:
                    port = 0

        schema = vol.Schema({
            vol.Required("host", default=host): str,
            vol.Required("type", default=check_type): vol.In(["https", "http", "tcp"]),
            vol.Optional("port", default=port): int,
            vol.Optional("keyword", default=keyword): str,
        })

        return self.async_show_form(step_id="init", data_schema=schema)