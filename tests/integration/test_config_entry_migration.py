"""Config-entry migration tests."""

from __future__ import annotations

import asyncio

from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_PASSWORD, CONF_USERNAME

import custom_components.cudy_router as cudy_init


class _ConfigEntries:
    def __init__(self) -> None:
        self.updated: dict[str, object] | None = None

    def async_update_entry(self, entry, **kwargs):  # noqa: ANN001, ANN003
        self.updated = {"entry": entry, **kwargs}


class _Hass:
    def __init__(self) -> None:
        self.config_entries = _ConfigEntries()


class _Entry:
    def __init__(self) -> None:
        self.version = 1
        self.data = {
            CONF_HOST: "192.168.10.1/",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        }


def test_async_migrate_entry_updates_schema_to_v2() -> None:
    """Migration should normalize host and backfill missing model."""
    hass = _Hass()
    entry = _Entry()

    migrated = asyncio.run(cudy_init.async_migrate_entry(hass, entry))

    assert migrated is True
    assert hass.config_entries.updated is not None
    assert hass.config_entries.updated["version"] == 2
    assert hass.config_entries.updated["data"][CONF_HOST] == "https://192.168.10.1"
    assert hass.config_entries.updated["data"][CONF_MODEL] == "default"
