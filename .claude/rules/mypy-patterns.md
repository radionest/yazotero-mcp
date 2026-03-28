---
globs: ["yazot/**/*.py"]
---
# mypy type narrowing

mypy не сужает типы через compound conditions типа `if x is None and not y`.
Используй ранний return/raise для каждой проверки отдельно, или явную аннотацию:
`val: str = param  # type: ignore[assignment]` после guard.

# @computed_field

Pydantic `@computed_field` не поддерживается mypy pydantic plugin как property.
Для type-safe доступа используй `item.data.field` вместо `item.field`.
