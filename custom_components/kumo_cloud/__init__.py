"""The Kumo Cloud integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .api import KumoCloudAPI, KumoCloudAuthError, KumoCloudConnectionError
from .const import CONF_SITE_ID, DOMAIN, DEFAULT_SCAN_INTERVAL
from .coordinator import KumoCloudDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Kumo Cloud component (Optimization 28: Config Flow only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Kumo Cloud from a config entry."""

    # Create API client (Optimization 6: Pass config entry for token persistence)
    api = KumoCloudAPI(hass, entry)

    # Initialize with stored tokens if available
    if "access_token" in entry.data:
        api.username = entry.data[CONF_USERNAME]
        api.access_token = entry.data["access_token"]
        api.refresh_token = entry.data["refresh_token"]

    try:
        # Optimization 20: Handle missing password (no longer stored for security)
        # Try to login or refresh tokens
        if not api.access_token:
            # No tokens available - need password for initial login
            if CONF_PASSWORD in entry.data:
                # Legacy entry with password still stored
                await api.login(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
            else:
                # New entry without password - trigger reauth
                raise ConfigEntryAuthFailed("Re-authentication required")
        else:
            # Verify the token works by making a test request
            try:
                await api.get_account_info()
            except KumoCloudAuthError:
                # Token expired - try refresh, or trigger reauth if that fails
                # The coordinator will handle token refresh, so just fail auth here
                raise ConfigEntryAuthFailed("Token expired - re-authentication required")

    except KumoCloudAuthError as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
    except KumoCloudConnectionError as err:
        raise ConfigEntryNotReady(f"Unable to connect: {err}") from err

    # Remove any legacy password storage and persist fresh tokens after login.
    updated_data = dict(entry.data)
    needs_entry_update = False

    if CONF_PASSWORD in updated_data:
        updated_data.pop(CONF_PASSWORD, None)
        needs_entry_update = True

    if api.access_token and updated_data.get("access_token") != api.access_token:
        updated_data["access_token"] = api.access_token
        needs_entry_update = True

    if api.refresh_token and updated_data.get("refresh_token") != api.refresh_token:
        updated_data["refresh_token"] = api.refresh_token
        needs_entry_update = True

    if needs_entry_update:
        hass.config_entries.async_update_entry(entry, data=updated_data)

    # Create the coordinator (Optimization 22: Use options for scan_interval)
    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    coordinator = KumoCloudDataUpdateCoordinator(hass, api, entry.data[CONF_SITE_ID], scan_interval)

    # Fetch initial data so we have data when entities are added
    await coordinator.async_config_entry_first_refresh()

    # Optimization 24: Clean up orphaned entities
    await _async_cleanup_entities(hass, entry, coordinator)

    # Store coordinator in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Optimization 22: Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Optimization 31: Register custom services
    await _async_register_services(hass)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change (Optimization 22)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Optimization 34: Clean up coordinator resources
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if hasattr(coordinator, "async_shutdown"):
            await coordinator.async_shutdown()

    return unload_ok



async def _async_cleanup_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator,
) -> None:
    """Remove entities for devices that no longer exist (Optimization 24)."""
    entity_reg = er.async_get(hass)

    # Get current device serials
    current_devices = {
        zone["adapter"]["deviceSerial"]
        for zone in coordinator.zones
        if "adapter" in zone and zone["adapter"]
    }

    # Find and remove orphaned entities
    for entity in er.async_entries_for_config_entry(entity_reg, entry.entry_id):
        # Extract device serial from unique_id (format varies by entity type)
        parts = entity.unique_id.split("_")
        if len(parts) >= 1:
            device_serial = parts[0]
            if device_serial not in current_devices:
                entity_reg.async_remove(entity.entity_id)
                _LOGGER.info("Removed orphaned entity: %s", entity.entity_id)



async def _async_register_services(hass: HomeAssistant) -> None:
    """Register custom services (Optimization 31)."""
    
    # Only register once
    if hass.services.has_service(DOMAIN, "refresh_device"):
        return

    async def async_refresh_device_service(call: ServiceCall) -> None:
        """Handle refresh_device service call."""
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return
        
        # Find the device serial from entity
        entity_reg = er.async_get(hass)
        entity_entry = entity_reg.async_get(entity_id)
        
        if not entity_entry:
            _LOGGER.error("Entity %s not found", entity_id)
            return
        
        # Get coordinator from entry
        coordinator = hass.data[DOMAIN].get(entity_entry.config_entry_id)
        if not coordinator:
            _LOGGER.error("Coordinator not found for entity %s", entity_id)
            return
        
        # Extract device serial from unique_id
        device_serial = entity_entry.unique_id.split("_")[0]
        
        _LOGGER.info("Forcing refresh for device %s", device_serial)
        await coordinator.async_refresh_device(device_serial)

    async def async_clear_cache_service(call: ServiceCall) -> None:
        """Handle clear_cache service call."""
        entity_id = call.data.get("entity_id")
        
        if entity_id:
            # Clear cache for specific device
            entity_reg = er.async_get(hass)
            entity_entry = entity_reg.async_get(entity_id)
            
            if not entity_entry:
                _LOGGER.error("Entity %s not found", entity_id)
                return
            
            coordinator = hass.data[DOMAIN].get(entity_entry.config_entry_id)
            if coordinator:
                device_serial = entity_entry.unique_id.split("_")[0]
                # Remove cached commands for this device
                keys_to_remove = [
                    key for key in coordinator.cached_commands.keys()
                    if key[0] == device_serial
                ]
                for key in keys_to_remove:
                    del coordinator.cached_commands[key]
                _LOGGER.info("Cleared %d cached commands for device %s", len(keys_to_remove), device_serial)
        else:
            # Clear all caches
            for coordinator in hass.data[DOMAIN].values():
                count = len(coordinator.cached_commands)
                coordinator.cached_commands.clear()
                _LOGGER.info("Cleared %d cached commands", count)

    hass.services.async_register(
        DOMAIN,
        "refresh_device",
        async_refresh_device_service,
        schema=vol.Schema({
            vol.Required("entity_id"): cv.entity_id,
        }),
    )

    hass.services.async_register(
        DOMAIN,
        "clear_cache",
        async_clear_cache_service,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
        }),
    )
