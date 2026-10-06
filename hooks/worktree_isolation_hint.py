#!/usr/bin/env python3
"""Hints for a session isolated in a git worktree (PostToolUse(EnterWorktree), PostToolUseFailure(Bash)).

After EnterWorktree, Claude Code checks each Bash command's literal text and refuses a command it cannot show
stays inside the worktree. The check is not limited to commands that run git: in real sessions about half of
the refused commands ran no git at all. It refuses chains, heredocs, `python3 -c`, variables, loops and
`$(...)`, and it counts `git` inside other words (a `github.com` path) or inside quoted text, though a single
plain command with such a path passes. The refusal is about what the text proves, not what it does.
Sessions kept hitting it two or three times in a row with variations of the same form.

This hook does not predict the refusal (that check is Claude Code's own and changes with it; a guess here
would either block good commands or miss). It only adds context:

  * PostToolUse on EnterWorktree: once, the forms that pass and the forms that are refused.
  * PostToolUseFailure on Bash: when the error is the isolation refusal ("This session is isolated in the
    worktree"), the rewrite for that kind of refusal, so the second attempt is the right one. The rewrite is
    chosen from the words of the refusal and, when the input carries it, from the form of the command.

Fail-open: malformed input or any error exits 0 without output. Turn it off with the official settings
(`disableAllHooks`, or `enabledPlugins` for ccharness), as for the other hooks.
"""
from __future__ import annotations

import json
import re
import sys

REFUSAL = "this session is isolated in the worktree"

ON_ENTER = (
    "ccharness: this session is now isolated in a worktree. Claude Code checks each Bash command's text and "
    "refuses any command it cannot show stays inside the worktree, whether or not it runs git (in real "
    "sessions, about half of the refused commands ran none). Refused: chains (`&&`, `;`, `|`), a heredoc or "
    "`python3 -c`, a variable, loop or `$(...)` where an argument may stand (also `-C` and `cd` targets), "
    "`git -C` to the main checkout, and inline text that mentions git passed to `gh` or `tmux`. `git` inside "
    "another word counts too (a `github.com` path) once the command is not a single plain one. Passes: one "
    "plain command per call with literal paths; file edits with Edit/Write instead of sed; anything with "
    "several steps written with the Write tool to a script file and run as `python3 /abs/path.py`; "
    "`gh ... --body-file <file>`. For the main checkout or another repository, leave first (ExitWorktree, "
    "action keep)."
)

SCRIPT_FILE = (
    "Do not feed a script through a heredoc or `python3 -c`: write it with the Write tool to a file at an "
    "absolute path outside the repository, run `python3 /abs/path/to/x.py`, and delete the file when done."
)
LITERAL = (
    "Spell values out: replace variables, loops, `$(...)` and computed `-C` / `cd` targets with literal "
    "paths and values, one call per value. If many values are needed, put the loop in a script file."
)
EDIT_TOOL = "Edit file contents with the Edit tool instead of sed or awk."
LEAVE = (
    "Do not point git at another checkout with `-C`: run git in the worktree itself. For work in the main "
    "checkout or another repository, leave the worktree first (ExitWorktree, action keep)."
)
TEXT_FILE = (
    "Do not pass text that mentions git inline to gh or tmux: write it to a file and use `--body-file <file>` "
    "(or `-F <file>`) for gh; for tmux, put the call in a script file and run that."
)
SPLIT = (
    "Split it into plain commands, one per call: a chain (`&&`, `;`, `|`) is refused whether or not it runs "
    "git. Several steps belong in a script file written with the Write tool and run as `python3 /abs/x.py`. "
    "For diff or log output, write it to a file (`git diff --output=<file>`) and read the file in the next "
    "call. If the command touches another repository, even read-only, leave the worktree first (ExitWorktree, "
    "action keep), or check its state without git (`ls`, `gh api`)."
)
NO_GIT = (
    "Nothing in this command's text runs git, but the check refuses any command it cannot verify, and it "
    "counts `git` inside another word{where} or inside quoted text. Make it one plain command, or write the "
    "steps to a script file with the Write tool and run `python3 /abs/x.py`."
)

# (words from the refusal, rewrite), checked against refusals worded by Claude Code in real sessions.
# Every rewrite whose words match is given; SPLIT only when nothing matches the refusal or the command.
# All refusals end with "... must target its own worktree", so the words come from the part before that.
REWRITES = [
    (("feeds python text", "python text", "heredoc"), SCRIPT_FILE),
    (("computed at runtime",), LITERAL),
    (("runs sed", "runs awk"), EDIT_TOOL),
    (("shared checkout", "via -c"), LEAVE),
    (("runs gh with the text", "runs tmux with the text"), TEXT_FILE),
    (("too complex",), SPLIT),
]
GENERAL = SPLIT

_GIT_WORD = re.compile(r"(?<![\w./-])git(?![\w-])")
# `python3 -c ...` or a script on stdin (`python3 - <<EOF`).
_INLINE_SCRIPT = re.compile(r"\b(python3?|node|perl|ruby|bash|sh|zsh)\s+(-c\b|-(\s|$))")
# `$(...)`, `${...}`, `$NAME`, or `NAME=` at the start of a command (not `-f title=x` arguments).
_COMPUTED = re.compile(r"\$\(|\$\{|\$[A-Za-z_]|(^|[;&|(]\s*)[A-Za-z_][A-Za-z0-9_]*=")
_LOOP = re.compile(r"\b(for|while|until)\b[^\n]*\bdo\b")


def rewrites_for(error: str) -> list[str]:
    low = error.lower()
    return [text for words, text in REWRITES if any(w in low for w in words)]


def rewrites_for_command(command: str) -> list[str]:
    """Rewrites chosen from the form of the refused command itself."""
    tips = []
    if "<<" in command or _INLINE_SCRIPT.search(command):
        tips.append(SCRIPT_FILE)
    if _COMPUTED.search(command) or _LOOP.search(command):
        tips.append(LITERAL)
    if re.search(r"\b(gh|tmux)\b", command) and re.search(r"(['\"])[^'\"]*\bgit\b[^'\"]*\1", command):
        tips.append(TEXT_FILE)
    if not _GIT_WORD.search(command):
        where = " (here: `github.com` in a path)" if "github" in command.lower() else ""
        tips.append(NO_GIT.format(where=where))
    return tips


def context(event: str, payload: dict) -> str | None:
    tool = payload.get("tool_name")
    if event == "PostToolUse" and tool == "EnterWorktree":
        return ON_ENTER
    if event == "PostToolUseFailure" and tool == "Bash":
        error = str(payload.get("error") or "")
        if REFUSAL not in error.lower():
            return None
        tips = rewrites_for(error)
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if isinstance(command, str) and command.strip():
            tips += [t for t in rewrites_for_command(command) if t not in tips]
        tips = tips or [GENERAL]
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
