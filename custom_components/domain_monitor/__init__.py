import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, OVERALL_SENSOR_KEY
from .coordinator import DomainDataCoordinator, normalize_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "number", "button", "switch", "binary_sensor"]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Migrate old entries to the current version (v1 string -> v2 JSON list)."""
    _LOGGER.debug("Migrating %s from version %s", entry.entry_id, entry.version)

    if entry.version > 2:
        return False

    if entry.version == 1:
        data = {**entry.data}
        services, invalid = normalize_services(data.get("services", ""))
        data["services"] = services

        if invalid:
            _LOGGER.warning(
                "Dropping unparseable services while migrating entry %s: %s",
                entry.entry_id,
                ", ".join(invalid),
            )

        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.info("Migrated %s to version 2", entry.entry_id)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    coordinator = DomainDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    _manage_invalid_service_issues(hass, entry, coordinator)

    return True


def _manage_invalid_service_issues(hass, entry, coordinator):
    """Surface unparseable service entries as repair issues in the UI."""
    issue_id = f"invalid_services_{entry.entry_id}"

    if coordinator.invalid_services:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="invalid_service",
            translation_placeholders={
                "services": "\n".join(coordinator.invalid_services),
                "entry": entry.title or entry.entry_id,
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        ir.async_delete_issue(hass, DOMAIN, f"invalid_services_{entry.entry_id}")

        stored = hass.data[DOMAIN].get(OVERALL_SENSOR_KEY)
        if stored and stored[0] == entry.entry_id:
            hass.data[DOMAIN].pop(OVERALL_SENSOR_KEY, None)

            remaining = [
                item_id
                for item_id, item in hass.data[DOMAIN].items()
                if isinstance(item, DataUpdateCoordinator)
            ]
            if remaining:
                # The global sensor lived on this entry and was unloaded with
                # it – re-create it on a remaining entry's coordinator.
                hass.async_create_task(
                    hass.config_entries.async_reload(remaining[0])
                )

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)
