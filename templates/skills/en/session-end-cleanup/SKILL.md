---
name: session-end-cleanup
description: At session end, after a merge, or when asked to tidy branches - inventory branches and worktrees from the main checkout with ccharness:worktree-sweep and ask the user which to delete. Never deletes anything itself.
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

1. Work from the main checkout. If this session is isolated in a worktree, leave it first with `ExitWorktree` (`action: keep`).
2. Invoke the **`ccharness:worktree-sweep`** skill. It fetches, fast-forwards the base branch when that loses nothing, and classifies every branch and worktree as delete / review / in-use with the commands to run.
3. Show the report and ask the user which commands to run. Run only those.

### Without ccharness

If the skill is not available, do the same by hand:

1. `git fetch origin --prune`, then `git pull --ff-only` on the base branch in the main checkout (a stale local base branch makes later checks wrong).
2. For each branch, decide by content, not by labels:
   - `git merge-base --is-ancestor <branch> origin/<base>` succeeds → merged.
   - Otherwise `git cherry origin/<base> <branch>`: only `-` lines and no merge commits of its own (`git rev-list --merges origin/<base>..<branch>` is empty) → the same patches are already there; any `+` line → not merged.
   - `[gone]` only means the remote branch was deleted. It is not evidence of a merge.
3. For a branch with a worktree, also check `git -C <worktree> status --porcelain --ignored`: uncommitted, untracked and ignored files all count. `git worktree remove` refuses the first two but deletes ignored files without asking.
4. Present: **delete** (merged, nothing left) with `git worktree remove <path>` (no `--force`) and `git branch -d <branch>`; **review** (anything else) with the reason; leave worktrees locked by a running session alone.

## Notes

- `-D` (force) discards unmerged work and git does not check it. Propose it only with a `git cherry` result of all `-` and no merge commits on the branch, and run it only when the user agrees.
- Never remove a worktree another session is using.
