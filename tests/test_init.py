"""Test Kumo Cloud integration setup (Optimization 30)."""
import pytest
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.kumo_cloud import async_setup, async_setup_entry, async_unload_entry
from custom_components.kumo_cloud.const import DOMAIN


async def test_async_setup(hass: HomeAssistant):
    """Test the component setup."""
    assert await async_setup(hass, {}) is True


async def test_setup_entry(hass: HomeAssistant, mock_config_entry, mock_kumo_api):
    """Test successful setup of entry."""
    with patch("custom_components.kumo_cloud.KumoCloudAPI", return_value=mock_kumo_api):
        assert await async_setup_entry(hass, mock_config_entry) is True
        assert DOMAIN in hass.data
        assert mock_config_entry.entry_id in hass.data[DOMAIN]


async def test_unload_entry(hass: HomeAssistant, mock_config_entry, mock_kumo_api):
    """Test unload of entry."""
    with patch("custom_components.kumo_cloud.KumoCloudAPI", return_value=mock_kumo_api):
        # Setup first
        await async_setup_entry(hass, mock_config_entry)

        # Then unload
        assert await async_unload_entry(hass, mock_config_entry) is True
        assert mock_config_entry.entry_id not in hass.data.get(DOMAIN, {})
