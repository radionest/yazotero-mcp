#!/bin/bash
# PostToolUse hook: auto-format Python files after Edit/Write.

FILE="$TOOL_INPUT_FILE_PATH"

[[ "$FILE" == *.py ]] || exit 0

uv run bash -c 'ruff check --fix --quiet "$1" 2>/dev/null; black --quiet "$1" 2>/dev/null' _ "$FILE"
