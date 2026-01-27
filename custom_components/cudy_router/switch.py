"""Support for Cudy Router Switch Platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODULE_MESH
from .coordinator import CudyRouterDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class CudyMeshSwitchEntityDescription(SwitchEntityDescription):
    """Describe Cudy Router mesh switch entity."""

    pass


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Cudy Router switches."""
    coordinator: CudyRouterDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    # Use configured name, or mesh main_router_name, or default to "Cudy Router"
    configured_name = config_entry.data.get(CONF_NAME)
    mesh_data = coordinator.data.get(MODULE_MESH, {}) if coordinator.data else {}
    main_router_mesh_name = mesh_data.get("main_router_name")
    router_name = configured_name or main_router_mesh_name or "Cudy Router"
    
    entities: list[SwitchEntity] = []

    # Add mesh device switches
    if coordinator.data:
        mesh_data = coordinator.data.get(MODULE_MESH, {})
        mesh_devices = mesh_data.get("mesh_devices", {})
        
        for mesh_mac, mesh_device in mesh_devices.items():
            mesh_name = mesh_device.get("name") or mesh_mac
            
            # Add LED switch for each mesh device
            entities.append(
                CudyMeshLEDSwitch(
                    coordinator,
                    router_name,
                    mesh_mac,
                    mesh_name,
                )
            )

    async_add_entities(entities)


class CudyMeshLEDSwitch(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SwitchEntity
):
    """Switch to control mesh device LEDs."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:led-on"

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str | None,
        mesh_mac: str,
        mesh_name: str,
    ) -> None:
        """Initialize the mesh LED switch."""
        super().__init__(coordinator)
        self._mesh_mac = mesh_mac
        self._mesh_name = mesh_name
        self._attr_name = f"{mesh_name} LED"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}-led"
        )
        # Link to the mesh device
        # Use just the mesh device name, not "Mesh <name>"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}")},
            manufacturer="Cudy",
            name=mesh_name,
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
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
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.set_mesh_led, self._mesh_mac, True
        )
        if result[0] in (200, 302):
            self._is_on = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on LED for %s: %s", self._mesh_name, result[1])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the LED off."""
        result = await self.hass.async_add_executor_job(
            self.coordinator.api.set_mesh_led, self._mesh_mac, False
        )
        if result[0] in (200, 302):
            self._is_on = False
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off LED for %s: %s", self._mesh_name, result[1])

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        # Try to get initial LED state
        state = await self.hass.async_add_executor_job(
            self.coordinator.api.get_mesh_led_state, self._mesh_mac
        )
        if state is not None:
            self._is_on = state
