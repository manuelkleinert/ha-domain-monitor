from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN, OVERALL_SENSOR_KEY


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Der globale Sensor wird nur ein einziges Mal erzeugt; die Zuordnung zum
    # besitzenden Entry wird gemerkt, damit er nach dem Entfernen des Entries
    # von einem verbleibenden Entry neu angelegt werden kann.
    if not hass.data[DOMAIN].get(OVERALL_SENSOR_KEY):
        entity = DomainMonitorTotalStatus(coordinator)
        hass.data[DOMAIN][OVERALL_SENSOR_KEY] = (entry.entry_id, entity)
        async_add_entities([entity])


class DomainMonitorTotalStatus(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is ON unless one of the monitored services is down."""

    _attr_name = "Overall Domain Status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_unique_id = "domain_monitor_overall_status"

    def _coordinators(self):
        domain_data = self.hass.data.get(DOMAIN, {})
        return [
            item
            for item in domain_data.values()
            if isinstance(item, DataUpdateCoordinator)
        ]

    def _statuses(self):
        statuses = []
        for coordinator in self._coordinators():
            if coordinator.data:
                statuses.extend(r.get("status") for r in coordinator.data.values())
        return statuses

    @property
    def is_on(self):
        """Return true unless at least one monitored service is down.

        "unknown" states (e.g. while Home Assistant has no internet) do not
        count as down, so no false alarms are raised during an outage.
        """
        statuses = self._statuses()
        if not statuses:
            return True
        return all(status in ("up", "unknown") for status in statuses)

    @property
    def extra_state_attributes(self):
        """Return lists of all down/unknown hosts across all entries."""
        down_hosts = []
        unknown_hosts = []
        total_count = 0

        for coordinator in self._coordinators():
            if not coordinator.data:
                continue
            total_count += len(coordinator.data)
            for host, result in coordinator.data.items():
                status = result.get("status")
                if status == "down":
                    down_hosts.append(host)
                elif status == "unknown":
                    unknown_hosts.append(host)

        flags = [
            coordinator.internet_ok
            for coordinator in self._coordinators()
            if coordinator.internet_ok is not None
        ]

        attributes = {
            "down_hosts": down_hosts,
            "unknown_hosts": unknown_hosts,
            "total_monitored": total_count,
            "problem_count": len(down_hosts),
        }

        if flags:
            attributes["internet_connected"] = all(flags)

        return attributes

    async def async_added_to_hass(self):
        """Also listen to updates from the coordinators of other entries."""
        await super().async_added_to_hass()
        for coordinator in self._coordinators():
            if coordinator is self.coordinator:
                continue
            self.async_on_remove(
                coordinator.async_add_listener(self.async_write_ha_state)
            )
