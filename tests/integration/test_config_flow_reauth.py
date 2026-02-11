"""Config-flow reauthentication tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_PASSWORD, CONF_USERNAME

import custom_components.cudy_router.config_flow as cudy_config_flow


class _FakeConfigEntries:
    def __init__(self, entry) -> None:  # noqa: ANN001
        self.entry = entry
        self.updated_data: dict[str, str] | None = None
        self.reload_entry_id: str | None = None

    def async_get_entry(self, entry_id: str):  # noqa: ANN201
        if self.entry.entry_id == entry_id:
            return self.entry
        return None

    def async_update_entry(self, _entry, data):  # noqa: ANN001, ANN201
        self.updated_data = data

    async def async_reload(self, entry_id: str) -> None:
        self.reload_entry_id = entry_id


class _FakeHass:
    def __init__(self, config_entries: _FakeConfigEntries) -> None:
        self.config_entries = config_entries


def test_reauth_step_routes_to_reauth_confirm() -> None:
    """Reauth step should bind the target entry and show confirm form."""
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            CONF_HOST: "https://192.168.10.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old",
            CONF_MODEL: "default",
        },
    )
    config_entries = _FakeConfigEntries(entry)

    flow = cudy_config_flow.CudyRouterConfigFlow()
    flow.hass = _FakeHass(config_entries)
    flow.context = {"entry_id": "entry-1"}

    result = asyncio.run(flow.async_step_reauth({}))

    assert flow._reauth_entry is entry
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


def test_reauth_confirm_updates_entry_on_success(monkeypatch) -> None:  # noqa: ANN001
    """Successful reauth should update entry data and abort as successful."""
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            CONF_HOST: "https://192.168.10.1",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old",
            CONF_MODEL: "default",
        },
    )
    config_entries = _FakeConfigEntries(entry)

    flow = cudy_config_flow.CudyRouterConfigFlow()
    flow.hass = _FakeHass(config_entries)
    flow._reauth_entry = entry

    async def _fake_validate_input(_hass, data):  # noqa: ANN001
        return {
            "title": "Cudy Router",
            "host": data[CONF_HOST],
            "device_model": data.get(CONF_MODEL, "default"),
        }

    monkeypatch.setattr(cudy_config_flow, "validate_input", _fake_validate_input)

    result = asyncio.run(
        flow.async_step_reauth_confirm(
            {
                CONF_USERNAME: "new-admin",
                CONF_PASSWORD: "new-password",
            }
        )
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert config_entries.updated_data is not None
    assert config_entries.updated_data[CONF_USERNAME] == "new-admin"
    assert config_entries.updated_data[CONF_PASSWORD] == "new-password"
    assert config_entries.reload_entry_id == "entry-1"
