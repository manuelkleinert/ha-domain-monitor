from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, OVERALL_SENSOR_KEY
from .coordinator import DomainDataCoordinator

PLATFORMS = ["sensor", "number", "button", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    coordinator = DomainDataCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        stored = hass.data[DOMAIN].get(OVERALL_SENSOR_KEY)
        if stored and stored[0] == entry.entry_id:
            hass.data[DOMAIN].pop(OVERALL_SENSOR_KEY, None)

            remaining = [
                item_id
                for item_id, item in hass.data[DOMAIN].items()
                if isinstance(item, DataUpdateCoordinator)
            ]
            if remaining:
                # Der globale Sensor hing am entfernten Entry und wurde mit
                # diesem entladen – auf einem verbleibenden Entry neu anlegen.
                hass.async_create_task(
                    hass.config_entries.async_reload(remaining[0])
                )

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)
