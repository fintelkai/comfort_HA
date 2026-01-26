"""Common fixtures for Kumo Cloud tests (Optimization 30)."""
import pytest
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.kumo_cloud.const import CONF_SITE_ID, DOMAIN


@pytest.fixture
def mock_kumo_api():
    """Mock Kumo Cloud API client."""
    with patch("custom_components.kumo_cloud.api.KumoCloudAPI") as mock:
        api_instance = mock.return_value
        api_instance.access_token = "test_token"
        api_instance.refresh_token = "test_refresh"
        api_instance.login.return_value = {"token": {"access": "test_token", "refresh": "test_refresh"}}
        api_instance.get_sites.return_value = [
            {"id": "site_1", "name": "Test Site"}
        ]
        api_instance.get_zones.return_value = [
            {
                "id": "zone_1",
                "name": "Test Zone",
                "adapter": {"deviceSerial": "device_1"}
            }
        ]
        api_instance.get_device_details.return_value = {
            "serialNumber": "device_1",
            "model": {"materialDescription": "Test Model"},
            "roomTemp": 22.5,
            "operationMode": "cool",
            "power": 1,
        }
        api_instance.get_device_profile.return_value = [
            {
                "numberOfFanSpeeds": 5,
                "hasVaneSwing": True,
                "hasModeHeat": True,
            }
        ]
        yield api_instance


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        CONF_USERNAME: "test@example.com",
        CONF_SITE_ID: "site_1",
        "access_token": "test_token",
        "refresh_token": "test_refresh",
    }
    entry.options = {}
    return entry
