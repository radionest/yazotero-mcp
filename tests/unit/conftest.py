from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yazot.config import Settings
from yazot.zotero_client import ZoteroClient

_THIS_DIR = str(Path(__file__).parent)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if str(item.fspath).startswith(_THIS_DIR):
            item.add_marker(pytest.mark.unit)


@pytest.fixture
def local_settings() -> Settings:
    """Settings for local Zotero mode."""
    return Settings(
        zotero_local=True,
        zotero_library_id="0",
        zotero_api_key=None,
        zotero_library_type="user",
    )


@pytest.fixture
def web_settings() -> Settings:
    """Settings for web Zotero mode."""
    return Settings(
        zotero_local=False,
        zotero_library_id="123456",
        zotero_api_key="test_api_key_123",
        zotero_library_type="user",
    )


@pytest.fixture
def local_test_client(local_settings: Settings) -> ZoteroClient:
    """Local Zotero client for testing router behavior."""
    return ZoteroClient(local_settings)


@pytest.fixture
def local_zotero_client(local_settings: Settings) -> ZoteroClient:
    """Local Zotero client for server startup tests."""
    return ZoteroClient(local_settings)


@pytest.fixture
def web_zotero_client(web_settings: Settings) -> ZoteroClient:
    """Web Zotero client for server startup tests."""
    with patch("yazot.zotero_client.zotero.Zotero") as mock_zotero:
        mock_zotero.return_value = MagicMock()
        return ZoteroClient(web_settings)
