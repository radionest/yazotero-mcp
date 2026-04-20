# Worktree PR workflow

## PR creation sequence

1. Finish ALL code changes (including nit-fixes, docstring updates)
2. Commit and push
3. Run `pr-diff-reviewer` agent
4. Only then `gh pr create`

Each new commit after review invalidates it — the hook checks SHA match.
Do NOT fix reviewer nits after review; fix them before, then re-review.

## gh pr merge from worktree

`gh pr merge` without `--repo` fails in a worktree because local git can't checkout main.
Always use: `gh pr merge N --squash --delete-branch --repo owner/repo`

## Files after EnterWorktree

Files read from the main project path are NOT counted as read for worktree paths.
After `EnterWorktree`, re-read files before editing them.
