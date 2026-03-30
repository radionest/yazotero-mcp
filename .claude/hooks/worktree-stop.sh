#!/bin/bash
# Stop hook: блокирует завершение сессии в worktree,
# чтобы Claude спросил пользователя о судьбе изменений.

INPUT=$(cat)

# Предотвращаем бесконечный цикл — на повторной попытке пропускаем
if echo "$INPUT" | grep -qE '"stop_hook_active"\s*:\s*true'; then
  exit 0
fi

# Проверяем, что мы в git-репозитории
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# Проверяем, что это worktree (не основной репо)
GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
GIT_COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null)
if [ "$GIT_DIR" = "$GIT_COMMON_DIR" ]; then
  exit 0
fi

# Собираем информацию о состоянии
BRANCH=$(git branch --show-current 2>/dev/null)
HAS_CHANGES=$(git status --porcelain 2>/dev/null | head -1)
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"
AHEAD=$(git rev-list "$DEFAULT_BRANCH"..HEAD --count 2>/dev/null || echo "0")

# Блокируем stop — stderr покажется Claude
cat >&2 <<EOF
WORKTREE_PENDING: Сессия в worktree, ветка '$BRANCH'.
Коммитов впереди main: $AHEAD
Незакоммиченные изменения: $([ -n "$HAS_CHANGES" ] && echo "есть" || echo "нет")

Перед завершением спроси пользователя:
1) Push ветки + создать PR в main + удалить worktree
2) Оставить worktree (для продолжения позже)
3) Отменить изменения + удалить worktree
EOF

exit 2
