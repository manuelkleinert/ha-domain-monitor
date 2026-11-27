import pytest
from homeassistant import config_entries, setup
from homeassistant.data_entry_flow import InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.domain_monitor.const import DOMAIN
from custom_components.domain_monitor.config_flow import _resolve_port


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
    # Schema violations are rejected by the flow manager itself (InvalidData)
    with pytest.raises(InvalidData) as exc:
        await hass.config_entries.flow.async_configure(
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
    assert "host" in str(exc.value)


async def test_user_flow_rejects_out_of_range(hass):
    await setup.async_setup_component(hass, "http", {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with pytest.raises(InvalidData) as exc:
        await hass.config_entries.flow.async_configure(
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
    assert "interval" in str(exc.value) or "retries" in str(exc.value)


def test_resolve_port():
    assert _resolve_port("https", None) == 443
    assert _resolve_port("http", 0) == 80
    assert _resolve_port("tcp", 8080) == 8080


async def test_options_flow_menu_then_settings(hass):
    await setup.async_setup_component(hass, "http", {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "services": [{"host": "example.com", "type": "https", "port": 443, "keyword": None}],
            "interval": 120,
        },
        options={},
        title="example.com (https)",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert set(result["menu_options"]) == {"settings", "manage"}

    # Navigate to the settings form and quick-save the tuning
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "settings"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "interval": 300,
            "timeout": 10,
            "retries": 3,
            "slow_threshold_ms": 2000,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["data"]["interval"] == 300
    assert len(result["data"]["services"]) == 1
