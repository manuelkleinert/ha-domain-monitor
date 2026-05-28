import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, TIMEOUT, DEFAULT_RETRIES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        DomainMonitorIntervalNumber(coordinator, entry),
        DomainMonitorTimeoutNumber(coordinator, entry),
        DomainMonitorRetriesNumber(coordinator, entry),
    ]

    async_add_entities(entities)


class DomainMonitorBaseNumber(NumberEntity):
    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry):
        self.coordinator = coordinator
        self.entry = entry

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_options = dict(self.entry.options)
        new_options[self.option_key] = int(value)
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)


class DomainMonitorIntervalNumber(DomainMonitorBaseNumber):
    _attr_icon = "mdi:timer-sand"
    _attr_native_min_value = 10
    _attr_native_max_value = 3600
    _attr_native_step = 10
    _attr_mode = NumberMode.BOX
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_name = f"{entry.title} Interval" if entry.title else "Domain Monitor Interval"
        self._attr_unique_id = f"domain_monitor_{entry.entry_id}_interval"
        self.option_key = "interval"

    @property
    def native_value(self) -> float:
        return float(self.coordinator.interval)


class DomainMonitorTimeoutNumber(DomainMonitorBaseNumber):
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 1
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_name = f"{entry.title} Timeout" if entry.title else "Domain Monitor Timeout"
        self._attr_unique_id = f"domain_monitor_{entry.entry_id}_timeout"
        self.option_key = "timeout"

    @property
    def native_value(self) -> float:
        return float(self.coordinator.timeout)


class DomainMonitorRetriesNumber(DomainMonitorBaseNumber):
    _attr_icon = "mdi:refresh"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_name = f"{entry.title} Retries" if entry.title else "Domain Monitor Retries"
        self._attr_unique_id = f"domain_monitor_{entry.entry_id}_retries"
        self.option_key = "retries"

    @property
    def native_value(self) -> float:
        return float(self.coordinator.retries)
