---
name: local-workspace-files
description: Detail on local workspace files (personal plans, work logs, sensitive context, personal settings) - why they are not shared, the .gitignore layout, and how to carry them into and back out of background or worktree sessions. The skeleton is .claude/rules/local-workspace-files.md.
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
CLAUDE.local.md
*.timelog
```

Anything the team decides to share (for example a shared task ledger) is removed from the list at that point.

## Background and worktree sessions

- **Carry in (main → worktree)**: untracked files are not copied into an isolated worktree. Copy only what the work needs.
- **Carry back (worktree → main)**: move untracked working files created in the worktree (captures, logs) to the same place in the main checkout before removing the worktree. On a name clash, keep both with a session identifier.
- **When no path works**: park the files in a temporary directory and tell the user where.

## Where personal settings live

| Content | Location |
|---|---|
| Your own style across every repository | `~/.claude/CLAUDE.md`, `~/.claude/rules/` |
| Personal notes for this repository only | `CLAUDE.local.md` (gitignored) |
| Personal permission or env differences | `.claude/settings.local.json` |
