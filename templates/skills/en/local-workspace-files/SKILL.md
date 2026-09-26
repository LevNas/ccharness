---
name: local-workspace-files
description: Detail on local workspace files (personal plans, work logs, personal settings) - why they are not shared, the .gitignore layout, carrying them into worktrees with .worktreeinclude, and moving work back out. The skeleton is .claude/rules/local-workspace-files.md.
license: MIT
allowed-tools: Read, Bash
---

# Local workspace files (detail)

The skeleton is in `.claude/rules/local-workspace-files.md`. This skill adds the reasons and procedures.

## Why they are not shared

- Personal progress and plans carry no context for other members; they go unread and add review load.
- Sensitive background (personnel, evaluations, personal circumstances) stays out of shared repositories on the minimisation principle.
- Machine-specific values (paths, hostnames, preferences) in shared settings break other environments.

## .gitignore layout

```
.claude/tasks/
.claude/private/
.claude/settings.local.json
.claude/worktrees/
CLAUDE.local.md
*.timelog
```

Anything the team decides to share (for example a shared task ledger) is removed from the list at that point. Ignoring `.claude/worktrees/` keeps worktree contents from showing up as untracked files in the main checkout.

## Worktree sessions

- **Carry in (main → worktree)**: a new worktree is a checkout of tracked files only, so gitignored files such as `.env` or `settings.local.json` are absent. List them in `.worktreeinclude` at the project root (`.gitignore` syntax) and Claude Code copies them into every worktree it creates (`--worktree`, subagent worktrees, desktop parallel sessions). Only files that match a pattern and are also gitignored are copied.

  ```
  .env
  .claude/settings.local.json
  ```

- **Read-through**: when the worktree root has no `.claude/skills`, the main checkout's skills, agents and commands load in the worktree session. Gitignored skills need no copying.
- **Base branch**: the default is the remote default branch (`worktree.baseRef: "fresh"`); use `"head"` to carry unpushed work into the worktree.
- **Carry back (worktree → main)**: move untracked working files created in the worktree (captures, logs) to the same place in the main checkout before removing the worktree. On a name clash, keep both with a session identifier.
- **When no path works**: park the files in a temporary directory and tell the user where.

## Where personal settings live

| Content | Location |
|---|---|
| Your own style across every repository | `~/.claude/CLAUDE.md`, `~/.claude/rules/` |
| Personal notes for this repository only | `CLAUDE.local.md` (gitignored) |
| Personal permission or env differences | `.claude/settings.local.json` |
