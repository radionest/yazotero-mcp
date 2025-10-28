"""Protocol decorators and utilities for Zotero client operations.

This module provides decorators that enforce API compatibility rules,
particularly for operations that are only supported by the web API.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from .exceptions import WebOnlyOperationError

# Type variable for generic function signatures
F = TypeVar("F", bound=Callable[..., Any])


def webonly(func: F) -> F:
    """Decorator to mark methods that require web API access.

    The local Zotero API (http://localhost:23119/api) is read-only and does
    not support write operations. This decorator ensures that methods marked
    with @webonly will raise WebOnlyOperationError when called on a client
    configured for local mode.

    The decorator checks the 'mode' attribute of the first argument (self),
    which should be a ZoteroClient instance.

    Usage:
        class ZoteroClient:
            def __init__(self):
                self.mode = "local"  # or "web"

            @webonly
            async def create_items(self, items):
                # This will raise if self.mode == "local"
                ...

    Raises:
        WebOnlyOperationError: If called on a local mode client

    Args:
        func: The method to decorate (should be a method of ZoteroClient)

    Returns:
        Decorated method that checks client mode before execution
    """

    @wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Check if client is in local mode
        if hasattr(self, "mode") and self.mode == "local":
            raise WebOnlyOperationError(func.__name__)

        # Execute original method
        return await func(self, *args, **kwargs)

    return wrapper  # type: ignore
