"""Support for Cudy Router Button Platform."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODULE_MESH
from .coordinator import CudyRouterDataUpdateCoordinator

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
    router_name = config_entry.data.get(CONF_NAME) or config_entry.data.get(CONF_HOST)
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
        
        for mesh_mac, mesh_device in mesh_devices.items():
            mesh_name = mesh_device.get("name") or mesh_mac
            
            entities.append(
                CudyMeshRebootButton(
                    coordinator,
                    router_name,
                    mesh_mac,
                    mesh_name,
                )
            )

    async_add_entities(entities)


class CudyRouterRebootButton(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], ButtonEntity
):
    """Button to reboot the main Cudy router."""

    _attr_has_entity_name = True
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer="Cudy",
            name=router_name,
        )

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
    _attr_icon = "mdi:restart"

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str | None,
        mesh_mac: str,
        mesh_name: str,
    ) -> None:
        """Initialize the mesh reboot button."""
        super().__init__(coordinator)
        self._mesh_mac = mesh_mac
        self._mesh_name = mesh_name
        self._attr_name = f"{mesh_name} Reboot"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}-reboot"
        )
        # Link to the mesh device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}")},
            manufacturer="Cudy",
            name=f"Mesh {mesh_name}",
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
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
