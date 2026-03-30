import json
import os
from typing import Any

import httpx
import pytest
from dotenv import load_dotenv

from yazot.mcp_server import mcp


@pytest.fixture(scope="session", autouse=True)
def load_test_env() -> None:
    """Automatically load .env.test for all tests in the session.

    Also copies TEST_ZOTERO_* values to ZOTERO_* to isolate MCP lifespan
    from production .env credentials. Without this, Client(mcp) → app_lifespan
    → Settings() would read production tokens from .env.
    """
    env_test_path = os.path.join(os.path.dirname(__file__), "..", ".env.test")
    if os.path.exists(env_test_path):
        load_dotenv(env_test_path, override=True)
    else:
        load_dotenv(".env.test", override=True)

    # Isolate MCP lifespan from production .env:
    # Copy TEST_ZOTERO_* → ZOTERO_* so Settings() uses test credentials
    for suffix in ("LOCAL", "LIBRARY_ID", "API_KEY", "LIBRARY_TYPE"):
        test_val = os.environ.get(f"TEST_ZOTERO_{suffix}")
        if test_val is not None:
            os.environ[f"ZOTERO_{suffix}"] = test_val


# WORKAROUND: FastMCP lifespan cleanup bug
# FastMCP 2.x (and 3.x) never resets _lifespan_result_set after Client
# disconnects because the cleanup code in _lifespan_manager() is unreachable
# due to anyio task group cancellation.  This causes subsequent Client(mcp)
# sessions to reuse stale lifespan context with already-closed resources.
# Reproduction & details: ~/Projects/fastmcp-lifespan-issue/
# TODO: remove when FastMCP fixes _lifespan_manager() cleanup
@pytest.fixture(autouse=True)
def _reset_mcp_lifespan() -> None:
    """Force FastMCP to create a fresh lifespan on each test."""
    mcp._lifespan_result_set = False
    mcp._lifespan_result = None


# Test helpers


def make_httpx_response(
    status_code: int = 200,
    json_data: dict[str, Any] | None = None,
    content: bytes = b"",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Create a mock httpx.Response for testing HTTP clients.

    If json_data is provided, it is serialized to content and content-type
    header is set to application/json automatically.
    """
    if json_data is not None:
        content = json.dumps(json_data).encode()
        headers = {**(headers or {}), "content-type": "application/json"}
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers=headers or {},
        request=httpx.Request("GET", "https://example.com"),
    )
