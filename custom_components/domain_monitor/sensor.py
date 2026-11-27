from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device import build_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for service in coordinator.services:
        entities.append(DomainSensor(coordinator, service))
        entities.append(DomainResponseTimeSensor(coordinator, service))
        if service["type"] == "https":
            entities.append(DomainCertificateSensor(coordinator, service))

    async_add_entities(entities)


def _service_label(service: dict) -> str:
    if service["type"] == "tcp":
        return f"{service['host']} (tcp:{service['port']})"
    return f"{service['host']} ({service['type']}:{service['port']})"


def _unique_id_base(coordinator, service: dict) -> str:
    return f"domain_monitor_{coordinator.entry.entry_id}_{service['id']}"


class DomainSensor(CoordinatorEntity):
    """Availability sensor that updates on every coordinator refresh."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, service: dict):
        super().__init__(coordinator)
        self.service = service
        self._attr_translation_key = "status"
        self._attr_translation_placeholders = {"host": _service_label(service)}
        self._attr_unique_id = f"{_unique_id_base(coordinator, service)}_status"
        self._attr_device_info = build_device_info(coordinator.entry)
        self._attr_icon = {
            "https": "mdi:shield-check",
            "http": "mdi:web",
            "tcp": "mdi:lan",
        }[service["type"]]

    @property
    def state(self):
        data = self.coordinator.data.get(self.service["id"])
        if not data:
            return "unknown"
        return data["status"]

    @property
    def extra_state_attributes(self):
        attributes = dict(self.coordinator.data.get(self.service["id"], {}))
        uptime = self.coordinator.uptime_percent(self.service["id"])
        if uptime is not None:
            attributes["uptime_percent"] = uptime
        return attributes


class DomainResponseTimeSensor(CoordinatorEntity, SensorEntity):
    """Response time of the last check in milliseconds (graphable)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, service: dict):
        super().__init__(coordinator)
        self.service = service
        self._attr_translation_key = "response_time"
        self._attr_translation_placeholders = {"host": _service_label(service)}
        self._attr_unique_id = f"{_unique_id_base(coordinator, service)}_response_time"
        self._attr_device_info = build_device_info(coordinator.entry)
        self._attr_icon = "mdi:speedometer"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_native_unit_of_measurement = "ms"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.service["id"])
        if not data or data.get("response_ms") is None:
            return None
        return round(data["response_ms"])


class DomainCertificateSensor(CoordinatorEntity, SensorEntity):
    """Days until the TLS certificate of an HTTPS service expires."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, service: dict):
        super().__init__(coordinator)
        self.service = service
        self._attr_translation_key = "certificate"
        self._attr_translation_placeholders = {"host": _service_label(service)}
        self._attr_unique_id = f"{_unique_id_base(coordinator, service)}_certificate"
        self._attr_device_info = build_device_info(coordinator.entry)
        self._attr_icon = "mdi:certificate"
        self._attr_native_unit_of_measurement = "d"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        info = self.coordinator.cert_info(self.service["id"])
        if not info or "days_left" not in info:
            return None
        return info["days_left"]

    @property
    def extra_state_attributes(self):
        return dict(self.coordinator.cert_info(self.service["id"]) or {})
