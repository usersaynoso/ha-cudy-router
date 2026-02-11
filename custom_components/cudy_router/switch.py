"""Support for Cudy Router Switch Platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
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
    # Use mesh main_router_name, or default to "Cudy Router"
    mesh_data = coordinator.data.get(MODULE_MESH, {}) if coordinator.data else {}
    main_router_mesh_name = mesh_data.get("main_router_name")
    router_name = main_router_mesh_name or "Cudy Router"
    
    entities: list[SwitchEntity] = []

    # Add main router LED switch
    entities.append(
        CudyMainRouterLEDSwitch(
            coordinator,
            router_name,
        )
    )

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


class CudyMainRouterLEDSwitch(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SwitchEntity
):
    """Switch to control main router LEDs."""

    _attr_has_entity_name = True
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
        # Link to the main router device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer="Cudy",
            name=router_name,
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
