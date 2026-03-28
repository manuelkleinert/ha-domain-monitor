from homeassistant.helpers.entity import Entity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["domain_monitor"][entry.entry_id]

    entities = []

    for service in coordinator.services:
        entities.append(DomainSensor(coordinator, service))

    async_add_entities(entities)


class DomainSensor(Entity):

    def __init__(self, coordinator, service):
        self.coordinator = coordinator
        self.service = service
        
        host = service["host"]
        if service["type"] == "http":
            name = f"{host} (http)"
            uid = f"domain_monitor_{host}_http"
        else:
            port = service["port"]
            name = f"{host} (tcp:{port})"
            uid = f"domain_monitor_{host}_tcp_{port}"
            
        self._attr_name = name
        self._attr_unique_id = uid.replace(".", "_")

    @property
    def state(self):
        data = self.coordinator.data.get(self.service["host"])
        if not data:
            return "unknown"
        return data["status"]

    @property
    def extra_state_attributes(self):
        return self.coordinator.data.get(self.service["host"], {})