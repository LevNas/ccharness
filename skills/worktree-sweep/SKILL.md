---
name: worktree-sweep
description: From the main checkout, fetch, fast-forward the base branch and classify leftover branches and worktrees as delete / review / in-use with the commands to run. Report only. Called by session-end-cleanup; use at session end, after a merge, or when asked to tidy branches.
license: MIT
allowed-tools: Bash, Read
---

# worktree-sweep

The decision whether a branch or worktree can go is the same every time for the same input, so it is computed, not judged. The script never deletes; git's own refusals (`git worktree remove` without `--force`, `git branch -d`) stay the last check when the user runs the commands.

## Steps

1. Be in the main checkout. If this session is isolated in a worktree, leave it first with `ExitWorktree` and `action: keep` (the worktree stays on disk); the script refuses to run from a linked worktree, because reading other worktrees from there would go around the isolation.
2. Run from the repository root:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/worktree_sweep.py"
   ```

   It fetches with `--prune`, fast-forwards the base branch when that loses nothing, and prints three groups. `--no-pull` leaves the base branch alone, `--no-gh` skips the pull request lookup, `--json` gives machine-readable output, `--target DIR` inspects another repository.
3. Show the report to the user as it is:
   - **delete**: merged into the base (an ancestor, or every patch already there per `git cherry`), and its worktree has nothing uncommitted, untracked or ignored. Give the commands; run them only when the user says so. A `git branch -D` line carries the `git cherry` proof.
   - **review**: give the reason and what the user needs to decide - the open PR, the commits not on the base (shown with their subjects and dates), the files left in the worktree. Ignored files matter because `git worktree remove` deletes them without asking.
   - **in-use**: leave alone; another session holds the lock, or the branch is checked out in the main checkout.
4. Never add `--force` to `git worktree remove`, and never turn a review item into a deletion on your own reading. If git refuses a command, report the refusal; it means the item was not what the report said.

## Notes

- `[gone]` means the remote branch was deleted, not that it was merged; the script does not count it as merged.
- Your own session's worktree shows as `in-use` while you are inside it and becomes `delete` once you leave it with `keep` (the lock is released).
