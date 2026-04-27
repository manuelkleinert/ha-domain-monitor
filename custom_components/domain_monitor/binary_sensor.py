from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DomainMonitorGlobalStatus(coordinator)])

class DomainMonitorGlobalStatus(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is ON if all monitored services are up."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Global Status"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def unique_id(self):
        return f"{self.coordinator.entry.entry_id}_global_status"

    @property
    def is_on(self):
        """Return true if all services are up."""
        if not self.coordinator.data:
            return False
            
        return all(
            result.get("status") == "up" 
            for result in self.coordinator.data.values()
        )

    @property
    def extra_state_attributes(self):
        """Return which hosts are down."""
        down_hosts = [
            host for host, result in self.coordinator.data.items() 
            if result.get("status") == "down"
        ]
        return {
            "down_hosts": down_hosts,
            "total_monitored": len(self.coordinator.data)
        }
