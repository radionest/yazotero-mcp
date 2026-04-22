---
globs: "yazot/**/*.py,tests/**/*.py"
description: How to inspect external package APIs (FastMCP, pyzotero, etc.)
---

# Inspecting external package APIs

## Do NOT grep site-packages

`Grep` on `.venv/lib/.../site-packages/` fails silently on `.pyc`-only modules and misses code in mixin files. Don't waste tool calls on it.

## Use `inspect.getsource()` instead

```bash
uv run python -c "
import inspect
from fastmcp import Client
print(inspect.getsource(Client.call_tool))
"
```

Always use `uv run python`, never bare `python` — the venv is not on PATH.

## FastMCP Client.call_tool() → CallToolResult

`Client.call_tool()` returns `CallToolResult(content, structured_content, meta, data, is_error)`.
- `.data` — deserialized structured content (Pydantic model or dict), produced by `_parse_call_tool_result()` in `fastmcp.client.mixins.tools`
- When a tool returns `to_slim_dict()` (a dict), FastMCP reconstructs the model via `output_schema` → `.data` is a typed dataclass with field access
- Fields excluded by `exclude_none=True` in `model_dump()` become `None` on the reconstructed dataclass (not missing — just `None`)
