"""LIVE test: run the real update cycle (real network, real hosts, real TLS).

Stubs only the HA framework (like simulate_cycle.py) but uses a REAL aiohttp
session, so we see exactly what a Home Assistant on this network sees:
- canary checks (internet_ok)
- HTTP/HTTPS/TCP checks of the configured hosts
- certificate probing
"""
import asyncio
import json
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
        self.bus = types.SimpleNamespace(async_fire=lambda *a, **k: None)


class DataUpdateCoordinator:
    def __init__(self, hass, logger=None, name=None, update_interval=None, config_entry=None):
        self.hass = hass
        self.data = {}

    def async_update_listeners(self):
        pass


config_entries.ConfigEntry = ConfigEntry
core.HomeAssistant = HomeAssistant
update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator


def async_get_clientsession(hass):
    import aiohttp

    return aiohttp.ClientSession()


aiohttp_client.async_get_clientsession = async_get_clientsession
issue_registry.IssueSeverity = "warning"

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

from custom_components.domain_monitor.coordinator import DomainDataCoordinator  # noqa: E402

SERVICES = [
    {"host": "hypnosentlebuch.ch", "type": "https", "port": 443, "keyword": None},
    {"host": "landscapehunter.ch", "type": "http", "port": 80, "keyword": None},
    {"host": "mail.manuelkleinert.ch", "type": "tcp", "port": 993, "keyword": None},
]


class FakeEntry:
    entry_id = "live_entry"
    title = "Live"
    data = {"services": SERVICES}
    options = {}


async def run():
    hass = HomeAssistant()
    coordinator = DomainDataCoordinator(hass, FakeEntry())

    print("=== Canary (Internet-Check) ===")
    ok = await coordinator._async_check_internet()
    print(f"internet_ok = {ok}")

    print("\n=== Voller Prüfzyklus (echte Hosts) ===")
    results = await coordinator._async_update_data()
    coordinator.data = results

    for sid, item in results.items():
        print(f"\n{sid}")
        print(f"  status      = {item.get('status')}")
        print(f"  code        = {item.get('code')}")
        print(f"  response_ms = {item.get('response_ms')}")
        print(f"  no_internet = {item.get('no_internet')}")

    print("\n=== Zertifikate (echte TLS-Probe) ===")
    await coordinator._async_refresh_certificates()
    for sid, info in coordinator.cert_data.items():
        print(f"\n{sid}")
        print(json.dumps(info, indent=2))

    await asyncio.get_running_loop().shutdown_default_executor()


asyncio.run(run())
