---
globs: ["yazot/**/*.py"]
---

# Error handling

- Always use `raise CustomError(...) from e` when re-raising inside except blocks (ruff B904)
- pyzotero uses httpx internally; `httpx.ConnectError`, `httpx.TimeoutException` do NOT inherit `zotero_errors.PyZoteroError` — catch them separately or use `except Exception` as catch-all
- All exceptions escaping MCP tool handlers must inherit `ToolError` (via `ZoteroError`), otherwise `mask_error_details=True` hides the message from the client
