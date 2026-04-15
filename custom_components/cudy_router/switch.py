"""Support for Cudy Router Switch Platform."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODULE_AUTO_UPDATE_SETTINGS,
    MODULE_CELLULAR_SETTINGS,
    MODULE_DEVICES,
    MODULE_MESH,
    MODULE_VPN_SETTINGS,
    MODULE_WIRELESS_SETTINGS,
    OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
    OPTIONS_DEVICELIST,
    SECTION_DEVICE_LIST,
)
from .coordinator import CudyRouterDataUpdateCoordinator
from .device_info import (
    async_cleanup_stale_client_entities,
    async_cleanup_stale_mesh_entities,
    build_client_device_info,
    build_mesh_device_info,
    build_router_device_info,
    mesh_display_name,
    router_display_name,
)
from .device_tracking import normalize_mac
from .device_tracking import configured_device_ids, is_selected_device
from .features import existing_feature

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class CudyRouterSettingSwitchDescription(SwitchEntityDescription):
    """Describe a configurable router switch entity."""

    module: str
    name_suffix: str


ROUTER_SETTING_SWITCHES: tuple[CudyRouterSettingSwitchDescription, ...] = (
    CudyRouterSettingSwitchDescription(
        key="enabled",
        module=MODULE_CELLULAR_SETTINGS,
        name_suffix="Cellular enabled",
        icon="mdi:sim",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="data_roaming",
        module=MODULE_CELLULAR_SETTINGS,
        name_suffix="Data roaming",
        icon="mdi:earth",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="smart_connect",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="Smart Connect",
        icon="mdi:wifi-sync",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="wifi_2g_enabled",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 2.4G enabled",
        icon="mdi:wifi",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="wifi_5g_enabled",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 5G enabled",
        icon="mdi:wifi",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="wifi_2g_hidden",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 2.4G hidden network",
        icon="mdi:eye-off",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="wifi_5g_hidden",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 5G hidden network",
        icon="mdi:eye-off",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="wifi_2g_isolate",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 2.4G separate clients",
        icon="mdi:account-network",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="wifi_5g_isolate",
        module=MODULE_WIRELESS_SETTINGS,
        name_suffix="WiFi 5G separate clients",
        icon="mdi:account-network",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="enabled",
        module=MODULE_VPN_SETTINGS,
        name_suffix="VPN enabled",
        icon="mdi:vpn",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="site_to_site",
        module=MODULE_VPN_SETTINGS,
        name_suffix="VPN site-to-site",
        icon="mdi:router-network",
        entity_category=EntityCategory.CONFIG,
    ),
    CudyRouterSettingSwitchDescription(
        key="auto_update",
        module=MODULE_AUTO_UPDATE_SETTINGS,
        name_suffix="Auto update",
        icon="mdi:update",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Cudy Router switches."""
    coordinator: CudyRouterDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    router_name = router_display_name(config_entry, coordinator.data)
    device_model = config_entry.data.get(CONF_MODEL, "default")

    entities: list[SwitchEntity] = []
    entity_registry = async_get_entity_registry(hass)

    def _remove_main_router_led_entity() -> None:
        """Remove the main-router LED entity when the model does not support it."""
        unique_id = f"{config_entry.entry_id}-main-router-led"
        entity_id = entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)
        if entity_id:
            entity_registry.async_remove(entity_id)

    for description in ROUTER_SETTING_SWITCHES:
        if (
            existing_feature(device_model, description.module)
            and coordinator.data
            and coordinator.data.get(description.module, {}).get(description.key)
            is not None
        ):
            entities.append(
                CudyRouterSettingSwitch(
                    coordinator,
                    router_name,
                    description,
                )
            )

    mesh_data = coordinator.data.get(MODULE_MESH, {}) if coordinator.data else {}
    main_router_led_supported = (
        existing_feature(device_model, MODULE_MESH)
        and mesh_data.get("main_router_led_status") is not None
    )
    if main_router_led_supported:
        entities.append(
            CudyMainRouterLEDSwitch(
                coordinator,
                router_name,
            )
        )
    else:
        _remove_main_router_led_entity()

    # Add mesh device switches
    if coordinator.data and existing_feature(device_model, MODULE_MESH):
        mesh_devices = mesh_data.get("mesh_devices", {})
        async_cleanup_stale_mesh_entities(
            hass,
            config_entry,
            "switch",
            set(mesh_devices),
        )
        
        for mesh_mac, mesh_device in mesh_devices.items():
            # Add LED switch for each mesh device
            entities.append(
                CudyMeshLEDSwitch(
                    coordinator,
                    router_name,
                    mesh_mac,
                    mesh_device,
                )
            )

    seen_client_features: set[tuple[str, str]] = set()
    if coordinator.data:
        auto_add_connected_devices = config_entry.options.get(
            OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
            True,
        )
        selected_ids = configured_device_ids(config_entry.options.get(OPTIONS_DEVICELIST))
        devices = coordinator.data.get(MODULE_DEVICES, {}).get(SECTION_DEVICE_LIST, [])
        matched_connected_devices = [
            device
            for device in devices
            if isinstance(device, dict)
            and (auto_add_connected_devices or is_selected_device(device, selected_ids))
        ]
        async_cleanup_stale_client_entities(
            hass,
            config_entry,
            "switch",
            {device.get("mac") for device in matched_connected_devices},
        )

        for device in matched_connected_devices:

            normalized_mac = normalize_mac(device.get("mac"))
            if not normalized_mac:
                continue

            for feature_key, name_suffix, icon in (
                ("internet", "Internet access", "mdi:web"),
                ("dnsfilter", "DNS filter", "mdi:dns"),
                ("vpn", "VPN", "mdi:vpn"),
            ):
                if device.get(feature_key) is None:
                    continue

                feature_id = (normalized_mac, feature_key)
                if feature_id in seen_client_features:
                    continue

                seen_client_features.add(feature_id)
                entities.append(
                    CudyClientFeatureSwitch(
                        coordinator,
                        config_entry,
                        device,
                        feature_key,
                        name_suffix,
                        icon,
                    )
                )

    async_add_entities(entities)


class CudyRouterSettingSwitch(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SwitchEntity
):
    """Switch entity backed by a router configuration page."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str,
        description: CudyRouterSettingSwitchDescription,
    ) -> None:
        """Initialize the router setting switch."""
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
    def is_on(self) -> bool | None:
        """Return the current setting value."""
        return self._setting_data().get("value")

    async def _set_value(self, value: bool) -> None:
        """Write a new value via the appropriate router endpoint."""
        module = self.entity_description.module
        api = self.coordinator.api

        if module == MODULE_CELLULAR_SETTINGS:
            result = await self.hass.async_add_executor_job(
                api.set_cellular_setting,
                self.entity_description.key,
                value,
            )
        elif module == MODULE_WIRELESS_SETTINGS and self.entity_description.key == "smart_connect":
            result = await self.hass.async_add_executor_job(api.set_smart_connect, value)
        elif module == MODULE_WIRELESS_SETTINGS:
            result = await self.hass.async_add_executor_job(
                api.set_wireless_setting,
                self.entity_description.key,
                value,
            )
        elif module == MODULE_VPN_SETTINGS:
            result = await self.hass.async_add_executor_job(
                api.set_vpn_setting,
                self.entity_description.key,
                value,
            )
        elif module == MODULE_AUTO_UPDATE_SETTINGS:
            result = await self.hass.async_add_executor_job(
                api.set_auto_update_setting,
                self.entity_description.key,
                value,
            )
        else:
            result = (0, f"Unsupported switch module: {module}")

        if result[0] in (200, 302):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error(
                "Failed to update %s: %s",
                self.entity_description.key,
                result[1],
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self._set_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self._set_value(False)


class CudyClientFeatureSwitch(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SwitchEntity
):
    """Per-client internet, DNS filter, and VPN switches."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        config_entry: ConfigEntry,
        device: dict[str, Any],
        feature_key: str,
        name_suffix: str,
        icon: str,
    ) -> None:
        """Initialize the client feature switch."""
        super().__init__(coordinator)
        self._feature_key = feature_key
        self._normalized_mac = normalize_mac(device.get("mac"))
        self._fallback_device = device
        self._attr_name = name_suffix
        self._attr_icon = icon
        self._attr_unique_id = (
            f"{config_entry.entry_id}-device-{self._normalized_mac}-{feature_key}"
        )
        self._attr_device_info = build_client_device_info(config_entry, device)

    def _current_device(self) -> dict[str, Any]:
        """Return the latest device payload."""
        if self.coordinator.data:
            devices = self.coordinator.data.get(MODULE_DEVICES, {}).get(SECTION_DEVICE_LIST, [])
            for device in devices:
                if normalize_mac(device.get("mac")) == self._normalized_mac:
                    return device
        return self._fallback_device

    @property
    def is_on(self) -> bool | None:
        """Return the current feature state."""
        return self._current_device().get(self._feature_key)

    async def _set_value(self, value: bool) -> None:
        """Toggle the requested feature if needed."""
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.set_device_access,
            self._current_device(),
            self._feature_key,
            value,
        )
        if result[0] in (200, 302):
            self._fallback_device[self._feature_key] = value
            if self.coordinator.data:
                devices = self.coordinator.data.get(MODULE_DEVICES, {}).get(SECTION_DEVICE_LIST, [])
                for device in devices:
                    if normalize_mac(device.get("mac")) == self._normalized_mac:
                        device[self._feature_key] = value
                        break
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error(
                "Failed to update %s for %s: %s",
                self._feature_key,
                self._normalized_mac,
                result[1],
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the feature."""
        await self._set_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the feature."""
        await self._set_value(False)


class CudyMainRouterLEDSwitch(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SwitchEntity
):
    """Switch to control main router LEDs."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:led-on"

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str,
    ) -> None:
        """Initialize the main router LED switch."""
        super().__init__(coordinator)
        self._router_name = router_name
        self._attr_name = "LED"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-main-router-led"
        )
        self._attr_device_info = build_router_device_info(coordinator)
        self._is_on: bool = True  # Default to on

    @property
    def is_on(self) -> bool:
        """Return true if LED is on."""
        return self._is_on

    @property
    def icon(self) -> str:
        """Return the icon based on LED state."""
        return "mdi:led-on" if self._is_on else "mdi:led-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the LED on."""
        _LOGGER.info("Main router LED switch: turning ON")
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.set_main_router_led, True
        )
        _LOGGER.info("Main router LED ON result: %s", result)
        if result[0] in (200, 302):
            self._is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on LED for main router: %s", result[1])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the LED off."""
        _LOGGER.info("Main router LED switch: turning OFF")
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.set_main_router_led, False
        )
        _LOGGER.info("Main router LED OFF result: %s", result)
        if result[0] in (200, 302):
            self._is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off LED for main router: %s", result[1])

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            mesh_data = self.coordinator.data.get(MODULE_MESH, {})
            led_status = mesh_data.get("main_router_led_status")
            if led_status is not None:
                self._is_on = led_status == "on"
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        # Try to get initial LED state from mesh data
        if self.coordinator.data:
            mesh_data = self.coordinator.data.get(MODULE_MESH, {})
            led_status = mesh_data.get("main_router_led_status")
            if led_status is not None:
                self._is_on = led_status == "on"


class CudyMeshLEDSwitch(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SwitchEntity
):
    """Switch to control mesh device LEDs."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:led-on"

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str | None,
        mesh_mac: str,
        mesh_device: dict[str, Any],
    ) -> None:
        """Initialize the mesh LED switch."""
        super().__init__(coordinator)
        self._mesh_mac = mesh_mac
        self._mesh_name = mesh_display_name(mesh_device.get("name"), mesh_mac)
        self._attr_name = "LED"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}-led"
        )
        self._attr_device_info = build_mesh_device_info(
            coordinator,
            mesh_mac,
            mesh_device,
        )
        self._is_on: bool = True  # Default to on

    @property
    def is_on(self) -> bool:
        """Return true if LED is on."""
        return self._is_on

    @property
    def icon(self) -> str:
        """Return the icon based on LED state."""
        return "mdi:led-on" if self._is_on else "mdi:led-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the LED on."""
        _LOGGER.info("Mesh LED switch for %s: turning ON", self._mesh_name)
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.set_mesh_led, self._mesh_mac, True
        )
        _LOGGER.info("Mesh LED ON result for %s: %s", self._mesh_name, result)
        if result[0] in (200, 302):
            self._is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on LED for %s: %s", self._mesh_name, result[1])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the LED off."""
        _LOGGER.info("Mesh LED switch for %s: turning OFF", self._mesh_name)
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.set_mesh_led, self._mesh_mac, False
        )
        _LOGGER.info("Mesh LED OFF result for %s: %s", self._mesh_name, result)
        if result[0] in (200, 302):
            self._is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off LED for %s: %s", self._mesh_name, result[1])

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            mesh_data = self.coordinator.data.get(MODULE_MESH, {})
            mesh_devices = mesh_data.get("mesh_devices", {})
            device_data = mesh_devices.get(self._mesh_mac, {})
            led_status = device_data.get("led_status")
            if led_status is not None:
                self._is_on = led_status == "on"
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        # Try to get initial LED state from coordinator data
        if self.coordinator.data:
            mesh_data = self.coordinator.data.get(MODULE_MESH, {})
            mesh_devices = mesh_data.get("mesh_devices", {})
            device_data = mesh_devices.get(self._mesh_mac, {})
            led_status = device_data.get("led_status")
            if led_status is not None:
                self._is_on = led_status == "on"
