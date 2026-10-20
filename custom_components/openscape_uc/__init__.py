"""The OpenScape UC integration."""

from __future__ import annotations

from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .api import OpenScapeUCAuthError, OpenScapeUCClient, OpenScapeUCError
from .const import (
    CONF_TRUST_INTERNAL_CERTS,
    DEFAULT_TRUST_INTERNAL_CERTS,
    DOMAIN,
    STORAGE_VERSION,
)
from .coordinator import OpenScapeUCCoordinator

PLATFORMS: list[Platform] = [Platform.SELECT, Platform.SENSOR]

type OpenScapeUCConfigEntry = ConfigEntry[OpenScapeUCCoordinator]


def create_session(hass: HomeAssistant, trust_internal_certs: bool) -> aiohttp.ClientSession:
    """Create a dedicated aiohttp session with its own cookie jar.

    A dedicated session is required so the login cookies are not shared with
    the rest of Home Assistant. unsafe=True allows cookies from IP-address hosts.
    """
    return async_create_clientsession(
        hass,
        verify_ssl=not trust_internal_certs,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )


async def async_setup_entry(hass: HomeAssistant, entry: OpenScapeUCConfigEntry) -> bool:
    """Set up OpenScape UC from a config entry."""
    session = create_session(
        hass,
        entry.data.get(CONF_TRUST_INTERNAL_CERTS, DEFAULT_TRUST_INTERNAL_CERTS),
    )
    entry.async_on_unload(session.close)

    store = _session_store(hass, entry)

    async def _save_session() -> None:
        await store.async_save({"cookies": client.export_session()})

    client = OpenScapeUCClient(
        session,
        entry.data[CONF_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        on_login=_save_session,
    )

    if stored := await store.async_load():
        client.restore_session(stored["cookies"])
    # Unload callbacks run in reverse order, so this saves any cookies the
    # server refreshed since the last login before the session is closed.
    entry.async_on_unload(_save_session)

    try:
        await client.async_ensure_session()
    except OpenScapeUCAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except OpenScapeUCError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = OpenScapeUCCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenScapeUCConfigEntry) -> bool:
    """Unload a config entry.

    The server session is kept alive so it can be reused after a restart.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: OpenScapeUCConfigEntry) -> None:
    """Delete the stored session when the config entry is removed."""
    await _session_store(hass, entry).async_remove()


def _session_store(hass: HomeAssistant, entry: ConfigEntry) -> Store[dict[str, Any]]:
    """Return the store holding the session cookies of a config entry."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
