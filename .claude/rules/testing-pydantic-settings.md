# Testing with pydantic-settings

`monkeypatch.delenv("VAR")` does NOT fully clear the value — pydantic-settings
falls back to `.env` file values when the env var is missing from `os.environ`.

Choose the right approach by field type:
- **str / Optional[str]**: `monkeypatch.setenv("VAR", "")` — sets to empty string
- **bool**: `monkeypatch.setenv("VAR", "false")` — pydantic coerces correctly
- **int**: `monkeypatch.delenv("VAR", raising=False)` — let pydantic use the field default
- When the field has no default and you need to disable it: set a valid sentinel value for that type
