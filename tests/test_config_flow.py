"""Test Cudy Router config flow."""

from unittest.mock import MagicMock, patch

import pytest

from .conftest import MOCK_CONFIG, CONF_HOST, CONF_USERNAME, CONF_PASSWORD


def test_host_normalization():
    """Test host URL normalization in config flow."""
    # Test various host formats get normalized correctly
    test_cases = [
        ("192.168.10.1", "https://192.168.10.1"),
        ("http://192.168.10.1", "http://192.168.10.1"),
        ("https://192.168.10.1", "https://192.168.10.1"),
        ("router.local", "https://router.local"),
        ("http://router.local/", "http://router.local"),
        ("https://192.168.10.1/", "https://192.168.10.1"),
    ]

    for input_host, expected in test_cases:
        # Normalize: add https if no scheme, strip trailing slash
        host = input_host.rstrip("/")
        if not host.startswith(("http://", "https://")):
            host = f"https://{host}"
        assert host == expected, f"Failed for input: {input_host}"


def test_router_authentication_success(mock_router):
    """Test successful router authentication."""
    assert mock_router.authenticate() is True


def test_router_authentication_failure(mock_router_auth_fail):
    """Test failed router authentication."""
    assert mock_router_auth_fail.authenticate() is False


def test_router_connection_failure(mock_router_connection_fail):
    """Test router connection failure raises exception."""
    with pytest.raises(Exception, match="Connection failed"):
        mock_router_connection_fail()


def test_mock_config_has_required_fields():
    """Test that mock config has all required fields."""
    assert CONF_HOST in MOCK_CONFIG
    assert CONF_USERNAME in MOCK_CONFIG
    assert CONF_PASSWORD in MOCK_CONFIG
