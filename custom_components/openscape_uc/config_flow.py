"""Config flow for the OpenScape UC integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from yarl import URL

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_session
from .api import (
    OpenScapeUCAuthError,
    OpenScapeUCClient,
    OpenScapeUCConnectionError,
    OpenScapeUCError,
)
from .const import (
    CONF_TRUST_INTERNAL_CERTS,
    DEFAULT_TRUST_INTERNAL_CERTS,
    DOMAIN,
    LOGGER,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(
            CONF_TRUST_INTERNAL_CERTS, default=DEFAULT_TRUST_INTERNAL_CERTS
        ): bool,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class OpenScapeUCConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenScape UC."""

    VERSION = 1

    async def _async_validate_input(self, data: dict[str, Any]) -> dict[str, str]:
        """Try to log in with the given data and return any errors."""
        errors: dict[str, str] = {}
        url = URL(data[CONF_URL])
        if url.scheme not in ("http", "https") or not url.host:
            return {CONF_URL: "invalid_url"}

        session = create_session(self.hass, data[CONF_TRUST_INTERNAL_CERTS])
        client = OpenScapeUCClient(
            session, data[CONF_URL], data[CONF_USERNAME], data[CONF_PASSWORD]
        )
        try:
            await client.async_login()
            await client.async_logout()
        except OpenScapeUCAuthError:
            errors["base"] = "invalid_auth"
        except OpenScapeUCConnectionError:
            errors["base"] = "cannot_connect"
        except OpenScapeUCError:
            LOGGER.exception("Unexpected response from server")
            errors["base"] = "unknown"
        except Exception:
            LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        finally:
            await session.close()
        return errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = URL(user_input[CONF_URL])
            await self.async_set_unique_id(
                f"{url.host}_{user_input[CONF_USERNAME]}".lower()
            )
            self._abort_if_unique_id_configured()

            errors = await self._async_validate_input(user_input)
            if not errors:
                return self.async_create_entry(
                    title=f"{user_input[CONF_USERNAME]} @ {url.host}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication when the stored credentials stop working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            errors = await self._async_validate_input(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            description_placeholders={CONF_USERNAME: entry.data[CONF_USERNAME]},
            errors=errors,
        )
