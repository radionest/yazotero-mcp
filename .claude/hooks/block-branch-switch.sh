#!/bin/bash
# PreToolUse hook for Bash: блокирует git checkout/switch в основном репозитории.
# Для переключения веток используй EnterWorktree.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -z "$COMMAND" ] && exit 0

# Проверяем git checkout/switch (но не восстановление файлов)
if ! echo "$COMMAND" | grep -qP 'git\s+(checkout|switch)\b'; then
  exit 0
fi

# Разрешаем git checkout -- <file> (восстановление файлов)
if echo "$COMMAND" | grep -qP 'git\s+(checkout|switch)\s+--\s'; then
  exit 0
fi

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# Проверяем, что мы в основном репозитории (не в worktree)
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null)

if [ "$(realpath "$GIT_DIR")" = "$(realpath "$COMMON_DIR")" ]; then
  cat >&2 <<'EOF'
BLOCKED: Переключение веток в основном репозитории запрещено.
Используй EnterWorktree для работы на другой ветке.
`git checkout -- <file>` для восстановления файлов по-прежнему доступен.
EOF
  exit 2
fi

exit 0
