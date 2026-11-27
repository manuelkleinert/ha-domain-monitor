from homeassistant import config_entries, setup

from custom_components.domain_monitor.const import DOMAIN
from custom_components.domain_monitor.config_flow import (
    DomainMonitorOptionsFlowHandler,
    _resolve_port,
)


async def test_user_flow_creates_json_services(hass):
    await setup.async_setup_component(hass, "http", {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "example.com",
            "type": "https",
            "port": 443,
            "keyword": "Welcome",
            "interval": 60,
            "timeout": 10,
            "retries": 3,
            "slow_threshold_ms": 2000,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    entry_data = result["result"].data
    assert isinstance(entry_data["services"], list)
    assert entry_data["services"][0] == {
        "host": "example.com",
        "type": "https",
        "port": 443,
        "keyword": "Welcome",
    }


async def test_user_flow_rejects_bad_host(hass):
    await setup.async_setup_component(hass, "http", {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "https://evil.com/path",
            "type": "https",
            "port": 443,
            "keyword": "",
            "interval": 60,
            "timeout": 10,
            "retries": 3,
            "slow_threshold_ms": 2000,
        },
    )
    assert result["type"] == "form"
    assert result["errors"] == {"host": "does not match regular expression"}


async def test_user_flow_rejects_out_of_range(hass):
    await setup.async_setup_component(hass, "http", {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "example.com",
            "type": "https",
            "port": 443,
            "keyword": "",
            "interval": 5,
            "timeout": 10,
            "retries": 0,
            "slow_threshold_ms": 2000,
        },
    )
    assert result["type"] == "form"
    assert result["errors"]


def test_resolve_port():
    assert _resolve_port("https", None) == 443
    assert _resolve_port("http", 0) == 80
    assert _resolve_port("tcp", 8080) == 8080


def test_options_flow_init_stores_entry():
    entry = type("Entry", (), {"entry_id": "x", "data": {}, "options": {}, "title": "t"})()
    handler = DomainMonitorOptionsFlowHandler(entry)
    assert handler._entry is entry
