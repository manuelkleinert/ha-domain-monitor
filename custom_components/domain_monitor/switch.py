from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.helpers.restore_state import RestoreEntity
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


class DomainMonitorSwitch(CoordinatorEntity, RestoreEntity, SwitchEntity):
    """Pause or resume monitoring of a single service (survives restarts)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, service: dict):
        super().__init__(coordinator)
        self.service = service
        self._attr_translation_key = "monitor"
        self._attr_translation_placeholders = {"host": _service_label(service)}
        self._attr_unique_id = f"{_unique_id_base(coordinator, service)}_monitor"
        self._attr_device_info = build_device_info(coordinator.entry)
        self._attr_icon = "mdi:eye"

    @property
    def is_on(self):
        return self.service["id"] not in self.coordinator.disabled

    async def async_added_to_hass(self) -> None:
        """Restore the paused state after a Home Assistant restart."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state == STATE_OFF:
            self.coordinator.set_enabled(self.service["id"], False)

    async def async_turn_on(self) -> None:
        """Resume monitoring."""
        self.coordinator.set_enabled(self.service["id"], True)

    async def async_turn_off(self) -> None:
        """Pause monitoring."""
        self.coordinator.set_enabled(self.service["id"], False)
