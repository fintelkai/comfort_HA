"""Diagnostics support for Kumo Cloud (Optimization 23)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_SITE_ID, DOMAIN

TO_REDACT = {
    "access_token",
    "refresh_token",
    "username",
    "password",
    "serialNumber",
    "deviceSerial",
    "email",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": entry.options,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update_time": coordinator.last_update_success_time.isoformat()
            if coordinator.last_update_success_time
            else None,
            "zones_count": len(coordinator.zones),
            "devices_count": len(coordinator.devices),
            "cached_commands_count": len(coordinator.cached_commands),
        },
        "zones": async_redact_data(coordinator.zones, TO_REDACT),
        "devices": async_redact_data(coordinator.devices, TO_REDACT),
        "device_profiles": coordinator.device_profiles,
    }
