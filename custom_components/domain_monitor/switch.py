from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device import build_device_info
from .sensor import _service_label, _unique_id_base


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        DomainMonitorSwitch(coordinator, service)
        for service in coordinator.services
    ]

    async_add_entities(entities)


class DomainMonitorSwitch(CoordinatorEntity, SwitchEntity):
    """Pause or resume monitoring of a single service (runtime only)."""

    def __init__(self, coordinator, service: dict):
        super().__init__(coordinator)
        self.service = service
        self._attr_name = f"Monitor {_service_label(service)}"
        self._attr_unique_id = f"{_unique_id_base(coordinator, service)}_monitor"
        self._attr_device_info = build_device_info(coordinator.entry)
        self._attr_icon = "mdi:eye"

    @property
    def is_on(self):
        return self.service["id"] not in self.coordinator.disabled

    async def async_turn_on(self) -> None:
        """Resume monitoring."""
        self.coordinator.set_enabled(self.service["id"], True)

    async def async_turn_off(self) -> None:
        """Pause monitoring."""
        self.coordinator.set_enabled(self.service["id"], False)
