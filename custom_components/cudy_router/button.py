"""Support for Cudy Router Button Platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODULE_MESH
from .coordinator import CudyRouterDataUpdateCoordinator
from .device_info import (
    async_cleanup_stale_mesh_entities,
    build_mesh_device_info,
    build_router_device_info,
    mesh_display_name,
    router_display_name,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Cudy Router buttons."""
    coordinator: CudyRouterDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    router_name = router_display_name(config_entry, coordinator.data)
    
    entities: list[ButtonEntity] = []

    # Add main router reboot button
    entities.append(
        CudyRouterRebootButton(
            coordinator,
            router_name,
        )
    )

    # Add mesh device reboot buttons
    if coordinator.data:
        mesh_data = coordinator.data.get(MODULE_MESH, {})
        mesh_devices = mesh_data.get("mesh_devices", {})
        async_cleanup_stale_mesh_entities(
            hass,
            config_entry,
            "button",
            set(mesh_devices),
        )
        
        for mesh_mac, mesh_device in mesh_devices.items():
            entities.append(
                CudyMeshRebootButton(
                    coordinator,
                    router_name,
                    mesh_mac,
                    mesh_device,
                )
            )

    async_add_entities(entities)


class CudyRouterRebootButton(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], ButtonEntity
):
    """Button to reboot the main Cudy router."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"
    _attr_name = "Reboot"

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str | None,
    ) -> None:
        """Initialize the reboot button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-reboot"
        self._attr_device_info = build_router_device_info(coordinator)

    async def async_press(self) -> None:
        """Handle the button press - reboot the router."""
        _LOGGER.info("Rebooting main Cudy router")
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.reboot_router
        )
        if result[0] not in (200, 302):
            _LOGGER.error("Failed to reboot router: %s", result[1])


class CudyMeshRebootButton(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], ButtonEntity
):
    """Button to reboot a mesh device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restart"

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str | None,
        mesh_mac: str,
        mesh_device: dict[str, Any],
    ) -> None:
        """Initialize the mesh reboot button."""
        super().__init__(coordinator)
        self._mesh_mac = mesh_mac
        self._mesh_name = mesh_display_name(mesh_device.get("name"), mesh_mac)
        self._attr_name = "Reboot"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}-reboot"
        )
        self._attr_device_info = build_mesh_device_info(
            coordinator,
            mesh_mac,
            mesh_device,
        )

    async def async_press(self) -> None:
        """Handle the button press - reboot the mesh device."""
        _LOGGER.info("Rebooting mesh device: %s (%s)", self._mesh_name, self._mesh_mac)
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.reboot_mesh_device, self._mesh_mac
        )
        if result[0] not in (200, 302):
            _LOGGER.error(
                "Failed to reboot mesh device %s: %s", self._mesh_name, result[1]
            )
