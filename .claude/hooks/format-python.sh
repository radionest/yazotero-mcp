#!/bin/bash
# PostToolUse hook: auto-format Python files after Edit/Write.

FILE="$TOOL_INPUT_FILE_PATH"

[[ "$FILE" == *.py ]] || exit 0

uv run ruff check --fix --quiet "$FILE" 2>/dev/null
uv run black --quiet "$FILE" 2>/dev/null
