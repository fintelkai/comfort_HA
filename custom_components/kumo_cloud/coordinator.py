from datetime import datetime, timedelta, timezone
from typing import Any
import asyncio
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import HomeAssistant

from .api import KumoCloudAPI, KumoCloudAuthError, KumoCloudConnectionError
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, COMMAND_SETTLE_TIME

_LOGGER = logging.getLogger(__name__)

class KumoCloudDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Kumo Cloud data."""

    def __init__(self, hass: HomeAssistant, api: KumoCloudAPI, site_id: str, scan_interval: int = DEFAULT_SCAN_INTERVAL) -> None:
        """Initialize the coordinator (Optimization 22: configurable scan_interval)."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.site_id = site_id
        self.zones: list[dict[str, Any]] = []
        self.devices: dict[str, dict[str, Any]] = {}
        self.device_profiles: dict[str, list[dict[str, Any]]] = {}
        # Optimization 10: Zone index for O(1) lookups instead of O(n) linear search
        self.zone_index: dict[str, dict[str, Any]] = {}

        # Instance variable to store cached commands
        # Optimization 3: Add max age to prevent memory leaks
        self.cached_commands: dict[tuple[str, str], tuple[str, Any]] = {}
        self._cache_max_age = timedelta(minutes=5)  # Clear commands older than 5 minutes

    def _process_pending_commands(self, device_serial: str, device_detail: dict[str, Any]) -> None:
        """Process cached commands and cull outdated commands for a device."""
        # Check if the device already exists and the updatedAt matches
        if device_serial in self.devices and "updatedAt" in device_detail:
            self.cull_cached_commands(device_serial, device_detail.get("updatedAt"))

        # Reapply cached commands to the device details
        for (cached_device_serial, command), (_, command_value) in self.cached_commands.items():
            if cached_device_serial == device_serial:
                device_detail[command] = command_value

    async def _async_update_data(self, _retry_attempted: bool = False) -> dict[str, Any]:
        """Fetch data from Kumo Cloud.

        Args:
            _retry_attempted: Internal flag to prevent infinite recursion on token refresh
        """
        try:
            # Get zones for the site
            zones = await self.api.get_zones(self.site_id)

            # Get device details for each zone
            devices = {}
            device_profiles = {}

            # Optimization 1: Fetch all zone data in parallel
            tasks = []
            device_serials = []

            for zone in zones:
                if "adapter" in zone and zone["adapter"]:
                    device_serial = zone["adapter"]["deviceSerial"]
                    device_serials.append(device_serial)

                    # Create tasks for parallel execution
                    tasks.append(self.api.get_device_details(device_serial))
                    tasks.append(self.api.get_device_profile(device_serial))

            # Execute all API calls in parallel
            if tasks:
                results = await asyncio.gather(*tasks)

                # Process results (alternating device_detail, device_profile)
                for i, device_serial in enumerate(device_serials):
                    device_detail = results[i * 2]
                    device_profile = results[i * 2 + 1]

                    # Process pending commands for the device
                    self._process_pending_commands(device_serial, device_detail)

                    devices[device_serial] = device_detail
                    device_profiles[device_serial] = device_profile

            # Store the data for access by entities
            self.zones = zones
            self.devices = devices
            self.device_profiles = device_profiles
            # Optimization 10: Build zone index for O(1) lookups
            self.zone_index = {zone["id"]: zone for zone in zones}

            return {
                "zones": zones,
                "devices": devices,
                "device_profiles": device_profiles,
            }

        except KumoCloudAuthError as err:
            # Optimization 9: Try to refresh token once, prevent infinite recursion
            if not _retry_attempted:
                try:
                    _LOGGER.debug("Authentication failed, attempting token refresh")
                    await self.api.refresh_access_token()
                    # Retry the request with flag set to prevent further retries
                    return await self._async_update_data(_retry_attempted=True)
                except KumoCloudAuthError as refresh_err:
                    raise UpdateFailed(
                        f"Authentication failed after token refresh: {refresh_err}"
                    ) from refresh_err
            else:
                # Already retried once, don't retry again to prevent infinite recursion
                raise UpdateFailed(
                    f"Authentication failed on retry: {err}"
                ) from err
        except KumoCloudConnectionError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

    async def async_refresh_device(self, device_serial: str) -> None:
        """Refresh a specific device's data immediately."""
        try:
            # Get fresh device details
            device_detail = await self.api.get_device_details(device_serial)

            # Process pending commands for the device
            self._process_pending_commands(device_serial, device_detail)

            # Update the cached device data
            self.devices[device_serial] = device_detail

            # Also update the zone data if it contains the same info
            for zone in self.zones:
                if "adapter" in zone and zone["adapter"]:
                    if zone["adapter"]["deviceSerial"] == device_serial:
                        # Update adapter data with fresh device data
                        zone["adapter"].update(
                            {
                                "roomTemp": device_detail.get("roomTemp"),
                                "operationMode": device_detail.get("operationMode"),
                                "power": device_detail.get("power"),
                                "fanSpeed": device_detail.get("fanSpeed"),
                                "airDirection": device_detail.get("airDirection"),
                                "spCool": device_detail.get("spCool"),
                                "spHeat": device_detail.get("spHeat"),
                                "humidity": device_detail.get("humidity"),
                            }
                        )
                        # Optimization 10: Update zone index as well
                        self.zone_index[zone["id"]] = zone
                        break

            # Update the coordinator's data dict
            self.data = {
                "zones": self.zones,
                "devices": self.devices,
                "device_profiles": self.device_profiles,
            }

            # Notify all listeners that data has been updated
            self.async_update_listeners()

            _LOGGER.debug("Refreshed device %s data", device_serial)

        except Exception as err:
            _LOGGER.warning("Failed to refresh device %s: %s", device_serial, err)

    def cache_command(self, device_serial: str, command: str, value: Any) -> None:
        """Cache a command with its value and timestamp."""
        current_time = datetime.now(timezone.utc).isoformat()
        self.cached_commands[(device_serial, command)] = (current_time, value)
        _LOGGER.debug("Cached command in device data: %s at %s", command, current_time)

        # Optimization 3: Periodically clean up stale cached commands
        self._cleanup_stale_cache()

    def cull_cached_commands(self, device_serial: str, date: str) -> None:
        """Remove cached commands for a device where the date is on or after the item's timestamp."""
        to_remove = []
        input_date = datetime.fromisoformat(date)

        for key, value in self.cached_commands.items():
            cached_device_serial, command = key
            cached_date, _ = value
            cached_date_obj = datetime.fromisoformat(cached_date)

            # Check if the device_serial matches and the input date is on or after the cached date
            if cached_device_serial == device_serial and input_date >= cached_date_obj:
                to_remove.append(key)

        # Remove the matching keys
        for key in to_remove:
            del self.cached_commands[key]

        # Optimization 5: Only log when commands are actually culled
        if to_remove:
            remaining_count = len(self.cached_commands)
            _LOGGER.debug(
                "Culled %d cached commands for device %s on or after %s. Remaining: %d",
                len(to_remove), device_serial, date, remaining_count
            )

    def _cleanup_stale_cache(self) -> None:
        """Remove cached commands older than max age to prevent memory leaks."""
        now = datetime.now(timezone.utc)
        to_remove = []

        for key, value in self.cached_commands.items():
            cached_date_str, _ = value
            cached_date = datetime.fromisoformat(cached_date_str)

            # Remove commands older than max age
            if now - cached_date > self._cache_max_age:
                to_remove.append(key)

        if to_remove:
            for key in to_remove:
                del self.cached_commands[key]
            _LOGGER.debug("Cleaned up %d stale cached commands (older than %s)", len(to_remove), self._cache_max_age)

class KumoCloudDevice:
    """Representation of a Kumo Cloud device."""

    def __init__(
        self,
        coordinator: KumoCloudDataUpdateCoordinator,
        zone_id: str,
        device_serial: str,
    ) -> None:
        """Initialize the device."""
        self.coordinator = coordinator
        self.zone_id = zone_id
        self.device_serial = device_serial
        # Optimization 13: Removed unused instance variables (_zone_data, _device_data, _profile_data)

    @property
    def zone_data(self) -> dict[str, Any]:
        """Get the zone data with O(1) lookup (Optimization 10)."""
        # Use zone index for constant-time lookup instead of O(n) linear search
        return self.coordinator.zone_index.get(self.zone_id, {})

    @property
    def device_data(self) -> dict[str, Any]:
        """Get the device data."""
        # Always get fresh data from coordinator
        return self.coordinator.devices.get(self.device_serial, {})

    @property
    def profile_data(self) -> list[dict[str, Any]]:
        """Get the device profile data."""
        # Always get fresh data from coordinator
        return self.coordinator.device_profiles.get(self.device_serial, [])

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        adapter = self.zone_data.get("adapter", {})
        device_data = self.device_data

        # Check both adapter and device data for connection status
        adapter_connected = adapter.get("connected", False)
        device_connected = device_data.get("connected", adapter_connected)

        return device_connected

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.zone_data.get("name", f"Zone {self.zone_id}")

    @property
    def unique_id(self) -> str:
        """Return a unique ID for the device."""
        return f"{self.device_serial}_{self.zone_id}"

    @property
    def device_info(self) -> "DeviceInfo":  # Optimization 27: Add type hint
        """Return device information shared across all entities (Optimization 12).

        This consolidates duplicate device_info implementations from climate and sensor entities.
        """
        from homeassistant.helpers.device_registry import DeviceInfo
        from .const import DOMAIN

        zone_data = self.zone_data
        device_data = self.device_data
        model = device_data.get("model", {}).get("materialDescription", "Unknown Model")

        return DeviceInfo(
            identifiers={(DOMAIN, self.device_serial)},
            name=zone_data.get("name", "Kumo Cloud Device"),
            manufacturer="Mitsubishi Electric",
            model=model,
            sw_version=device_data.get("model", {}).get("serialProfile"),
            serial_number=device_data.get("serialNumber"),
        )

    async def send_command(self, commands: dict[str, Any]) -> None:
        """Send a command to the device and refresh status."""
        try:
            response = await self.coordinator.api.send_command(self.device_serial, commands)
            _LOGGER.debug("Sent command to device %s: %s, Response: %s", self.device_serial, commands, response)

            # Cache the commands in the coordinator immediately
            self.cache_commands(commands)

            # Optimization 17: Wait for command to be processed (configurable)
            await asyncio.sleep(COMMAND_SETTLE_TIME)

            # Refresh this specific device's data immediately
            await self.coordinator.async_refresh_device(self.device_serial)

        except Exception as err:
            _LOGGER.error(
                "Failed to send command to device %s: %s", self.device_serial, err
            )
            raise

    def cache_command(self, command: str, value: Any) -> None:
        """Cache a command with its value and timestamp in the coordinator."""
        self.coordinator.cache_command(self.device_serial, command, value)

    def cache_commands(self, commands: dict[str, Any]) -> None:
        """Cache multiple commands with their values and timestamps in the coordinator."""
        for command, value in commands.items():
            self.cache_command(command, value)

    def async_shutdown(self) -> None:
        """Shutdown coordinator and clean up resources (Optimization 34)."""
        self.cached_commands.clear()
        _LOGGER.debug("Coordinator shutdown complete - cleared cached commands")
