"""Local smoke test of the pure coordinator logic without a Home Assistant install.

Stubs the homeassistant modules that coordinator.py imports, then exercises
parsing, certificate parsing and helper functions with real assertions.
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# --- stub the homeassistant modules needed at import time ---
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
    pass


class DataUpdateCoordinator:
    def __init__(self, hass, logger=None, name=None, update_interval=None, config_entry=None):
        self.hass = hass
        self.data = {}


def async_get_clientsession(hass):
    return None


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

from custom_components.domain_monitor.coordinator import (  # noqa: E402
    normalize_services,
    parse_peer_cert,
    service_id,
    _socket_host,
)

failures = []


def check(name, condition, detail=""):
    status = "OK " if condition else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not condition:
        failures.append(name)


# Legacy string parsing
services, invalid = normalize_services(
    "example.com:https:443:Welcome, test.org:http, nas.local:tcp:22, bad:ftp:21"
)
check("legacy: 3 services parsed", len(services) == 3)
check("legacy: 1 invalid collected", len(invalid) == 1)
check("legacy: keyword parsed", services[0]["keyword"] == "Welcome")
check("legacy: default port http", services[1]["port"] == 80)
check("legacy: tcp port", services[2]["port"] == 22)

# JSON list parsing (incl. IPv6 bracket host)
services, invalid = normalize_services(
    [
        {"host": "example.com", "type": "https", "port": 8443, "keyword": "up"},
        {"host": "[::1]", "type": "tcp", "port": 443},
        {"host": "x.com", "type": "https"},
    ]
)
check("json: 3 services parsed", len(services) == 3 and invalid == [])
check("json: custom port kept", services[0]["port"] == 8443)
check("json: ipv6 host kept", services[1]["host"] == "[::1]")
check("json: default port resolved", services[2]["port"] == 443)

# Invalid entries collected for repair
services, invalid = normalize_services(
    ["example.com:ftp:21", "nas.local:tcp:notaport", "", {"host": "x.com", "type": "tcp"}]
)
check("invalid: nothing parsed", services == [])
check("invalid: 3 collected", len(invalid) == 3)

# Unique service ids
services, _ = normalize_services(
    [
        {"host": "example.com", "type": "https", "port": 443},
        {"host": "example.com", "type": "http", "port": 80},
        {"host": "example.com", "type": "tcp", "port": 22},
    ]
)
ids = {service_id(s) for s in services}
check("ids: unique", len(ids) == 3)

# Certificate parsing
cert = {
    "notAfter": "Nov 27 12:00:00 2027 GMT",
    "issuer": (("commonName", "R11"),),
    "subject": (("commonName", "example.com"),),
}
info = parse_peer_cert(cert)
check("cert: subject", info and info["subject"] == "example.com")
check("cert: issuer", info and info["issuer"] == "R11")
check("cert: days_left plausible", info and info["days_left"] > 300)
check("cert: empty dict rejected", parse_peer_cert({}) is None)
check("cert: garbage rejected", parse_peer_cert({"notAfter": "garbage"}) is None)

# IPv6 bracket stripping
check("socket host: hostname", _socket_host("example.com") == "example.com")
check("socket host: ipv6", _socket_host("[::1]") == "::1")

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("ALL CHECKS PASSED")
