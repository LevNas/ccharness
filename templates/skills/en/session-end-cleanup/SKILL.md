---
name: session-end-cleanup
description: At session end or when asked to tidy branches, detect local branches and worktrees that are merged or whose upstream is gone, classify them as A (safe to delete) or B (worktree attached), and ask the user. Never deletes anything itself.
license: MIT
allowed-tools: Bash, Read
---

# session-end-cleanup — branch and worktree inventory

This skill **detects and proposes only**. Deletion is the user's call.

## Trigger

- End of session (after session-wrap)
- After a merge instruction
- "Tidy up the stale branches"

## Steps

1. Reflect remote deletions: `git fetch origin --prune`
2. Collect:
   - merged into main: `git branch --merged main --format '%(refname:short)'`
   - upstream gone: `git for-each-ref --format '%(refname:short) %(upstream:track)' refs/heads | grep gone`
   - branches checked out in worktrees: `git worktree list --porcelain`
3. Classify. Protected branches (`main`, `master`, `develop`, `release`) and the current branch are excluded.
   - **A. Safe to delete**: merged or upstream gone, no worktree → `git branch -d <branch>`
   - **B. Waiting**: same, but a worktree is attached → `git worktree remove <path>` first, then `git branch -d <branch>`. Move untracked working files (logs, captures) out of the worktree before removing it.
   - **C. Active**: everything else. Leave alone.
4. Present the classification with the commands and ask the user whether to run them.

## Notes

- `-D` (force) discards unmerged work; use it only when the user asks for it explicitly.
- Never remove a worktree another session is using.
