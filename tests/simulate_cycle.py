"""Extended local simulation: run the full update cycle with a fake session.

Stubs homeassistant like smoke_local.py, then checks:
- full _async_update_data cycle (http up + down, tcp) with response_ms present
- no_internet path flags
- disabled-service result storage AND response alignment (zip bug)
- cert refresh populating cert_data (via monkeypatched fetch)
- event firing on status change
"""
import asyncio
import sys
import types
from datetime import UTC, datetime
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
        self.bus = types.SimpleNamespace(async_fire=lambda *a, **k: fired_events.append((a, k)))


class DataUpdateCoordinator:
    def __init__(self, hass, logger=None, name=None, update_interval=None, config_entry=None):
        self.hass = hass
        self.data = {}

    def async_update_listeners(self):
        pass


def async_get_clientsession(hass):
    return FakeSession()


class IssueSeverity:
    WARNING = "warning"


config_entries.ConfigEntry = ConfigEntry
core.HomeAssistant = HomeAssistant
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

fired_events = []


class FakeResp:
    status = 200

    async def text(self):
        return "Hello World"

    @property
    def content(self):
        return types.SimpleNamespace(read=AsyncBytes())


class AsyncBytes:
    def __await__(self):
        async def _inner():
            return b"Hello World"
        return _inner().__await__()


class FakeSession:
    def get(self, *args, **kwargs):
        return FakeCtx()


class FakeCtx:
    async def __aenter__(self):
        return FakeResp()

    async def __aexit__(self, *args):
        return False


from custom_components.domain_monitor.coordinator import DomainDataCoordinator  # noqa: E402

failures = []


def check(name, condition, detail=""):
    status = "OK " if condition else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not condition:
        failures.append(name)


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


hass = HomeAssistant()
coordinator = DomainDataCoordinator(hass, FakeEntry())

# fake TLS cert fetch success + fake http success
async def fake_fetch(service):
    coordinator.cert_data[service["id"]] = {
        "expires_at": "2027-01-01T00:00:00+00:00",
        "days_left": 300,
        "issuer": "R11",
        "subject": service["host"],
        "checked_at": datetime.now(UTC).isoformat(),
    }


coordinator._async_fetch_certificate = fake_fetch
coordinator._internet_ok = True

results = asyncio.run(coordinator._async_update_data())
coordinator.data = results  # the real base class assigns the result to self.data

check("cycle: both services stored", len(results) == 2, f"keys={list(results)}")
check("cycle: response_ms present", all(r["response_ms"] is not None for r in results.values()))
check("cycle: status up", all(r["status"] == "up" for r in results.values()))
check("cycle: cert data stored", "a.com:https:443" in coordinator.cert_data, f"certs={list(coordinator.cert_data)}")
check("cycle: uptime", coordinator.uptime_percent("a.com:https:443") == 100.0)

# zip alignment bug: disable one service, update again
fired_events.clear()
coordinator.set_enabled("b.com:http:80", False)
results = asyncio.run(coordinator._async_update_data())
check("disabled: both results present", len(results) == 2, f"keys={list(results)}")
check("disabled: disabled service unknown+enabled False",
      results["b.com:http:80"]["status"] == "unknown" and results["b.com:http:80"]["enabled"] is False)
check("disabled: enabled service keeps data",
      results["a.com:https:443"]["host"] == "a.com" and results["a.com:https:443"]["status"] == "up")

# disabled-FIRST alignment check: a disabled service before an enabled one
# must not shift results (regression test for the zip misalignment)
class FakeEntry2(FakeEntry):
    data = {
        "services": [
            {"host": "paused.com", "type": "https", "port": 443, "keyword": None},
            {"host": "active.com", "type": "https", "port": 443, "keyword": None},
        ]
    }


hass2 = HomeAssistant()
coordinator2 = DomainDataCoordinator(hass2, FakeEntry2())
coordinator2._async_fetch_certificate = fake_fetch
coordinator2._internet_ok = True
coordinator2.set_enabled("paused.com:https:443", False)
results2 = asyncio.run(coordinator2._async_update_data())
coordinator2.data = results2

check("alignment: both results present", len(results2) == 2, f"keys={list(results2)}")
check("alignment: active.com got its own result",
      results2.get("active.com:https:443", {}).get("host") == "active.com")
check("alignment: paused.com got the disabled result",
      results2.get("paused.com:https:443", {}).get("enabled") is False
      and results2.get("paused.com:https:443", {}).get("host") == "paused.com")

# event on status change
async def failing_fetch(service):
    pass


async def down_http(session, service):
    return {
        "host": service["host"], "type": service["type"], "port": service["port"],
        "status": "down", "code": None, "response_ms": None, "slow": False,
        "time": datetime.now(UTC),
    }


fired_events.clear()
coordinator._async_fetch_certificate = failing_fetch
coordinator.check_http = down_http
coordinator._internet_ok = True
results3 = asyncio.run(coordinator._async_update_data())
coordinator.data = results3
check("event: fired on up->down", len(fired_events) == 1, f"events={len(fired_events)}")  # a.com up->down; b.com already unknown (disabled)

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL SIMULATION CHECKS PASSED")
