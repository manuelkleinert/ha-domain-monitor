from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device import build_device_info
from .sensor import _service_label, _unique_id_base


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        DomainMonitorButton(coordinator, service)
        for service in coordinator.services
    ]

    async_add_entities(entities)


class DomainMonitorButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, service: dict):
        super().__init__(coordinator)
        self.service = service
        self._attr_translation_key = "check_button"
        self._attr_translation_placeholders = {"host": _service_label(service)}
        self._attr_unique_id = f"{_unique_id_base(coordinator, service)}_check_button"
        self._attr_device_info = build_device_info(coordinator.entry)
        self._attr_icon = "mdi:refresh"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_request_refresh()
