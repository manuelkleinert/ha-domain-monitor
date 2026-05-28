from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for service in coordinator.services:
        entities.append(DomainMonitorButton(coordinator, service))
    
    async_add_entities(entities)

class DomainMonitorButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, service):
        super().__init__(coordinator)
        self.service = service
        self.host = service["host"]
        
        self._attr_name = f"Check {self.host} Now"
        self._attr_icon = "mdi:refresh"

    @property
    def unique_id(self):
        return f"{self.coordinator.entry.entry_id}_{self.host}_check_button"

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.async_request_refresh()
