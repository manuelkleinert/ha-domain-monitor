from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def build_device_info(entry) -> DeviceInfo:
    """One device per config entry: all entities group under it."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or "Domain Monitor",
        manufacturer="manuelkleinert",
        model="Domain Monitor",
    )
