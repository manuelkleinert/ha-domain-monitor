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

_ADD_SERVICE = "__add__"
_DONE = "__done__"


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
        return DomainMonitorOptionsFlowHandler(config_entry)

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
    """Options flow: tuning plus a multi-step editor for the service list."""

    def __init__(self, config_entry):
        self._entry = config_entry
        self._tuning: dict = {}

    def _current_services(self) -> list[dict]:
        raw = self._entry.options.get("services", self._entry.data.get("services", []))
        services, _ = normalize_services(raw)
        return services

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self._tuning = {
                "interval": user_input["interval"],
                "timeout": user_input["timeout"],
                "retries": user_input["retries"],
                "slow_threshold_ms": user_input["slow_threshold_ms"],
            }

            if user_input["edit_services"]:
                return await self.async_step_manage()

            return await self._async_save(self._current_services())

        current = self._entry.options
        fallback = self._entry.data
        defaults = self._tuning or {
            key: current.get(key, fallback.get(key, default))
            for key, default in (
                ("interval", DEFAULT_SCAN_INTERVAL),
                ("timeout", TIMEOUT),
                ("retries", DEFAULT_RETRIES),
                ("slow_threshold_ms", DEFAULT_SLOW_THRESHOLD),
            )
        }

        schema = vol.Schema(
            {
                vol.Required("edit_services", default=False): bool,
                **_tuning_schema(defaults),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_manage(self, user_input=None):
        services = self._current_services()

        if user_input is not None:
            selected = user_input["service"]
            if selected == _DONE:
                return await self.async_step_init()
            if selected == _ADD_SERVICE:
                return await self.async_step_service()
            service = next(s for s in services if service_id(s) == selected)
            return await self.async_step_service(service)

        mapping = {service_id(s): _service_label(s) for s in services}
        mapping[_ADD_SERVICE] = "+ Add new service"
        mapping[_DONE] = "- Done -"

        schema = vol.Schema({vol.Required("service"): vol.In(mapping)})
        return self.async_show_form(step_id="manage", data_schema=schema)

    async def async_step_service(self, user_input=None):
        services = self._current_services()
        editing = getattr(self, "_editing_sid", None)

        if user_input is None:
            service = next((s for s in services if service_id(s) == editing), None)
            self._editing_sid = service_id(service) if service else None
            return self.async_show_form(
                step_id="service", data_schema=self._service_form_schema(service)
            )

        current = next((s for s in services if service_id(s) == self._editing_sid), None)

        if user_input["delete"]:
            if len(services) <= 1:
                return self.async_show_form(
                    step_id="service",
                    data_schema=self._service_form_schema(current),
                    errors={"base": "at_least_one"},
                )
            services = [s for s in services if service_id(s) != self._editing_sid]
            return await self._async_save(services)

        service = {
            "host": user_input["host"].strip(),
            "type": user_input["type"],
            "port": _resolve_port(user_input["type"], user_input.get("port")),
            "keyword": (user_input.get("keyword") or "").strip() or None,
        }
        sid = service_id(service)

        if any(service_id(s) == sid for s in services) and sid != self._editing_sid:
            return self.async_show_form(
                step_id="service",
                data_schema=self._service_form_schema(current),
                errors={"base": "duplicate_service"},
            )

        if self._editing_sid:
            services = [
                service if service_id(s) == self._editing_sid else s for s in services
            ]
        else:
            services.append(service)

        return await self._async_save(services)

    @staticmethod
    def _service_form_schema(service: dict | None):
        schema = (
            _service_fields_schema(
                host=service["host"],
                check_type=service["type"],
                port=service["port"],
                keyword=service["keyword"] or "",
            )
            if service
            else _service_fields_schema()
        )
        return vol.Schema({**schema, vol.Required("delete", default=False): bool})

    async def _async_save(self, services: list[dict]):
        title = _service_label(services[0]) if services else self._entry.title
        self.hass.config_entries.async_update_entry(self._entry, title=title)

        return self.async_create_entry(
            title="",
            data={
                "services": services,
                **self._tuning,
            },
        )
