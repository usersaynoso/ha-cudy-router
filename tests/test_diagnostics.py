"""Tests for Home Assistant diagnostics payload generation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
diagnostics = load_cudy_module("diagnostics")


class _FakeHass:
    def __init__(self, coordinator) -> None:
        self.data = {const.DOMAIN: {coordinator.config_entry.entry_id: coordinator}}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class _NoProbeApi:
    def debug_get(self, path: str) -> dict[str, object]:
        raise AssertionError(f"diagnostics should not probe {path}")


def test_config_entry_diagnostics_uses_cached_data_without_live_router_probes() -> None:
    """Diagnostics downloads should return quickly from cached integration state."""
    config_entry = SimpleNamespace(
        entry_id="entry123",
        title="Office Router",
        version=3,
        domain=const.DOMAIN,
        data={"host": "192.168.10.1", "username": "admin", "password": "secret", "model": "LT500D"},
        options={},
    )
    coordinator = SimpleNamespace(
        config_entry=config_entry,
        api=_NoProbeApi(),
        data={
            "modem": {
                "network": {"value": "4G"},
                "signal": {"value": 2},
            },
        },
    )

    payload = asyncio.run(
        diagnostics.async_get_config_entry_diagnostics(
            _FakeHass(coordinator),
            config_entry,
        )
    )

    assert payload["diagnostics"]["live_endpoint_probes_included"] is False
    assert payload["diagnostics"]["full_probe_report_action"] == "cudy_router.generate_debug_report"
    assert payload["coordinator"]["data"]["modem"]["signal"]["value"] == 2
    assert payload["probes"]["modem"] == []
