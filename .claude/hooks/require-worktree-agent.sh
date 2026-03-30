#!/bin/bash
# PreToolUse hook for Agent: блокирует аналитических и девелоперских агентов на main.
# Заставляет войти в worktree перед запуском, чтобы анализ и правки были в одном контексте.

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

BRANCH=$(git branch --show-current 2>/dev/null)
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"
[ "$BRANCH" != "$DEFAULT_BRANCH" ] && exit 0

# Read tool input from stdin
INPUT=$(cat)

# Extract subagent_type
SUBAGENT=$(echo "$INPUT" | sed -n 's/.*"subagent_type"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')

# Block development agents on main (Explore is read-only — allowed)
case "$SUBAGENT" in
  Plan|python-developer|feature-dev:*)
    cat >&2 <<'EOF'
BLOCKED: Аналитический/архитектурный агент на ветке main.
Войди в worktree через EnterWorktree перед запуском анализа или разработки.
Это обеспечит, что анализ и последующие изменения будут в одном worktree.
EOF
    exit 2
    ;;
esac

exit 0
