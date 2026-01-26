"""Common fixtures for Cudy Router tests."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

# Define constants locally to avoid homeassistant dependency in tests
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"


@pytest.fixture
def mock_router() -> Generator[MagicMock, None, None]:
    """Create a mock CudyRouter instance."""
    router = MagicMock()
    router.authenticate.return_value = True
    yield router


@pytest.fixture
def mock_router_auth_fail() -> Generator[MagicMock, None, None]:
    """Create a mock CudyRouter instance that fails authentication."""
    router = MagicMock()
    router.authenticate.return_value = False
    yield router


@pytest.fixture
def mock_router_connection_fail() -> Generator[MagicMock, None, None]:
    """Create a mock that raises exception on instantiation."""
    mock = MagicMock(side_effect=Exception("Connection failed"))
    yield mock


MOCK_CONFIG = {
    CONF_HOST: "192.168.10.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "password123",
}
