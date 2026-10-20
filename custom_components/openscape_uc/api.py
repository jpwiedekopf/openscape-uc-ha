"""Client for the OpenScape UC web client API."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from http import HTTPStatus
from http.cookies import Morsel
from typing import Any

import aiohttp
from yarl import URL

from .const import LOGGER, REQUEST_TIMEOUT

LOGIN_PATH = "/owc-servlets/login"
CONFIG_PATH = "/owc-servlets/config"
USER_PATH = "/owc-servlets/user/"
SESSION_COOKIE = "OpenScapeUC"
LOGIN_COOKIES = frozenset({SESSION_COOKIE, "JSESSIONID"})

ONS_PLACEHOLDER = "$ONS"
ONS_DISPLAY_NAME = "Work phone"


class OpenScapeUCError(Exception):
    """Base error for the OpenScape UC client."""


class OpenScapeUCConnectionError(OpenScapeUCError):
    """Raised when the server cannot be reached."""


class OpenScapeUCAuthError(OpenScapeUCError):
    """Raised when authentication fails."""


@dataclass(frozen=True, slots=True)
class PhoneDevice:
    """A device that calls can be routed to."""

    device_id: str
    name: str
    address: str | None
    device_type: str | None
    preferable: bool

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PhoneDevice:
        """Create a device from an entry of prefDeviceSettings."""
        name = data.get("name") or data.get("address") or data["id"]
        return cls(
            device_id=data["id"],
            # The web UI shows the business phone placeholder as "Work phone".
            name=ONS_DISPLAY_NAME if name == ONS_PLACEHOLDER else name,
            address=data.get("address"),
            device_type=data.get("type"),
            preferable=bool(data.get("preferable", False)),
        )


@dataclass(slots=True)
class OpenScapeUCState:
    """Snapshot of the state polled from the server."""

    devices: list[PhoneDevice] = field(default_factory=list)
    inbound_device: PhoneDevice | None = None
    outbound_device: PhoneDevice | None = None

    @classmethod
    def from_user_json(cls, data: dict[str, Any]) -> OpenScapeUCState:
        """Create the state from the response of the user endpoint."""
        settings = data["prefDeviceSettings"]
        inbound = settings.get("inBoundPreferredDevice")
        outbound = settings.get("outBoundPreferredDevice")
        return cls(
            devices=[PhoneDevice.from_json(d) for d in settings.get("deviceList", [])],
            inbound_device=PhoneDevice.from_json(inbound) if inbound else None,
            outbound_device=PhoneDevice.from_json(outbound) if outbound else None,
        )


class OpenScapeUCClient:
    """Thin wrapper around the OpenScape UC web client endpoints.

    Session state is kept in the cookie jar of the passed aiohttp session and
    can be exported/restored so it survives restarts.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        username: str,
        password: str,
        on_login: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the client.

        on_login is awaited after every successful login, e.g. to persist the
        new session cookies.
        """
        self._session = session
        self._base_url = URL(endpoint)
        self._username = username
        self._password = password
        self._on_login = on_login
        self._session_lock = asyncio.Lock()

    @property
    def base_url(self) -> URL:
        """Return the base URL of the web client."""
        return self._base_url

    async def async_login(self) -> None:
        """Authenticate and store the session cookies in the cookie jar."""
        async with self._session_lock:
            await self._login()

    async def async_ensure_session(self) -> None:
        """Make sure the cookie jar holds a valid session, logging in if needed."""
        async with self._session_lock:
            # Iterating the jar drops expired cookies, so a missing session
            # cookie means we never logged in or the session has expired.
            if SESSION_COOKIE not in {cookie.key for cookie in self._session.cookie_jar}:
                LOGGER.debug("No unexpired session cookie, logging in")
                await self._login()
                return

            # Don't follow redirects: an invalid session may be redirected to
            # a login page that itself answers with 200.
            response = await self._send("GET", CONFIG_PATH, allow_redirects=False)
            response.release()
            if response.status != HTTPStatus.OK:
                LOGGER.debug(
                    "Session check returned HTTP %s, logging in", response.status
                )
                await self._login()

    async def async_get_state(self) -> OpenScapeUCState:
        """Fetch the available devices and the preferred in- and outbound ones."""
        response = await self._request("GET", USER_PATH)
        async with response:
            try:
                data = await response.json(content_type=None)
                return OpenScapeUCState.from_user_json(data)
            except (aiohttp.ClientError, ValueError, KeyError, TypeError) as err:
                raise OpenScapeUCError(
                    f"Unexpected response from {USER_PATH}: {err!r}"
                ) from err

    async def async_select_device(self, device_id: str) -> None:
        """Route calls to the given device."""
        # TODO: implement once the endpoint and payload are known.
        raise NotImplementedError

    async def async_logout(self) -> None:
        """End the server-side session, if supported."""
        # TODO: implement once the logout endpoint is known.
        self._session.cookie_jar.clear()

    def export_session(self) -> list[dict[str, Any]]:
        """Return the cookies in the jar in a JSON-serializable form."""
        now = datetime.now(UTC)
        cookies: list[dict[str, Any]] = []
        for morsel in self._session.cookie_jar:
            attributes = {key: value for key, value in morsel.items() if value}
            # max-age is relative to when the cookie was received, so store an
            # absolute expiry instead. Sessions are saved right after login,
            # which makes "now" a close enough approximation.
            if max_age := attributes.pop("max-age", None):
                expires = now + timedelta(seconds=int(max_age))
                attributes["expires"] = format_datetime(expires, usegmt=True)
            cookies.append(
                {
                    "name": morsel.key,
                    "value": morsel.value,
                    "coded_value": morsel.coded_value,
                    "attributes": attributes,
                }
            )
        return cookies

    def restore_session(self, cookies: list[dict[str, Any]]) -> None:
        """Load cookies previously returned by export_session into the jar.

        Expired cookies are discarded by the jar.
        """
        for cookie in cookies:
            morsel: Morsel[str] = Morsel()
            morsel.set(cookie["name"], cookie["value"], cookie["coded_value"])
            morsel.update(cookie["attributes"])
            self._session.cookie_jar.update_cookies(
                {cookie["name"]: morsel}, self._base_url
            )

    async def _login(self) -> None:
        """Log in. Callers must hold the session lock."""
        # Drop stale session cookies so the server issues a fresh session.
        self._session.cookie_jar.clear()
        response = await self._send(
            "POST",
            LOGIN_PATH,
            # The web client sends the password Base64-encoded.
            json={
                "userId": self._username,
                "password": base64.b64encode(self._password.encode()).decode(),
            },
        )
        async with response:
            if response.status == HTTPStatus.UNAUTHORIZED:
                raise OpenScapeUCAuthError(
                    f"Login rejected: {await self._error_ids(response)}"
                )
            if response.status != HTTPStatus.OK:
                raise OpenScapeUCError(
                    f"Unexpected login response: HTTP {response.status}"
                )

        cookie_names = {cookie.key for cookie in self._session.cookie_jar}
        if missing := LOGIN_COOKIES - cookie_names:
            raise OpenScapeUCError(
                f"Login succeeded but cookies are missing: {', '.join(sorted(missing))}"
            )
        LOGGER.debug("Logged in to %s as %s", self._base_url, self._username)

        if self._on_login is not None:
            await self._on_login()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        retry_auth: bool = True,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Send an authenticated request relative to the base URL.

        The session is validated first; a 401 forces one fresh login and retry.
        """
        await self.async_ensure_session()
        response = await self._send(method, path, **kwargs)

        if response.status == HTTPStatus.UNAUTHORIZED:
            response.release()
            if not retry_auth:
                raise OpenScapeUCAuthError("Not authorized")
            LOGGER.debug("Request was rejected, logging in again")
            await self.async_login()
            return await self._request(method, path, retry_auth=False, **kwargs)

        if response.status >= HTTPStatus.BAD_REQUEST:
            response.release()
            raise OpenScapeUCError(
                f"Unexpected response from {response.url}: HTTP {response.status}"
            )

        return response

    async def _send(
        self, method: str, path: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Send a single request, mapping transport errors to connection errors."""
        url = self._base_url.join(URL(path))
        try:
            return await self._session.request(
                method,
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                **kwargs,
            )
        except (TimeoutError, aiohttp.ClientError) as err:
            raise OpenScapeUCConnectionError(
                f"Error communicating with {url}: {err}"
            ) from err

    @staticmethod
    async def _error_ids(response: aiohttp.ClientResponse) -> str:
        """Extract the error IDs from an error response body.

        Error bodies look like {"errorCodes": [{"id": "_error.Some-Error_"}]}.
        """
        try:
            body = await response.json(content_type=None)
            ids = [code["id"] for code in body["errorCodes"]]
        except (aiohttp.ClientError, ValueError, KeyError, TypeError):
            return "unknown error"
        return ", ".join(ids) or "unknown error"
