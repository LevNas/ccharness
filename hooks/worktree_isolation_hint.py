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

# Only so much of a command is scanned, so a huge one-line command cannot stall the hook.
_MAX_SCAN = 8000
# Something that may run git: `git`, `/usr/bin/git`, `git-lfs`, `gitk`, other git front ends, and gh
# subcommands that clone or check out. Errs towards "git": a false "git" only drops the no-git note, a
# false "no git" would tell the model something untrue. Not `.git`, `.gitignore`, `legit`, `digit`,
# `github`. Searched over the whole command (it is linear), and also with quotes and backslashes removed,
# so `gi''t` and `g\it` count.
_GIT_WORD = re.compile(r"(?<![\w.-])(?:git(?!hub)[\w-]*|lazygit|tig|glab)\b"
                       r"|\bgh\s+(?:pr\s+checkout|repo\s+(?:clone|sync|fork))\b")
# `python3 -c` / `python3 -` (a script on stdin), `node -e`, `perl -e`, `ruby -e`, `bash -c`.
_INLINE_SCRIPT = re.compile(r"\b(?:python3?\s+(?:-c\b|-(?:\s|$))|(?:node|perl|ruby)\s+-e\b|(?:ba|z)?sh\s+-c\b)")
_HEREDOC = re.compile(r"(?<!<)<<(?!<)")
# `$(...)`, `${...}`, `$NAME`, `$?`, `$1`, or `NAME=` at the start of a command (not `-f title=x`).
_COMPUTED = re.compile(r"\$[({A-Za-z_0-9?#@*!$]|(?:^|[;&|(\n])[ \t]*[A-Za-z_][A-Za-z0-9_]*=")
_LOOP_START = re.compile(r"\b(?:for|while|until)\b")
_LOOP_DO = re.compile(r"\bdo\b")
_SINGLE_QUOTED = re.compile(r"'[^']*'")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def rewrites_for(error: str) -> list[str]:
    low = error.lower()
    return [text for words, text in REWRITES if any(w in low for w in words)]


def _may_run_git(command: str) -> bool:
    return bool(_GIT_WORD.search(command) or _GIT_WORD.search(re.sub(r"['\"\\]", "", command)))


def rewrites_for_command(command: str) -> list[str]:
    """Rewrites chosen from the form of the refused command itself."""
    may_run_git = _may_run_git(command)  # over the whole command, before the cap
    command = command[:_MAX_SCAN]
    unquoted = _QUOTED.sub("''", command)  # text inside quotes is not shell syntax
    tips = []
    if _HEREDOC.search(unquoted) or _INLINE_SCRIPT.search(unquoted):
        tips.append(SCRIPT_FILE)
    # `$NF` in awk's single-quoted program is not a shell variable; double quotes do expand.
    if _COMPUTED.search(_SINGLE_QUOTED.sub("''", command)) or (
            _LOOP_START.search(unquoted) and _LOOP_DO.search(unquoted)):
        tips.append(LITERAL)
    if re.search(r"\b(?:gh|tmux)\b", unquoted) and any(
            _GIT_WORD.search(q) for q in _QUOTED.findall(command)):
        tips.append(TEXT_FILE)
    if not may_run_git:
        where = " (this command contains `github.com`)" if "github.com" in command.lower() else ""
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
            from_command = rewrites_for_command(command)
            if any(t.startswith("Nothing in this command") for t in from_command):
                # SPLIT speaks of git (diff output, other repositories); the no-git note replaces it.
                tips = [t for t in tips if t is not SPLIT]
            tips += [t for t in from_command if t not in tips]
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
