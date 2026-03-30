from pathlib import Path

import pytest

_THIS_DIR = str(Path(__file__).parent)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if str(item.fspath).startswith(_THIS_DIR):
            item.add_marker(pytest.mark.external)
