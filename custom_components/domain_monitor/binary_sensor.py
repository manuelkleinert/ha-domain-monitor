from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Wir fügen den globalen Sensor nur ein einziges Mal hinzu.
    # Wir prüfen, ob bereits ein globaler Sensor für diese Domäne existiert.
    if not hass.data[DOMAIN].get("global_sensor_added"):
        async_add_entities([DomainMonitorTotalStatus(hass)])
        hass.data[DOMAIN]["global_sensor_added"] = True

class DomainMonitorTotalStatus(BinarySensorEntity):
    """Binary sensor that is ON only if ALL services across ALL entries are up."""

    def __init__(self, hass):
        self.hass = hass
        self._attr_name = "Overall Domain Status"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_unique_id = "domain_monitor_overall_status"

    @property
    def is_on(self):
        """Return true if ALL services in ALL entries are up."""
        domain_data = self.hass.data.get(DOMAIN, {})
        
        all_results = []
        for entry_id, coordinator in domain_data.items():
            # Überspringe den Hilfseintrag für die Registrierung
            if entry_id == "global_sensor_added":
                continue
            
            # Sammle alle Status-Werte aus allen Coordinatoren
            if hasattr(coordinator, "data") and coordinator.data:
                all_results.extend([r.get("status") for r in coordinator.data.values()])
        
        if not all_results:
            return False
            
        return all(status == "up" for status in all_results)

    @property
    def extra_state_attributes(self):
        """Return list of all down hosts across all entries."""
        domain_data = self.hass.data.get(DOMAIN, {})
        down_hosts = []
        total_count = 0
        
        for entry_id, coordinator in domain_data.items():
            if entry_id == "global_sensor_added":
                continue
            if hasattr(coordinator, "data") and coordinator.data:
                total_count += len(coordinator.data)
                down_hosts.extend([
                    host for host, result in coordinator.data.items() 
                    if result.get("status") == "down"
                ])
                
        return {
            "down_hosts": down_hosts,
            "total_monitored": total_count,
            "problem_count": len(down_hosts)
        }

    async def async_added_to_hass(self):
        """Register for updates from all coordinators."""
        # Da dieser Sensor nicht an einen spezifischen Coordinator gebunden ist,
        # verlassen wir uns darauf, dass HA ihn regelmäßig aktualisiert oder 
        # wir lauschen auf Events. Am einfachsten ist es, ihn bei jeder Änderung
        # irgendeiner Entität zu triggern oder einfach die state-property dynamisch zu lassen.
        pass
