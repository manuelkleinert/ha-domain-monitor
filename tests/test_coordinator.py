import pytest
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.domain_monitor.const import DOMAIN, EVENT_STATUS_CHANGED
from custom_components.domain_monitor.coordinator import (
    DomainDataCoordinator,
    normalize_services,
    parse_peer_cert,
    service_id,
)


def _coordinator(hass, services, options=None) -> DomainDataCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"services": services},
        options=options or {},
        title="Test",
    )
    return DomainDataCoordinator(hass, entry)


def test_parse_legacy_string():
    services, invalid = normalize_services("example.com:https:443:Welcome, test.org:http:80:, nas.local:tcp:22")
    assert len(services) == 3
    assert len(invalid) == 0
    assert services[0] == {"host": "example.com", "type": "https", "port": 443, "keyword": "Welcome"}
    assert services[1]["port"] == 80
    assert services[2] == {"host": "nas.local", "type": "tcp", "port": 22, "keyword": None}


def test_parse_json_list():
    raw = [
        {"host": "example.com", "type": "https", "port": 8443, "keyword": "up"},
        {"host": "[::1]", "type": "tcp", "port": 443},
    ]
    services, invalid = normalize_services(raw)
    assert invalid == []
    assert services[0]["port"] == 8443
    assert services[1]["host"] == "[::1]"


def test_parse_invalid_entries_collected():
    services, invalid = normalize_services(
        ["example.com:ftp:21", "nas.local:tcp:notaport", "", {"host": "x.com", "type": "tcp"}]
    )
    assert services == []
    assert len(invalid) == 3


def test_default_ports_applied():
    services, _ = normalize_services([{"host": "example.com", "type": "https", "port": None}])
    assert services[0]["port"] == 443
    services, _ = normalize_services("example.com:http:80:")
    assert services[0]["port"] == 80
    assert services[0]["keyword"] is None
    services, _ = normalize_services("example.com:https:Welcome")
    assert services[0]["port"] == 443
    assert services[0]["keyword"] == "Welcome"


def test_service_id_unique():
    services, _ = normalize_services(
        [
            {"host": "example.com", "type": "https", "port": 443},
            {"host": "example.com", "type": "http", "port": 80},
            {"host": "example.com", "type": "tcp", "port": 22},
        ]
    )
    ids = {service_id(s) for s in services}
    assert len(ids) == 3


def test_parse_peer_cert():
    cert = {
        "notAfter": "Nov 27 12:00:00 2027 GMT",
        "issuer": ((("commonName", "R11"),),),
        "subject": ((("commonName", "example.com"),),),
    }
    info = parse_peer_cert(cert)
    assert info["subject"] == "example.com"
    assert info["issuer"] == "R11"
    assert info["days_left"] > 300

    # Flat 2-tuple shape must also be handled
    flat = {
        "notAfter": "Nov 27 12:00:00 2027 GMT",
        "issuer": (("commonName", "R11"),),
        "subject": (("commonName", "example.com"),),
    }
    flat_info = parse_peer_cert(flat)
    assert flat_info["subject"] == "example.com"
    assert flat_info["issuer"] == "R11"

    assert parse_peer_cert({}) is None
    assert parse_peer_cert({"notAfter": "garbage"}) is None


async def test_no_internet_marks_unknown(hass):
    coordinator = _coordinator(hass, [{"host": "example.com", "type": "https", "port": 443}])

    with (
        patch.object(coordinator, "_async_check_internet", AsyncMock(return_value=False)),
        patch.object(coordinator, "_async_refresh_certificates", AsyncMock()),
    ):
        coordinator._internet_ok = False
        results = await coordinator._async_update_data()

    sid = "example.com:https:443"
    assert results[sid]["status"] == "unknown"
    assert results[sid]["no_internet"] is True


async def test_real_down_when_internet_ok(hass):
    coordinator = _coordinator(hass, [{"host": "example.com", "type": "https", "port": 443}])

    down = {
        "host": "example.com",
        "type": "https",
        "port": 443,
        "status": "down",
        "code": None,
        "response_ms": None,
        "slow": False,
        "time": None,
    }

    with (
        patch.object(coordinator, "_async_check_internet", AsyncMock(return_value=True)),
        patch.object(coordinator, "check_http", AsyncMock(return_value=down.copy())),
        patch.object(coordinator, "_async_refresh_certificates", AsyncMock()),
    ):
        results = await coordinator._async_update_data()

    assert results["example.com:https:443"]["status"] == "down"
    assert "no_internet" not in results["example.com:https:443"]


async def test_status_change_fires_event(hass):
    coordinator = _coordinator(hass, [{"host": "example.com", "type": "https", "port": 443}])

    events = []

    def listener(event):
        events.append(event)

    coordinator.hass.bus.async_listen(EVENT_STATUS_CHANGED, listener)

    up = {
        "host": "example.com",
        "type": "https",
        "port": 443,
        "status": "up",
        "code": 200,
        "response_ms": 10,
        "slow": False,
        "time": None,
    }
    down = {**up, "status": "down", "code": None, "response_ms": None}

    with (
        patch.object(coordinator, "_async_check_internet", AsyncMock(return_value=True)),
        patch.object(coordinator, "check_http", AsyncMock(return_value=up.copy())),
        patch.object(coordinator, "_async_refresh_certificates", AsyncMock()),
    ):
        await coordinator._async_update_data()

        with patch.object(coordinator, "check_http", AsyncMock(return_value=down.copy())):
            await coordinator._async_update_data()

    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["old_status"] == "up"
    assert events[0].data["new_status"] == "down"
    assert events[0].data["host"] == "example.com"


async def test_first_result_does_not_fire_event(hass):
    coordinator = _coordinator(hass, [{"host": "example.com", "type": "https", "port": 443}])
    up = {
        "host": "example.com",
        "type": "https",
        "port": 443,
        "status": "up",
        "code": 200,
        "response_ms": 10,
        "slow": False,
        "time": None,
    }

    events = []
    coordinator.hass.bus.async_listen(EVENT_STATUS_CHANGED, lambda e: events.append(e))

    with (
        patch.object(coordinator, "_async_check_internet", AsyncMock(return_value=True)),
        patch.object(coordinator, "check_http", AsyncMock(return_value=up.copy())),
        patch.object(coordinator, "_async_refresh_certificates", AsyncMock()),
    ):
        await coordinator._async_update_data()

    await hass.async_block_till_done()
    assert events == []


async def test_uptime_percent(hass):
    coordinator = _coordinator(hass, [{"host": "example.com", "type": "https", "port": 443}])
    sid = "example.com:https:443"

    assert coordinator.uptime_percent(sid) is None

    for status in ("up", "up", "down", "up"):
        coordinator.history[sid].append({"status": status})

    assert coordinator.uptime_percent(sid) == 75.0


async def test_disabled_service_skipped(hass):
    coordinator = _coordinator(hass, [{"host": "example.com", "type": "https", "port": 443}])
    sid = "example.com:https:443"
    coordinator.set_enabled(sid, False)

    assert coordinator.data[sid]["status"] == "unknown"
    assert coordinator.data[sid]["enabled"] is False


async def test_slow_flag(hass):
    coordinator = _coordinator(hass, [{"host": "example.com", "type": "https", "port": 443}], options={"slow_threshold_ms": 100})

    slow_up = {
        "host": "example.com",
        "type": "https",
        "port": 443,
        "status": "up",
        "code": 200,
        "response_ms": 500,
        "slow": True,
        "time": None,
    }

    with (
        patch.object(coordinator, "_async_check_internet", AsyncMock(return_value=True)),
        patch.object(coordinator, "check_http", AsyncMock(return_value=slow_up.copy())),
        patch.object(coordinator, "_async_refresh_certificates", AsyncMock()),
    ):
        results = await coordinator._async_update_data()

    assert results["example.com:https:443"]["slow"] is True


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("example.com", "example.com"),
        ("[::1]", "::1"),
    ],
)
def test_socket_host(host, expected):
    from custom_components.domain_monitor.coordinator import _socket_host

    assert _socket_host(host) == expected
