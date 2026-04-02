# Testing with pydantic-settings

When clearing env vars in tests, use `monkeypatch.setenv("VAR", "")` instead of
`monkeypatch.delenv("VAR")` — pydantic-settings falls back to `.env` file values
when the env var is missing from `os.environ`, so `delenv` doesn't actually clear
the value from Settings' perspective.
