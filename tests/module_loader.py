"""Helpers for loading integration modules without importing package __init__."""

from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components" / "cudy_router"


def _ensure_package_stub(name: str, path: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module


def _ensure_homeassistant_stub() -> None:
    homeassistant = sys.modules.get("homeassistant")
    if homeassistant is None:
        homeassistant = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = homeassistant

    const_module = sys.modules.get("homeassistant.const")
    if const_module is None:
        const_module = types.ModuleType("homeassistant.const")
        const_module.CONF_HOST = "host"
        const_module.CONF_MODEL = "model"
        const_module.CONF_PASSWORD = "password"
        const_module.CONF_SCAN_INTERVAL = "scan_interval"
        const_module.CONF_USERNAME = "username"
        const_module.SIGNAL_STRENGTH_DECIBELS = "dB"
        const_module.SIGNAL_STRENGTH_DECIBELS_MILLIWATT = "dBm"
        const_module.STATE_UNAVAILABLE = "unavailable"

        class UnitOfDataRate:
            MEGABITS_PER_SECOND = "Mbit/s"

        class UnitOfInformation:
            BYTES = "B"
            MEGABYTES = "MB"

        class UnitOfTime:
            SECONDS = "s"

        const_module.UnitOfDataRate = UnitOfDataRate
        const_module.UnitOfInformation = UnitOfInformation
        const_module.UnitOfTime = UnitOfTime
        sys.modules["homeassistant.const"] = const_module

    components_module = sys.modules.get("homeassistant.components")
    if components_module is None:
        components_module = types.ModuleType("homeassistant.components")
        sys.modules["homeassistant.components"] = components_module

    sensor_module = sys.modules.get("homeassistant.components.sensor")
    if sensor_module is None:
        sensor_module = types.ModuleType("homeassistant.components.sensor")

        @dataclass(frozen=True, kw_only=True)
        class SensorEntityDescription:
            key: str
            device_class: object | None = None
            entity_category: object | None = None
            icon: str | None = None
            native_unit_of_measurement: str | None = None
            options: list[str] | None = None
            state_class: object | None = None

        class SensorDeviceClass:
            DATA_RATE = "data_rate"
            DATA_SIZE = "data_size"
            DURATION = "duration"
            ENUM = "enum"
            SIGNAL_STRENGTH = "signal_strength"

        class SensorEntity:
            @property
            def unique_id(self):
                return getattr(self, "_attr_unique_id", None)

        class SensorStateClass:
            MEASUREMENT = "measurement"
            TOTAL_INCREASING = "total_increasing"

        sensor_module.SensorDeviceClass = SensorDeviceClass
        sensor_module.SensorEntity = SensorEntity
        sensor_module.SensorEntityDescription = SensorEntityDescription
        sensor_module.SensorStateClass = SensorStateClass
        sys.modules["homeassistant.components.sensor"] = sensor_module

    config_entries_module = sys.modules.get("homeassistant.config_entries")
    if config_entries_module is None:
        config_entries_module = types.ModuleType("homeassistant.config_entries")

        class ConfigEntry:
            @classmethod
            def __class_getitem__(cls, item):
                return cls

        config_entries_module.ConfigEntry = ConfigEntry
        sys.modules["homeassistant.config_entries"] = config_entries_module

    core_module = sys.modules.get("homeassistant.core")
    if core_module is None:
        core_module = types.ModuleType("homeassistant.core")

        class HomeAssistant:  # noqa: D401
            """Minimal HomeAssistant stub for pure helper imports."""

        def callback(func):
            return func

        core_module.HomeAssistant = HomeAssistant
        core_module.callback = callback
        sys.modules["homeassistant.core"] = core_module

    helpers_module = sys.modules.get("homeassistant.helpers")
    if helpers_module is None:
        helpers_module = types.ModuleType("homeassistant.helpers")
        sys.modules["homeassistant.helpers"] = helpers_module

    entity_module = sys.modules.get("homeassistant.helpers.entity")
    if entity_module is None:
        entity_module = types.ModuleType("homeassistant.helpers.entity")

        class EntityCategory:
            DIAGNOSTIC = "diagnostic"

        entity_module.EntityCategory = EntityCategory
        sys.modules["homeassistant.helpers.entity"] = entity_module

    entity_platform_module = sys.modules.get("homeassistant.helpers.entity_platform")
    if entity_platform_module is None:
        entity_platform_module = types.ModuleType("homeassistant.helpers.entity_platform")
        entity_platform_module.AddEntitiesCallback = object
        sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_module

    typing_module = sys.modules.get("homeassistant.helpers.typing")
    if typing_module is None:
        typing_module = types.ModuleType("homeassistant.helpers.typing")
        typing_module.StateType = object
        sys.modules["homeassistant.helpers.typing"] = typing_module

    update_coordinator_module = sys.modules.get("homeassistant.helpers.update_coordinator")
    if update_coordinator_module is None:
        update_coordinator_module = types.ModuleType("homeassistant.helpers.update_coordinator")

        class CoordinatorEntity:
            def __init__(self, coordinator) -> None:
                self.coordinator = coordinator

            @classmethod
            def __class_getitem__(cls, item):
                return cls

        class DataUpdateCoordinator:
            def __init__(self, hass, logger, *, name, update_interval) -> None:
                self.hass = hass
                self.logger = logger
                self.name = name
                self.update_interval = update_interval

            @classmethod
            def __class_getitem__(cls, item):
                return cls

        class UpdateFailed(Exception):
            """Minimal UpdateFailed stub."""

        update_coordinator_module.CoordinatorEntity = CoordinatorEntity
        update_coordinator_module.DataUpdateCoordinator = DataUpdateCoordinator
        update_coordinator_module.UpdateFailed = UpdateFailed
        sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_module

    device_registry_module = sys.modules.get("homeassistant.helpers.device_registry")
    if device_registry_module is None:
        device_registry_module = types.ModuleType("homeassistant.helpers.device_registry")

        class DeviceInfo(dict):
            """Minimal DeviceInfo stub that preserves kwargs for assertions."""

            def __init__(self, **kwargs):
                super().__init__(**kwargs)

        class _DeviceRegistry:
            def __init__(self) -> None:
                self.devices = {}

            def async_remove_device(self, device_id: str) -> None:
                self.devices.pop(device_id, None)

        device_registry_module.CONNECTION_NETWORK_MAC = "mac"
        device_registry_module.DeviceInfo = DeviceInfo
        device_registry_module._registry = _DeviceRegistry()
        device_registry_module.async_get = lambda hass: device_registry_module._registry
        sys.modules["homeassistant.helpers.device_registry"] = device_registry_module

    entity_registry_module = sys.modules.get("homeassistant.helpers.entity_registry")
    if entity_registry_module is None:
        entity_registry_module = types.ModuleType("homeassistant.helpers.entity_registry")

        class _Registry:
            def __init__(self) -> None:
                self.entities = {}

            def async_remove(self, entity_id: str) -> None:
                self.entities.pop(entity_id, None)

        entity_registry_module._registry = _Registry()
        entity_registry_module.async_get = lambda hass: entity_registry_module._registry
        sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_module


def load_cudy_module(module_name: str):
    """Load a custom_components.cudy_router module directly from disk."""
    _ensure_package_stub("custom_components", ROOT / "custom_components")
    _ensure_package_stub("custom_components.cudy_router", PACKAGE_ROOT)
    _ensure_homeassistant_stub()

    qualified_name = f"custom_components.cudy_router.{module_name}"
    module_path = PACKAGE_ROOT / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(qualified_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module
