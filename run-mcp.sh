#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "$SCRIPT_DIR/.env"
set +a
exec "$SCRIPT_DIR/.venv/bin/python" -m yazot.mcp_server
