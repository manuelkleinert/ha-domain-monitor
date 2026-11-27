"""Simulate the options-flow service editor end-to-end with stubbed HA.

Drives: init -> manage (menu) -> add -> manage -> edit -> manage -> delete ->
manage -> done (save). Verifies the working list, error paths and the final
options payload.
"""
import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# --- stub homeassistant modules needed at import time ---
ha = types.ModuleType("homeassistant")
config_entries = types.ModuleType("homeassistant.config_entries")
core = types.ModuleType("homeassistant.core")
helpers = types.ModuleType("homeassistant.helpers")
update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
issue_registry = types.ModuleType("homeassistant.helpers.issue_registry")


class ConfigEntry:
    pass


class HomeAssistant:
    def __init__(self):
        self.updated = []
        self.config_entries = types.SimpleNamespace(
            async_update_entry=lambda *args, **kwargs: self.updated.append((args, kwargs))
        )


class _FlowBase:
    def __init_subclass__(cls, **kwargs):
        kwargs.pop("domain", None)
        super().__init_subclass__(**kwargs)
        cls._domain = kwargs.get("domain")

    def async_show_form(self, *, step_id, data_schema=None, errors=None, description_placeholders=None):
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def async_show_menu(self, *, step_id, menu_options, description_placeholders=None):
        return {
            "type": "menu",
            "step_id": step_id,
            "menu_options": menu_options,
            "description_placeholders": description_placeholders or {},
        }

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}


class DataUpdateCoordinator:
    def __init__(self, hass, logger=None, name=None, update_interval=None, config_entry=None):
        self.hass = hass
        self.data = {}


def async_get_clientsession(hass):
    return None


class IssueSeverity:
    WARNING = "warning"


config_entries.ConfigFlow = _FlowBase
config_entries.OptionsFlow = _FlowBase
config_entries.ConfigEntry = ConfigEntry
core.HomeAssistant = HomeAssistant
core.callback = lambda f: f
update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
aiohttp_client.async_get_clientsession = async_get_clientsession
issue_registry.IssueSeverity = IssueSeverity

for name, module in [
    ("homeassistant", ha),
    ("homeassistant.config_entries", config_entries),
    ("homeassistant.core", core),
    ("homeassistant.helpers", helpers),
    ("homeassistant.helpers.update_coordinator", update_coordinator),
    ("homeassistant.helpers.aiohttp_client", aiohttp_client),
    ("homeassistant.helpers.issue_registry", issue_registry),
]:
    sys.modules[name] = module
ha.helpers = helpers
helpers.update_coordinator = update_coordinator
helpers.issue_registry = issue_registry
helpers.aiohttp_client = aiohttp_client

from custom_components.domain_monitor.config_flow import (  # noqa: E402
    DomainMonitorOptionsFlowHandler,
)


class FakeEntry:
    entry_id = "test_entry"
    title = "Test"
    data = {
        "services": [
            {"host": "a.com", "type": "https", "port": 443, "keyword": None},
            {"host": "b.com", "type": "http", "port": 80, "keyword": None},
        ]
    }
    options = {}


failures = []


def check(name, condition, detail=""):
    status = "OK " if condition else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not condition:
        failures.append(name)


TUNING = {"interval": 60, "timeout": 10, "retries": 3, "slow_threshold_ms": 2000}


async def run():
    hass = HomeAssistant()
    entry = FakeEntry()
    handler = DomainMonitorOptionsFlowHandler()
    handler.hass = hass
    handler.config_entry = entry  # the real framework sets this on the handler

    # 1) init is a menu with two paths
    result = await handler.async_step_init()
    check("init: shows menu", result["type"] == "menu" and result["step_id"] == "init")
    check("init: has settings+manage buttons", set(result["menu_options"]) == {"settings", "manage"})

    # 2) settings path: tuning form, saves immediately (services untouched)
    result = await handler.async_step_settings()
    check("settings: shows form", result["type"] == "form" and result["step_id"] == "settings")
    result = await handler.async_step_settings(TUNING)
    check("settings: create_entry", result["type"] == "create_entry")
    check("settings: tuning saved", result["data"]["interval"] == 60)
    check("settings: services kept", len(result["data"]["services"]) == 2)

    # 3) manage path: menu with the service list
    result = await handler.async_step_manage()
    check("manage: shows menu", result["type"] == "menu" and result["step_id"] == "manage")
    check("manage: has 4 buttons", set(result["menu_options"]) == {"add_service", "edit_service", "delete_service", "done"})
    check("manage: list in description", "a.com (https:443)" in result["description_placeholders"]["services_list"])

    # 4) add a new service
    result = await handler.async_step_add_service()
    check("add: shows service form", result["type"] == "form" and result["step_id"] == "service")
    result = await handler.async_step_service(
        {"host": "c.com", "type": "https", "port": 443, "keyword": "up"}
    )
    check("add: back to menu", result["type"] == "menu")
    check("add: list now 3 entries", "c.com (https:443)" in handler._services_list_markdown())

    # 5) duplicate is rejected
    result = await handler.async_step_add_service()
    result = await handler.async_step_service(
        {"host": "c.com", "type": "https", "port": 443, "keyword": ""}
    )
    check("duplicate: rejected", result["errors"].get("base") == "duplicate_service")

    # 6) edit existing service (change port)
    result = await handler.async_step_edit_service()
    check("edit: shows select", result["type"] == "form" and result["step_id"] == "edit_service")
    result = await handler.async_step_edit_service({"service": "b.com:http:80"})
    check("edit: prefilled form", result["type"] == "form" and result["step_id"] == "service")
    result = await handler.async_step_service(
        {"host": "b.com", "type": "http", "port": 8080, "keyword": ""}
    )
    check("edit: back to menu", result["type"] == "menu")
    check("edit: port changed", "b.com (http:8080)" in handler._services_list_markdown())

    # 7) delete a service
    result = await handler.async_step_delete_service()
    check("delete: shows select", result["type"] == "form" and result["step_id"] == "delete_service")
    result = await handler.async_step_delete_service({"service": "b.com:http:8080"})
    check("delete: back to menu", result["type"] == "menu")
    check("delete: entry removed", "b.com" not in handler._services_list_markdown())

    # 8) deleting the last remaining service is blocked
    result = await handler.async_step_delete_service()
    result = await handler.async_step_delete_service({"service": "a.com:https:443"})
    check("delete second-to-last: allowed", result["type"] == "menu")
    result = await handler.async_step_delete_service()
    result = await handler.async_step_delete_service({"service": "c.com:https:443"})
    check("delete last: blocked", result["errors"].get("base") == "at_least_one")

    # 9) done -> saves working list, keeps the tuning from the entry
    result = await handler.async_step_done()
    check("done: create_entry", result["type"] == "create_entry")
    check("done: services saved", len(result["data"]["services"]) == 1)
    check("done: entry title updated", hass.updated[-1][1].get("title") == "c.com (https:443)")


asyncio.run(run())

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL FLOW SIMULATION CHECKS PASSED")
