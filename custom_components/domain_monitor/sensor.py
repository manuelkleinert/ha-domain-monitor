from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [DomainSensor(coordinator, d) for d in coordinator.domains]
    async_add_entities(entities)

class DomainSensor(SensorEntity):

    def __init__(self, coordinator, domain):
        self.coordinator = coordinator
        self.domain = domain
        self._attr_name = f"Domain {domain}"
        self._attr_unique_id = f"domain_monitor_{domain}"

    @property
    def state(self):
        data = self.coordinator.data.get(self.domain, {})
        return data.get("status", "unknown")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.domain, {})
        history = self.coordinator.history.get(self.domain, [])

        up = len([h for h in history if h.get("status") == "up"])
        uptime = round((up / len(history)) * 100, 2) if history else 0

        return {
            "response_ms": data.get("response_ms"),
            "status_code": data.get("code"),
            "last_check": str(data.get("time")),
            "uptime_percent": uptime,
            "checks": len(history)
        }

    @property
    def available(self):
        return self.coordinator.last_update_success
