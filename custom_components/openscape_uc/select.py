"""Select platform for the OpenScape UC integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OpenScapeUCConfigEntry
from .api import OpenScapeUCError, PhoneDevice
from .coordinator import OpenScapeUCCoordinator
from .entity import OpenScapeUCEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenScapeUCConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the select entities."""
    async_add_entities([OpenScapeUCPreferredDeviceSelect(entry.runtime_data)])


class OpenScapeUCPreferredDeviceSelect(OpenScapeUCEntity, SelectEntity):
    """Select entity for the preferred device.

    The server keeps separate in- and outbound preferences. This entity treats
    them as one setting and reflects the inbound device, since that decides
    which phone rings.
    """

    def __init__(self, coordinator: OpenScapeUCCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "preferred_device")

    @property
    def _devices(self) -> list[PhoneDevice]:
        """Return the devices that can be set as preferred device."""
        return [d for d in self.coordinator.data.devices if d.preferable]

    @property
    def options(self) -> list[str]:
        """Return the names of the available devices."""
        return [device.name for device in self._devices]

    @property
    def current_option(self) -> str | None:
        """Return the name of the preferred inbound device."""
        if (device := self.coordinator.data.inbound_device) is None:
            return None
        return device.name

    async def async_select_option(self, option: str) -> None:
        """Route calls to the chosen device."""
        device = next((d for d in self._devices if d.name == option), None)
        if device is None:
            raise HomeAssistantError(f"Unknown device: {option}")
        try:
            await self.coordinator.client.async_select_device(device.device_id)
        except OpenScapeUCError as err:
            raise HomeAssistantError(f"Failed to select {option}: {err}") from err
        await self.coordinator.async_request_refresh()
