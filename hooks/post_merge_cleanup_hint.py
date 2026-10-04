#!/usr/bin/env python3
"""Cleanup hint after a merged PR (PostToolUse(Bash)).

After `gh pr merge` the same tidy-up follows every time: leave the worktree, bring the branch the PR
merged into up to date (the default branch, or the parent of a stacked worktree), remove what is
left. The `worktree-sweep` skill computes that, but nothing made the session call it,
and its listing does not come back after compaction. This hook creates the moment to call it.

Context only: it never runs the sweep (the session is usually inside a linked worktree, which the script
refuses, and the script fetches and fast-forwards, side effects a hook should not have) and it never
deletes anything. The decision to delete stays with the user.

Matching: the command is split with shlex into simple commands (at `;`, `&&`, `||`, `|`, `&`, newline), and
one of them must be `gh` [options] `pr` [options] `merge` (`gh pr merge 12 --merge`,
`gh -R owner/repo pr merge 12`), so `gh pr view 3; git merge x` does not match. `--auto` and
`--disable-auto` in that same command suppress the hint: nothing was merged. Success is not checked:
PostToolUse fires only for a command that exited 0; a failure goes to PostToolUseFailure. A merge queued
behind a merge queue or branch protection also exits 0, so the hint can come before the PR is merged. The
tool result is not read (its field name differs between sources).

Fail-open: malformed input, an unparsable command or any error exits 0 without output. Turn it off with the
official settings (`disableAllHooks`, or `enabledPlugins` for ccharness), as for the other hooks.
"""
from __future__ import annotations

import json
import shlex
import sys

HINT = (
    "ccharness: a PR was merged. The branch the PR merged into must be brought up to date where it is "
    "checked out, and the merged branch's worktree removed. Which step applies depends on where this "
    "session is: "
    "(a) in the worktree of the merged branch: check it for uncommitted or untracked files (move untracked "
    "work files to the main checkout before removal), leave it with ExitWorktree, action keep, then run the "
    "`worktree-sweep` skill from the main checkout. "
    "(b) in the worktree of the PR's base branch (a stacked worktree): run `git pull --ff-only` there; the "
    "merged branch's worktree is swept later from the main checkout. "
    "`worktree-sweep` (report only) also fast-forwards the PR's base branch where it is checked out, or "
    "prints the command when that worktree is in use by a live session. "
    "Run its delete-class commands only when the user says so; never add `--force` to "
    "`git worktree remove`."
)


SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&"}
VALUE_OPTIONS = {"-R", "--repo"}  # gh options whose value is the next word
NOT_MERGED_YET = {"--auto", "--auto=true", "--disable-auto", "--disable-auto=true"}


def split_segments(command: str) -> list[list[str]]:
    """Words of the command, one list per simple command (split at ; && || | & and newlines)."""
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    segments: list[list[str]] = [[]]
    for word in lexer:
        if word in SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(word)
    return segments


def segment_is_pr_merge(words: list[str]) -> bool:
    """`gh [options] pr [options] merge ...` as one command, without --auto / --disable-auto."""
    i = 0
    while i < len(words) and "=" in words[i] and not words[i].startswith("-"):
        i += 1  # leading VAR=value
    if i >= len(words) or words[i] != "gh":
        return False
    expected = ["pr", "merge"]
    k = i + 1
    while k < len(words):
        w = words[k]
        k += 1
        if w in VALUE_OPTIONS:
            k += 1  # skip the value
        elif w.startswith("-"):
            continue
        elif w != expected[0]:
            return False
        else:
            expected.pop(0)
            if not expected:
                return not any(a in NOT_MERGED_YET for a in words[k:])
    return False


def is_pr_merge(command: str) -> bool:
    try:
        segments = split_segments(command)
    except ValueError:
        return False
    return any(segment_is_pr_merge(s) for s in segments)


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
