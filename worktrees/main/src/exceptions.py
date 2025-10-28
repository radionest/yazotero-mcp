"""Exception classes for Zotero MCP server.

All custom exceptions inherit from FastMCP's ToolError to ensure
proper error message delivery to MCP clients.
"""

from typing import Any

from fastmcp.exceptions import ToolError


class ZoteroError(ToolError):
    """Base exception for all Zotero MCP operations.

    Inherits from ToolError to ensure error messages are properly
    transmitted to MCP clients regardless of mask_error_details setting.
    """

    pass


class ZoteroNotFoundError(ZoteroError):
    """Raised when requested item, collection, or chunk is not found.

    Args:
        resource_type: Type of resource (e.g., 'item', 'collection', 'chunk')
        identifier: Resource identifier (key, ID, etc.)

    Examples:
        >>> raise ZoteroNotFoundError("item", "ABC123")
        >>> raise ZoteroNotFoundError("chunk", "uuid-here")
    """

    def __init__(self, resource_type: str, identifier: str):
        super().__init__(f"{resource_type} not found: {identifier}")
        self.resource_type = resource_type
        self.identifier = identifier


class ZoteroWriteError(ZoteroError):
    """Raised when Zotero write operations (create/update) fail.

    Stores detailed failure information including operation type and
    per-item failure details from Zotero API response.

    Args:
        operation: Type of operation (e.g., 'create_items', 'create_collections')
        failures: Dict mapping request indices to failure details
                 Format: {"0": {"key": "", "code": 400, "message": "..."}, ...}

    Attributes:
        operation: Operation type that failed
        failures: Detailed failure information for each failed item
    """

    def __init__(self, operation: str, failures: dict[str, Any]):
        self.operation = operation
        self.failures = failures

        # Build human-readable error message
        failed_details = [
            f"Index {idx}: {fail.get('message', 'Unknown error')} "
            f"(code {fail.get('code', 'N/A')})"
            for idx, fail in failures.items()
        ]
        message = f"Failed to {operation}: {'; '.join(failed_details)}"
        super().__init__(message)


class ContentNotAvailableError(ZoteroError):
    """Raised when requested content (fulltext, attachments) is not available.

    This can occur when:
    - Item has no PDF attachment
    - Fulltext extraction failed
    - Attachment file is missing

    Examples:
        >>> raise ContentNotAvailableError("No fulltext available for this item")
    """

    pass


class ConfigurationError(ZoteroError):
    """Raised when server configuration is invalid or incomplete.

    Typically occurs during initialization when required environment
    variables are missing or have invalid values.

    Examples:
        >>> raise ConfigurationError("ZOTERO_API_KEY required for web mode")
    """

    pass


class WebOnlyOperationError(ZoteroError):
    """Raised when attempting a web-only operation with a local client.

    The local Zotero API (http://localhost:23119/api) is read-only and
    does not support write operations. This error is raised when trying
    to perform create, update, or delete operations using a local client.

    Args:
        operation: Name of the operation attempted (e.g., 'create_items', 'update_item')

    Examples:
        >>> raise WebOnlyOperationError("create_items")
        >>> raise WebOnlyOperationError("delete_collection")
    """

    def __init__(self, operation: str):
        message = (
            f"Operation '{operation}' requires web API access. "
            "The local Zotero API is read-only. "
            "Please configure ZOTERO_API_KEY and set ZOTERO_LOCAL=false to use web API."
        )
        super().__init__(message)
        self.operation = operation
