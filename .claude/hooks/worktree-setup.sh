#!/bin/bash
# WorktreeCreate hook: symlink .env files from main repo + install dev dependencies.

ROOT=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")

for f in .env .env.test; do
  [ -f "$ROOT/$f" ] && [ ! -e "$f" ] && ln -s "$ROOT/$f" "$f"
done

uv sync --group dev
