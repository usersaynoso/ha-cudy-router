"""Support for Cudy Router select entities."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODULE_AUTO_UPDATE_SETTINGS,
    MODULE_CELLULAR_SETTINGS,
    MODULE_VPN_SETTINGS,
    MODULE_WIRELESS_SETTINGS,
)
from .coordinator import CudyRouterDataUpdateCoordinator
from .device_info import build_router_device_info
from .features import existing_feature

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class CudyRouterSelectDescription(SelectEntityDescription):
    """Describe a router-backed select entity."""

    module: str
    name_suffix: str


ROUTER_SELECTS: tuple[CudyRouterSelectDescription, ...] = (
    CudyRouterSelectDescription(
        key="sim_slot",
        module=MODULE_CELLULAR_SETTINGS,
        name_suffix="SIM slot",
        icon="mdi:sim",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="network_mode",
        module=MODULE_CELLULAR_SETTINGS,
        name_suffix="Network mode",
        icon="mdi:radio-tower",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="network_search",
        module=MODULE_CELLULAR_SETTINGS,
        name_suffix="Network search",
        icon="mdi:cellphone-search",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="apn_profile",
        module=MODULE_CELLULAR_SETTINGS,
        name_suffix="APN profile",
        icon="mdi:playlist-edit",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="pdp_type",
        module=MODULE_CELLULAR_SETTINGS,
        name_suffix="PDP type",
        icon="mdi:ip-network",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="wifi_2g_mode",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 2.4G mode",
        icon="mdi:wifi",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="wifi_2g_channel_width",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 2.4G channel width",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="wifi_2g_channel",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 2.4G channel",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="wifi_2g_tx_power",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 2.4G transmit power",
        icon="mdi:signal-distance-variant",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="wifi_5g_mode",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 5G mode",
        icon="mdi:wifi",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="wifi_5g_channel_width",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 5G channel width",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="wifi_5g_channel",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 5G channel",
        icon="mdi:wifi-settings",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="wifi_5g_tx_power",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 5G transmit power",
        icon="mdi:signal-distance-variant",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="protocol",
        module=MODULE_VPN_SETTINGS,
        name_suffix="VPN protocol",
        icon="mdi:vpn",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="default_rule",
        module=MODULE_VPN_SETTINGS,
        name_suffix="VPN default rule",
        icon="mdi:shield-link-variant",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="client_access",
        module=MODULE_VPN_SETTINGS,
        name_suffix="VPN client access",
        icon="mdi:lan-connect",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="vpn_policy",
        module=MODULE_VPN_SETTINGS,
        name_suffix="VPN policy",
        icon="mdi:shield-check",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSelectDescription(
        key="update_time",
        module=MODULE_AUTO_UPDATE_SETTINGS,
        name_suffix="Auto update time",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cudy Router select entities."""
    coordinator: CudyRouterDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    device_model = config_entry.data.get(CONF_MODEL, "default")

    entities = [
        CudyRouterSettingSelect(coordinator, description)
        for description in ROUTER_SELECTS
        if existing_feature(device_model, description.module)
        and coordinator.data
        and coordinator.data.get(description.module, {}).get(description.key)
    ]
    async_add_entities(entities)


class CudyRouterSettingSelect(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SelectEntity
):
    """Select entity backed by router settings pages."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        description: CudyRouterSelectDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = description.name_suffix
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-{description.module}-{description.key}"
        )
        self._attr_device_info = build_router_device_info(coordinator)

    def _setting_data(self) -> dict[str, Any]:
        """Return the latest setting payload."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get(self.entity_description.module, {}).get(self.entity_description.key, {})

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option label."""
        setting = self._setting_data()
        value = setting.get("value")
        options = setting.get("options", {})
        return options.get(value)

    @property
    def options(self) -> list[str]:
        """Return all valid option labels."""
        setting = self._setting_data()
        return list(setting.get("options", {}).values())

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        setting = self._setting_data()
        reverse_map = {
            label: value
            for value, label in setting.get("options", {}).items()
        }
        selected_value = reverse_map.get(option)
        if selected_value is None:
            _LOGGER.error(
                "Unknown option '%s' for %s",
                option,
                self.entity_description.key,
            )
            return

        module = self.entity_description.module
        api = self.coordinator.api
        if module == MODULE_CELLULAR_SETTINGS:
            result = await self.hass.async_add_executor_job(
                api.set_cellular_setting,
                self.entity_description.key,
                selected_value,
            )
        elif module == MODULE_WIRELESS_SETTINGS:
            result = await self.hass.async_add_executor_job(
                api.set_wireless_setting,
                self.entity_description.key,
                selected_value,
            )
        elif module == MODULE_VPN_SETTINGS:
            result = await self.hass.async_add_executor_job(
                api.set_vpn_setting,
                self.entity_description.key,
                selected_value,
            )
        elif module == MODULE_AUTO_UPDATE_SETTINGS:
            result = await self.hass.async_add_executor_job(
                api.set_auto_update_setting,
                self.entity_description.key,
                selected_value,
            )
        else:
            result = (0, f"Unsupported module: {module}")

        if result[0] in (200, 302):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error(
                "Failed to update %s: %s",
                self.entity_description.key,
                result[1],
            )
