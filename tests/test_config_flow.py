"""Test Cudy Router config flow."""

from unittest.mock import MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.cudy_router.const import DOMAIN

from .conftest import MOCK_CONFIG


async def test_form(hass: HomeAssistant, mock_setup_entry, mock_router) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: MOCK_CONFIG[CONF_HOST],
            CONF_USERNAME: MOCK_CONFIG[CONF_USERNAME],
            CONF_PASSWORD: MOCK_CONFIG[CONF_PASSWORD],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_CONFIG[CONF_HOST]
    assert result["data"] == {
        CONF_HOST: f"https://{MOCK_CONFIG[CONF_HOST]}",
        CONF_USERNAME: MOCK_CONFIG[CONF_USERNAME],
        CONF_PASSWORD: MOCK_CONFIG[CONF_PASSWORD],
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_with_name(hass: HomeAssistant, mock_setup_entry, mock_router) -> None:
    """Test form with optional name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: MOCK_CONFIG[CONF_HOST],
            CONF_USERNAME: MOCK_CONFIG[CONF_USERNAME],
            CONF_PASSWORD: MOCK_CONFIG[CONF_PASSWORD],
            CONF_NAME: "My Router",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "My Router"


async def test_form_invalid_auth(
    hass: HomeAssistant, mock_setup_entry, mock_router_auth_fail
) -> None:
    """Test we handle invalid auth."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: MOCK_CONFIG[CONF_HOST],
            CONF_USERNAME: MOCK_CONFIG[CONF_USERNAME],
            CONF_PASSWORD: "wrong_password",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_cannot_connect(hass: HomeAssistant, mock_setup_entry) -> None:
    """Test we handle cannot connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.cudy_router.config_flow.CudyRouter"
    ) as mock_router_class:
        mock_router_class.side_effect = Exception("Connection error")

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: MOCK_CONFIG[CONF_HOST],
                CONF_USERNAME: MOCK_CONFIG[CONF_USERNAME],
                CONF_PASSWORD: MOCK_CONFIG[CONF_PASSWORD],
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_already_configured(
    hass: HomeAssistant, mock_setup_entry, mock_router
) -> None:
    """Test we handle already configured error."""
    # Create an existing entry
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Existing Router",
        data={
            CONF_HOST: f"https://{MOCK_CONFIG[CONF_HOST]}",
            CONF_USERNAME: MOCK_CONFIG[CONF_USERNAME],
            CONF_PASSWORD: MOCK_CONFIG[CONF_PASSWORD],
        },
        source=config_entries.SOURCE_USER,
        unique_id=f"https://{MOCK_CONFIG[CONF_HOST]}",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: MOCK_CONFIG[CONF_HOST],
            CONF_USERNAME: MOCK_CONFIG[CONF_USERNAME],
            CONF_PASSWORD: MOCK_CONFIG[CONF_PASSWORD],
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
