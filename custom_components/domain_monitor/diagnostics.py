from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN

TO_REDACT = {"keyword"}


async def async_get_config_entry_diagnostics(hass, entry):
    """Return diagnostics for a config entry, keyword regexes redacted."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "internet_ok": coordinator.internet_ok,
        "disabled_services": sorted(coordinator.disabled),
        "invalid_services": coordinator.invalid_services,
        "services": [service for service in coordinator.services],
        "last_results": coordinator.data,
        "certificates": coordinator.cert_data,
    }
