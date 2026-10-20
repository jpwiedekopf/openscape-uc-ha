"""Sensor platform for the OpenScape UC integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OpenScapeUCConfigEntry
from .coordinator import OpenScapeUCCoordinator
from .entity import OpenScapeUCEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenScapeUCConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor entities."""
    async_add_entities([OpenScapeUCOutboundDeviceSensor(entry.runtime_data)])


class OpenScapeUCOutboundDeviceSensor(OpenScapeUCEntity, SensorEntity):
    """Read-only sensor for the preferred outbound device."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: OpenScapeUCCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "outbound_device")

    @property
    def options(self) -> list[str]:
        """Return the names of all known devices."""
        names = [device.name for device in self.coordinator.data.devices]
        # The enum sensor rejects values outside its options, so make sure the
        # current device is included even if it is missing from deviceList.
        if (device := self.coordinator.data.outbound_device) and device.name not in names:
            names.append(device.name)
        return names

    @property
    def native_value(self) -> str | None:
        """Return the name of the preferred outbound device."""
        if (device := self.coordinator.data.outbound_device) is None:
            return None
        return device.name
