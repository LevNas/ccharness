# Local workspace files

Personal working state does not get committed to the shared repository.

## Never commit

- Personal plans and progress (for example `.claude/tasks/`, unless the team decided to share them)
- Sensitive personal notes and background (`.claude/private/`)
- Work logs, time logs, scratch output
- Personal environment settings (`.claude/settings.local.json`, editor settings)

List them in `.gitignore`. When unsure, do not commit; ask the user.

## Keep personal environment details out of shared settings

`CLAUDE.md`, `.claude/settings.json` and `.claude/rules/` are shared. Machine-specific values, paths and preferences belong in `~/.claude/` or `settings.local.json`.

## Worktree sessions

- To carry gitignored local files into every new worktree, list them in `.worktreeinclude` at the project root (`.gitignore` syntax). Do not copy them by hand.
- Untracked working files produced in an isolated worktree are moved back to the main checkout before the worktree is removed.
