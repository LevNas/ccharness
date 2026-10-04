#!/usr/bin/env python3
"""Cleanup hint after a merged PR (PostToolUse(Bash)).

After `gh pr merge` the same tidy-up follows every time: leave the worktree, bring the base branch up to
date, remove what is left. The `worktree-sweep` skill computes that, but nothing made the session call it,
and its listing does not come back after compaction. This hook creates the moment to call it.

Context only: it never runs the sweep (the session is usually inside a linked worktree, which the script
refuses, and the script fetches and fast-forwards, side effects a hook should not have) and it never
deletes anything. The decision to delete stays with the user.

Matching: the command, split into words with shlex, contains `gh` ... `pr` ... `merge` in that order
(`gh pr merge 12 --merge`, `gh -R owner/repo pr merge 12`). `--auto` suppresses the hint: the PR is not
merged yet. Success is not checked: PostToolUse fires only for a command that exited 0; a failure goes to
PostToolUseFailure. The tool result is not read (its field name differs between sources).

Fail-open: malformed input, an unparsable command or any error exits 0 without output. Turn it off with the
official settings (`disableAllHooks`, or `enabledPlugins` for ccharness), as for the other hooks.
"""
from __future__ import annotations

import json
import shlex
import sys

HINT = (
    "ccharness: a PR was merged. Clean up in this order. "
    "1. If the session is in a worktree, check it for uncommitted or untracked files (move work files such "
    "as session captures to the main checkout before removal). "
    "2. Leave the worktree with ExitWorktree, action keep. "
    "3. From the main checkout, run the `worktree-sweep` skill (report only). "
    "4. Run its delete-class commands only when the user says so; never add `--force` to "
    "`git worktree remove`."
)


def is_pr_merge(command: str) -> bool:
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    if "--auto" in words:
        return False
    state = 0
    for w in words:
        if state == 0 and w == "gh":
            state = 1
        elif state == 1 and w == "pr":
            state = 2
        elif state == 2 and w == "merge":
            return True
    return False


def context(payload: dict) -> str | None:
    if payload.get("hook_event_name") != "PostToolUse" or payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(command, str) and is_pr_merge(command):
        return HINT
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        text = context(payload)
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
    except Exception:  # fail-open: a hint must never get in the way
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
