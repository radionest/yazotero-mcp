import os
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from yazot.config import Settings
from yazot.zotero_client import ZoteroClient

if TYPE_CHECKING:
    from tests.live.zotero_instance import ZoteroInstance

_THIS_DIR = str(Path(__file__).parent)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_marker = (
        pytest.mark.skip(reason="ZOTERO_TEST_INSTANCE not enabled")
        if os.getenv("ZOTERO_TEST_INSTANCE", "false").lower() != "true"
        else None
    )
    for item in items:
        if str(item.fspath).startswith(_THIS_DIR):
            item.add_marker(pytest.mark.live)
            if skip_marker is not None:
                item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def zotero_test_environment() -> Generator["ZoteroInstance | None", None, None]:
    """Provision an isolated Zotero process for integration tests."""
    from tests.live.zotero_instance import (
        ZoteroInstance,
        ZoteroInstancePool,
        ZoteroProcessGuard,
        detect_xvfb_needed,
    )

    if os.getenv("ZOTERO_TEST_INSTANCE", "false").lower() != "true":
        yield None
        return

    zotero_bin = Path(os.getenv("ZOTERO_BIN_PATH", "zotero"))
    guard = ZoteroProcessGuard()
    guard.cleanup_stale()

    use_xvfb = detect_xvfb_needed()
    pool = ZoteroInstancePool(
        zotero_bin=zotero_bin,
        guard=guard,
        use_xvfb=use_xvfb,
    )

    instance: ZoteroInstance | None = None
    try:
        instance = pool.acquire()
        yield instance
    finally:
        pool.release_all()


@pytest.fixture(scope="session")
def local_live_client(
    zotero_test_environment: "ZoteroInstance | None",
) -> ZoteroClient | None:
    """ZoteroClient connected to the live local Zotero instance."""
    if zotero_test_environment is None:
        return None
    settings = Settings(
        zotero_local=True,
        zotero_port=zotero_test_environment.port,
        zotero_library_id="0",
    )
    return ZoteroClient(settings)
