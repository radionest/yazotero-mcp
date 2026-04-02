---
globs: ["yazot/models.py", "yazot/mcp_server.py"]
---

# FastMCP response serialization

- FastMCP generates `output_schema` via `type_adapter.json_schema(mode="serialization")`
- `@model_serializer(mode="wrap")` on tool return types breaks this — schema degrades to `{"type": "object"}`, client gets raw dict instead of typed dataclass
- `@model_serializer` on **nested** models (e.g. `ZoteroItem`) is fine — only top-level return types are affected
- For slimming responses: use `to_slim_dict()` pattern (returns `model_dump(exclude_none=True)` as dict)
- Return type annotation must stay as the Pydantic model (for schema generation), add `# type: ignore[return-value]`
