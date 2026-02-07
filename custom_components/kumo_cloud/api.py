"""API client for Kumo Cloud."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from aiohttp import ClientResponseError, ClientTimeout

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    API_BASE_URL,
    API_VERSION,
    API_APP_VERSION,
    TOKEN_REFRESH_INTERVAL,
    TOKEN_EXPIRY_MARGIN,
)
# Optimization 7: Import type definitions for better type safety
from .types import (
    LoginResponse,
    Site,
    Zone,
    DeviceDetail,
    DeviceProfile,
)

_LOGGER = logging.getLogger(__name__)


# Optimization 8: Rate limiting as async context manager
class RateLimiter:
    """Async context manager for rate limiting API requests."""

    def __init__(self, min_interval: timedelta, lock: asyncio.Lock) -> None:
        """Initialize rate limiter.

        Args:
            min_interval: Minimum time between requests
            lock: Shared lock for synchronization
        """
        self.min_interval = min_interval
        self.lock = lock
        self.last_request_time: datetime | None = None

    async def __aenter__(self) -> RateLimiter:
        """Enter the context manager and enforce rate limiting."""
        await self.lock.acquire()

        if self.last_request_time is not None:
            time_since_last = datetime.now() - self.last_request_time
            if time_since_last < self.min_interval:
                wait_time = (self.min_interval - time_since_last).total_seconds()
                if wait_time > 0:
                    _LOGGER.debug(
                        "Rate limiting: waiting %.1f seconds before next request",
                        wait_time,
                    )
                    try:
                        await asyncio.sleep(wait_time)
                    except asyncio.CancelledError:
                        self.lock.release()
                        raise

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and update timestamp."""
        if exc_type is None:
            # Only update timestamp on successful request
            self.last_request_time = datetime.now()
        self.lock.release()


class KumoCloudError(HomeAssistantError):
    """Base exception for Kumo Cloud."""


class KumoCloudAuthError(KumoCloudError):
    """Authentication error."""


class KumoCloudConnectionError(KumoCloudError):
    """Connection error."""


class KumoCloudAPI:
    """Kumo Cloud API client."""

    def __init__(self, hass: HomeAssistant, config_entry=None) -> None:
        """Initialize the API client.

        Args:
            hass: Home Assistant instance
            config_entry: Optional config entry for token persistence (Optimization 6)
        """
        self.hass = hass
        self.session = async_get_clientsession(hass)
        self.base_url = API_BASE_URL
        self.username: str | None = None
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.token_expires_at: datetime | None = None
        self._config_entry = config_entry  # Optimization 6: Store for token updates
        # Optimization 8: Use rate limiter context manager
        self._request_lock = asyncio.Lock()
        self._rate_limiter = RateLimiter(
            min_interval=timedelta(seconds=2),
            lock=self._request_lock,
        )

    async def login(self, username: str, password: str) -> LoginResponse:
        """Login to Kumo Cloud and return user data."""
        url = f"{self.base_url}/{API_VERSION}/login"
        headers = {
            "x-app-version": API_APP_VERSION,
            "Content-Type": "application/json",
        }
        data = {
            "username": username,
            "password": password,
            "appVersion": API_APP_VERSION,
        }

        try:
            async with asyncio.timeout(30):
                async with self.session.post(
                    url, headers=headers, json=data
                ) as response:
                    if response.status == 403:
                        raise KumoCloudAuthError("Invalid username or password")
                    response.raise_for_status()
                    result = await response.json()

                    self.username = username
                    self.access_token = result["token"]["access"]
                    self.refresh_token = result["token"]["refresh"]
                    self.token_expires_at = datetime.now() + timedelta(
                        seconds=TOKEN_REFRESH_INTERVAL
                    )

                    return result

        except asyncio.TimeoutError as err:
            raise KumoCloudConnectionError("Connection timeout") from err
        except ClientResponseError as err:
            if err.status == 403:
                raise KumoCloudAuthError("Invalid credentials") from err
            raise KumoCloudConnectionError(f"HTTP error: {err.status}") from err
        except Exception as err:
            raise KumoCloudConnectionError(f"Unexpected error: {err}") from err

    async def refresh_access_token(self) -> None:
        """Refresh the access token."""
        if not self.refresh_token:
            raise KumoCloudAuthError("No refresh token available")

        url = f"{self.base_url}/{API_VERSION}/refresh"
        headers = {
            "x-app-version": API_APP_VERSION,
            "Content-Type": "application/json",
        }
        data = {"refresh": self.refresh_token}

        try:
            async with asyncio.timeout(30):
                async with self.session.post(
                    url, headers=headers, json=data
                ) as response:
                    if response.status == 401:
                        raise KumoCloudAuthError("Refresh token expired")
                    response.raise_for_status()
                    result = await response.json()

                    self.access_token = result["access"]
                    self.refresh_token = result["refresh"]
                    self.token_expires_at = datetime.now() + timedelta(
                        seconds=TOKEN_REFRESH_INTERVAL
                    )

                    # Optimization 6: Persist refreshed tokens to config entry
                    if self._config_entry:
                        self.hass.config_entries.async_update_entry(
                            self._config_entry,
                            data={
                                **self._config_entry.data,
                                "access_token": self.access_token,
                                "refresh_token": self.refresh_token,
                            },
                        )
                        _LOGGER.debug("Persisted refreshed tokens to config entry")

        except asyncio.TimeoutError as err:
            raise KumoCloudConnectionError("Connection timeout during refresh") from err
        except ClientResponseError as err:
            if err.status == 401:
                raise KumoCloudAuthError("Refresh token expired") from err
            raise KumoCloudConnectionError(
                f"HTTP error during refresh: {err.status}"
            ) from err

    async def _ensure_token_valid(self) -> None:
        """Ensure access token is valid, refresh if needed."""
        if not self.access_token:
            raise KumoCloudAuthError("No access token available")

        if (
            self.token_expires_at
            and datetime.now() + timedelta(seconds=TOKEN_EXPIRY_MARGIN)
            >= self.token_expires_at
        ):
            await self.refresh_access_token()

    async def _request(
        self, method: str, endpoint: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated request to the API with rate limiting."""
        # Optimization 8: Use rate limiter context manager
        async with self._rate_limiter:
            await self._ensure_token_valid()

            url = f"{self.base_url}/{API_VERSION}{endpoint}"
            headers = {
                "x-app-version": API_APP_VERSION,
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            max_retries = 3
            retry_delay = 60  # Start with 60 seconds for 429 errors

            for attempt in range(max_retries):
                got_429 = False
                try:
                    # Use a longer timeout to account for network delays (30 seconds)
                    # Note: 429 retry sleeps happen outside this timeout context
                    async with asyncio.timeout(30):
                        if method.upper() == "GET":
                            async with self.session.get(url, headers=headers) as response:
                                if response.status == 429:
                                    got_429 = True
                                    # Will handle sleep outside timeout context
                                else:
                                    response.raise_for_status()
                                    result = await response.json()
                                    return result
                        elif method.upper() == "POST":
                            async with self.session.post(
                                url, headers=headers, json=data
                            ) as response:
                                if response.status == 429:
                                    got_429 = True
                                    # Will handle sleep outside timeout context
                                else:
                                    response.raise_for_status()
                                    result = (
                                        await response.json()
                                        if response.content_type == "application/json"
                                        else {}
                                    )
                                    return result

                    # Handle 429 outside timeout context to avoid timeout during sleep
                    if got_429:
                        if attempt < max_retries - 1:
                            _LOGGER.warning(
                                "Rate limited (429). Waiting %d seconds before retry %d/%d",
                                retry_delay,
                                attempt + 1,
                                max_retries,
                            )
                            try:
                                await asyncio.sleep(retry_delay)
                            except asyncio.CancelledError:
                                raise
                            retry_delay *= 2  # Exponential backoff
                            continue
                        else:
                            raise KumoCloudConnectionError(
                                "Rate limit exceeded. Please try again later."
                            )

                except asyncio.TimeoutError as err:
                    if attempt < max_retries - 1:
                        _LOGGER.warning(
                            "Request timeout. Retrying %d/%d", attempt + 1, max_retries
                        )
                        continue
                    raise KumoCloudConnectionError("Request timeout") from err
                except ClientResponseError as err:
                    if err.status == 401:
                        raise KumoCloudAuthError("Authentication failed") from err
                    if err.status == 429:
                        # This shouldn't happen as we handle it above, but just in case
                        if attempt < max_retries - 1:
                            _LOGGER.warning(
                                "Rate limited (429). Waiting %d seconds before retry %d/%d",
                                retry_delay,
                                attempt + 1,
                                max_retries,
                            )
                            try:
                                await asyncio.sleep(retry_delay)
                            except asyncio.CancelledError:
                                raise
                            retry_delay *= 2
                            continue
                        raise KumoCloudConnectionError(
                            "Rate limit exceeded. Please try again later."
                        ) from err
                    raise KumoCloudConnectionError(f"HTTP error: {err.status}") from err

    async def get_account_info(self) -> dict[str, Any]:
        """Get account information."""
        return await self._request("GET", "/accounts/me")

    async def get_sites(self) -> list[Site]:
        """Get list of sites."""
        return await self._request("GET", "/sites/")

    async def get_zones(self, site_id: str) -> list[Zone]:
        """Get list of zones for a site."""
        return await self._request("GET", f"/sites/{site_id}/zones")

    async def get_device_details(self, device_serial: str) -> DeviceDetail:
        """Get device details."""
        return await self._request("GET", f"/devices/{device_serial}")

    async def get_device_profile(self, device_serial: str) -> list[DeviceProfile]:
        """Get device profile information."""
        return await self._request("GET", f"/devices/{device_serial}/profile")

    async def send_command(
        self, device_serial: str, commands: dict[str, Any]
    ) -> dict[str, Any]:
        """Send command to device."""
        data = {"deviceSerial": device_serial, "commands": commands}
        return await self._request("POST", "/devices/send-command", data)
