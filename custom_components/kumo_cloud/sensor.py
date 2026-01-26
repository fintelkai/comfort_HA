"""Platform for Kumo Cloud sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature  # Optimization 18: Removed unused ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import KumoCloudDataUpdateCoordinator, KumoCloudDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kumo Cloud sensor devices."""
    coordinator: KumoCloudDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for zone in coordinator.zones:
        if "adapter" in zone and zone["adapter"]:
            device_serial = zone["adapter"]["deviceSerial"]
            zone_id = zone["id"]

            device = KumoCloudDevice(coordinator, zone_id, device_serial)
            entities.append(KumoCloudTemperatureSensor(device))
            entities.append(KumoCloudHumiditySensor(device))

    async_add_entities(entities)


class KumoCloudTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Kumo Cloud temperature sensor."""

    _attr_has_entity_name = True
    _attr_name = "Temperature"

    def __init__(self, device: KumoCloudDevice) -> None:
        """Initialize the temperature sensor."""
        super().__init__(device.coordinator)
        self.device = device
        self._attr_unique_id = f"{device.device_serial}_temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = "temperature"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the current temperature."""
        adapter = self.device.zone_data.get("adapter", {})
        return adapter.get("roomTemp")

    @property
    def available(self) -> bool:
        """Return True if entity is available (Optimization 11)."""
        return self.device.available and self.coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information (Optimization 12: delegated to device)."""
        return self.device.device_info


class KumoCloudHumiditySensor(CoordinatorEntity, SensorEntity):
    """Representation of a Kumo Cloud humidity sensor."""

    _attr_has_entity_name = True
    _attr_name = "Humidity"

    def __init__(self, device: KumoCloudDevice) -> None:
        """Initialize the humidity sensor."""
        super().__init__(device.coordinator)
        self.device = device
        self._attr_unique_id = f"{device.device_serial}_humidity"
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_class = "humidity"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the current humidity."""
        adapter = self.device.zone_data.get("adapter", {})
        device_data = self.device.device_data
        return device_data.get("humidity", adapter.get("humidity"))

    @property
    def available(self) -> bool:
        """Return True if entity is available (Optimization 11)."""
        return self.device.available and self.coordinator.last_update_success

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information (Optimization 12: delegated to device)."""
        return self.device.device_info
