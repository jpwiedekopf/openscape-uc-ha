"""Data update coordinator for the OpenScape UC integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OpenScapeUCAuthError,
    OpenScapeUCClient,
    OpenScapeUCError,
    OpenScapeUCState,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER

if TYPE_CHECKING:
    from . import OpenScapeUCConfigEntry


class OpenScapeUCCoordinator(DataUpdateCoordinator[OpenScapeUCState]):
    """Poll the OpenScape UC server for the current device selection."""

    config_entry: OpenScapeUCConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OpenScapeUCConfigEntry,
        client: OpenScapeUCClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> OpenScapeUCState:
        """Fetch the latest state from the server."""
        try:
            return await self.client.async_get_state()
        except OpenScapeUCAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OpenScapeUCError as err:
            raise UpdateFailed(str(err)) from err
