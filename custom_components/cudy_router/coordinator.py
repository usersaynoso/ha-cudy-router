"""Coordinator for Cudy Router integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MODEL, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .router import CudyRouter

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = 15
REQUEST_TIMEOUT = 30


class CudyRouterDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Get the latest data from the router."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: CudyRouter) -> None:
        """Initialize router data."""
        self.config_entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.api = api
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} - {self.host}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from the router."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                return await self.api.get_data(
                    self.hass,
                    self.config_entry.options,
                    self.config_entry.data[CONF_MODEL],
                )
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout communicating with router: {err}") from err
        except Exception as err:
            _LOGGER.error(err)
            raise UpdateFailed(f"Error communicating with router: {err}") from err
