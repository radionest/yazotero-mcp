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
