#!/usr/bin/env python3
"""Hints for a session isolated in a git worktree (PostToolUse(EnterWorktree), PostToolUseFailure(Bash)).

After EnterWorktree, Claude Code checks each Bash command's literal text and refuses git it cannot show
stays inside the worktree: a heredoc or `python3 -c` whose text names git, a variable where an option may
stand, a loop, a long chain. The command may be harmless; the refusal is about what the text proves.
Sessions kept hitting it two or three times in a row with variations of the same form.

This hook does not predict the refusal (that check is Claude Code's own and changes with it; a guess here
would either block good commands or miss). It only adds context:

  * PostToolUse on EnterWorktree: once, the forms that pass and the forms that are refused.
  * PostToolUseFailure on Bash: when the error is the isolation refusal ("This session is isolated in the
    worktree"), the rewrite for that kind of refusal, so the second attempt is the right one.

Fail-open: malformed input or any error exits 0 without output. Turn it off with the official settings
(`disableAllHooks`, or `enabledPlugins` for ccharness), as for the other hooks.
"""
from __future__ import annotations

import json
import sys

REFUSAL = "this session is isolated in the worktree"

ON_ENTER = (
    "ccharness: this session is now isolated in a worktree. Claude Code checks each Bash command's text and "
    "refuses git it cannot show stays inside the worktree, even when the command is harmless. Refused: a "
    "heredoc or `python3 -c` whose text mentions git; a variable, loop or `$(...)` where an argument may "
    "stand (also `-C` and `cd` targets); `git -C` to the main checkout; long `&&` / `|` chains with git; "
    "`gh` with inline text that mentions git. Passes: one plain git command per call, run in the worktree, "
    "with literal paths; file edits with Edit/Write instead of sed; a script written to a file and run as "
    "`python3 /abs/path.py`; `gh ... --body-file <file>`. For the main checkout or another repository, "
    "leave first (ExitWorktree, action keep)."
)

# (words from the refusal, rewrite), checked against refusals worded by Claude Code in real sessions.
# Every rewrite whose words match is given; GENERAL only when none does. All refusals end with
# "... must target its own worktree", so the words come from the part before that.
REWRITES = [
    (("feeds python text", "python text", "heredoc"),
     "Do not feed a script through a heredoc or `python3 -c`: write it with the Write tool to a file at an "
     "absolute path outside the repository, run `python3 /abs/path/to/x.py`, and delete the file when done."),
    (("computed at runtime",),
     "Spell values out: replace variables, loops, `$(...)` and computed `-C` / `cd` targets with literal "
     "paths and values, one call per value. If many values are needed, put the loop in a script file."),
    (("runs sed", "runs awk"),
     "Edit file contents with the Edit tool instead of sed or awk."),
    (("shared checkout", "via -c"),
     "Do not point git at another checkout with `-C`: run git in the worktree itself. For work in the main "
     "checkout or another repository, leave the worktree first (ExitWorktree, action keep)."),
    (("runs gh with the text",),
     "Do not pass text that mentions git inline to gh: write it to a file and use `--body-file <file>` "
     "(or `-F <file>`)."),
    (("too complex",),
     "Split the command: one git command per call, no `&&`, `;` or `|` around it. For diff or log output, "
     "write it to a file (`git diff --output=<file>`) and read the file in the next call. If the command "
     "touches another repository, even read-only, leave the worktree first (ExitWorktree, action keep), or "
     "check its state without git (`ls`, `gh api`)."),
]
GENERAL = REWRITES[-1][1]


def rewrites_for(error: str) -> list[str]:
    low = error.lower()
    return [text for words, text in REWRITES if any(w in low for w in words)]


def context(event: str, payload: dict) -> str | None:
    tool = payload.get("tool_name")
    if event == "PostToolUse" and tool == "EnterWorktree":
        return ON_ENTER
    if event == "PostToolUseFailure" and tool == "Bash":
        error = str(payload.get("error") or "")
        if REFUSAL not in error.lower():
            return None
        tips = rewrites_for(error) or [GENERAL]
        return ("ccharness: the worktree isolation check refused this command because of its form, not what "
                "it does. Do not retry a variation of the same form. " + " ".join(tips))
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        event = payload.get("hook_event_name") or ""
        text = context(event, payload)
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))
    except Exception:  # fail-open: a hint must never get in the way
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
