---
globs: ["yazot/**/*.py"]
---
# mypy type narrowing

mypy does not narrow types through compound conditions like `if x is None and not y`.
Use early return/raise for each check separately, or an explicit annotation:
`val: str = param  # type: ignore[assignment]` after the guard.

# @computed_field

Pydantic `@computed_field` is not supported by the mypy pydantic plugin as a property.
For type-safe access use `item.data.field` instead of `item.field`.

# asyncio.gather(return_exceptions=True)

Return type is `list[T | BaseException]`. mypy does not narrow via `isinstance(result, Exception)`.
Use `isinstance(result, BaseException)` for narrowing, then separate Exception from non-Exception:

```python
for result in results:
    if isinstance(result, BaseException):
        if not isinstance(result, Exception):
            raise result  # CancelledError, KeyboardInterrupt
        logger.warning("...", result)
        continue
    # here result is narrowed to T
```

# type: ignore и import stubs

Проект использует `ignore_missing_imports = true` (pyproject.toml) — mypy НЕ ругается на импорт библиотек без стабов.
Не добавляй `# type: ignore[import-untyped]` превентивно. Сначала запусти `uv run mypy yazot/`.

`warn_unused_ignores = true` — лишние `type: ignore` комментарии вызывают ошибку.
