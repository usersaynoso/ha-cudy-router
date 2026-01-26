"""Common fixtures for Cudy Router tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.cudy_router.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_router() -> Generator[MagicMock]:
    """Create a mock CudyRouter instance."""
    with patch(
        "custom_components.cudy_router.config_flow.CudyRouter"
    ) as mock_router_class:
        router = MagicMock()
        router.authenticate.return_value = True
        mock_router_class.return_value = router
        yield router


@pytest.fixture
def mock_router_auth_fail() -> Generator[MagicMock]:
    """Create a mock CudyRouter instance that fails authentication."""
    with patch(
        "custom_components.cudy_router.config_flow.CudyRouter"
    ) as mock_router_class:
        router = MagicMock()
        router.authenticate.return_value = False
        mock_router_class.return_value = router
        yield router


MOCK_CONFIG = {
    CONF_HOST: "192.168.10.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "password123",
}
