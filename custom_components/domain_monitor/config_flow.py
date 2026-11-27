import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .coordinator import normalize_services, service_id
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    TIMEOUT,
    DEFAULT_RETRIES,
    DEFAULT_SLOW_THRESHOLD,
    MIN_INTERVAL,
    MAX_INTERVAL,
    MIN_TIMEOUT,
    MAX_TIMEOUT,
    MIN_RETRIES,
    MAX_RETRIES,
    MIN_SLOW_THRESHOLD,
    MAX_SLOW_THRESHOLD,
)

# Hostname, IP literal or bracketed IPv6 literal: no scheme, no path, no
# credentials, no spaces. Bare (non-bracketed) IPv6 is not possible because
# it collides with the colon-based legacy string format.
HOST_PATTERN = r"^([A-Za-z0-9._-]+|\[[0-9a-fA-F:]+\])$"


def _tuning_schema(tuning: dict) -> dict:
    return {
        vol.Optional("interval", default=tuning.get("interval", DEFAULT_SCAN_INTERVAL)): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_INTERVAL, max=MAX_INTERVAL)
        ),
        vol.Optional("timeout", default=tuning.get("timeout", TIMEOUT)): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_TIMEOUT, max=MAX_TIMEOUT)
        ),
        vol.Optional("retries", default=tuning.get("retries", DEFAULT_RETRIES)): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_RETRIES, max=MAX_RETRIES)
        ),
        vol.Optional("slow_threshold_ms", default=tuning.get("slow_threshold_ms", DEFAULT_SLOW_THRESHOLD)): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SLOW_THRESHOLD, max=MAX_SLOW_THRESHOLD)
        ),
    }


def _service_fields_schema(host: str = "", check_type: str = "https", port: int = 443, keyword: str = "") -> dict:
    return {
        vol.Required("host", default=host): vol.Match(HOST_PATTERN),
        vol.Required("type", default=check_type): vol.In(["https", "http", "tcp"]),
        vol.Optional("port", default=port): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional("keyword", default=keyword): str,
    }


def _service_label(service: dict) -> str:
    if service["type"] == "tcp":
        return f"{service['host']} (tcp:{service['port']})"
    return f"{service['host']} ({service['type']}:{service['port']})"


def _resolve_port(check_type: str, port) -> int:
    if not port or port <= 0:
        return 443 if check_type == "https" else 80
    return port


class DomainMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DomainMonitorOptionsFlowHandler()

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            host = user_input["host"].strip()
            check_type = user_input["type"]
            port = _resolve_port(check_type, user_input.get("port"))
            keyword = (user_input.get("keyword") or "").strip()

            service = {"host": host, "type": check_type, "port": port, "keyword": keyword or None}

            return self.async_create_entry(
                title=f"{host} ({check_type})",
                data={
                    "services": [service],
                    "interval": user_input["interval"],
                    "timeout": user_input["timeout"],
                    "retries": user_input["retries"],
                    "slow_threshold_ms": user_input["slow_threshold_ms"],
                },
            )

        schema = _service_fields_schema()
        schema.update(_tuning_schema({}))

        return self.async_show_form(step_id="user", data_schema=vol.Schema(schema))


class DomainMonitorOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow: a menu with two paths – tuning and the service editor.

    HA flow forms cannot mix form fields and action buttons, so instead of a
    checkbox the flow opens with a menu: "Settings" shows the tuning form,
    "Services" opens the menu-driven editor (add/edit/delete/done) with the
    current services listed in its description.
    """

    def __init__(self):
        self._tuning: dict = {}
        self._services: list[dict] | None = None
        self._editing_sid: str | None = None

    def _entry_services(self) -> list[dict]:
        raw = self.config_entry.options.get("services", self.config_entry.data.get("services", []))
        services, _ = normalize_services(raw)
        return services

    def _current_tuning(self) -> dict:
        entry = self.config_entry
        return {
            key: entry.options.get(key, entry.data.get(key, default))
            for key, default in (
                ("interval", DEFAULT_SCAN_INTERVAL),
                ("timeout", TIMEOUT),
                ("retries", DEFAULT_RETRIES),
                ("slow_threshold_ms", DEFAULT_SLOW_THRESHOLD),
            )
        }

    def _services_list_markdown(self) -> str:
        if not self._services:
            return "-"
        return "\n".join(f"- {_service_label(s)}" for s in self._services)

    def _service_options(self) -> dict:
        return {service_id(s): _service_label(s) for s in self._services or []}

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "manage"],
        )

    async def async_step_settings(self, user_input=None):
        if user_input is not None:
            self._tuning = {
                "interval": user_input["interval"],
                "timeout": user_input["timeout"],
                "retries": user_input["retries"],
                "slow_threshold_ms": user_input["slow_threshold_ms"],
            }
            return await self._async_save(self._entry_services())

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(_tuning_schema(self._tuning or self._current_tuning())),
        )

    async def async_step_manage(self, user_input=None):
        """Overview: current services in the description, actions as buttons."""
        if self._services is None:
            self._services = self._entry_services()

        return self.async_show_menu(
            step_id="manage",
            menu_options=[
                "add_service",
                "edit_service",
                "delete_service",
                "settings",
                "done",
            ],
            description_placeholders={"services_list": self._services_list_markdown()},
        )

    async def async_step_add_service(self, user_input=None):
        self._editing_sid = None
        return await self.async_step_service()

    async def async_step_edit_service(self, user_input=None):
        if user_input is not None:
            self._editing_sid = user_input["service"]
            return await self.async_step_service()

        if not self._services:
            return await self.async_step_manage()

        return self.async_show_form(
            step_id="edit_service",
            data_schema=vol.Schema({vol.Required("service"): vol.In(self._service_options())}),
        )

    async def async_step_delete_service(self, user_input=None):
        if user_input is not None:
            if len(self._services) <= 1:
                return self.async_show_form(
                    step_id="delete_service",
                    data_schema=vol.Schema(
                        {vol.Required("service"): vol.In(self._service_options())}
                    ),
                    errors={"base": "at_least_one"},
                )
            self._services = [
                s for s in self._services if service_id(s) != user_input["service"]
            ]
            return await self.async_step_manage()

        if not self._services:
            return await self.async_step_manage()

        return self.async_show_form(
            step_id="delete_service",
            data_schema=vol.Schema(
                {vol.Required("service"): vol.In(self._service_options())}
            ),
        )

    async def async_step_done(self, user_input=None):
        """Leave the editor and save all changes at once."""
        return await self._async_save(self._services or [])

    async def async_step_service(self, user_input=None):
        current = next(
            (s for s in self._services or [] if service_id(s) == self._editing_sid), None
        )

        if user_input is None:
            schema = (
                _service_fields_schema(
                    host=current["host"],
                    check_type=current["type"],
                    port=current["port"],
                    keyword=current["keyword"] or "",
                )
                if current
                else _service_fields_schema()
            )
            return self.async_show_form(step_id="service", data_schema=vol.Schema(schema))

        service = {
            "host": user_input["host"].strip(),
            "type": user_input["type"],
            "port": _resolve_port(user_input["type"], user_input.get("port")),
            "keyword": (user_input.get("keyword") or "").strip() or None,
        }
        sid = service_id(service)

        if any(service_id(s) == sid for s in self._services or []) and sid != self._editing_sid:
            return self.async_show_form(
                step_id="service",
                data_schema=vol.Schema(
                    _service_fields_schema(
                        host=current["host"],
                        check_type=current["type"],
                        port=current["port"],
                        keyword=current["keyword"] or "",
                    )
                    if current
                    else _service_fields_schema()
                ),
                errors={"base": "duplicate_service"},
            )

        if self._editing_sid:
            self._services = [
                service if service_id(s) == self._editing_sid else s for s in self._services
            ]
        else:
            self._services.append(service)

        return await self.async_step_manage()

    async def _async_save(self, services: list[dict]):
        entry = self.config_entry
        title = _service_label(services[0]) if services else entry.title
        self.hass.config_entries.async_update_entry(entry, title=title)

        return self.async_create_entry(
            title="",
            data={
                "services": services,
                **(self._tuning or self._current_tuning()),
            },
        )
