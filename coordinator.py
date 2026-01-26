"""Coordinator for Cudy Router integration."""
from datetime import timedelta
import logging
from typing import Any

import async_timeout

from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL

from .router import CudyRouter

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CudyRouterDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Get the latest data from the router."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: CudyRouter
    ) -> None:
        """Initialize router data."""
        self.hass = hass
        self.config_entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.api = api
        scan_interval = (entry.options and entry.options.get(CONF_SCAN_INTERVAL)) or 15
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} - {self.host}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from the router."""
        async with async_timeout.timeout(30):
            try:
                return await self.api.get_data(self.hass, self.config_entry.options)
            except Exception as err:
                raise UpdateFailed from err
