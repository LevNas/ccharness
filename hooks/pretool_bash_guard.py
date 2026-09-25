#!/usr/bin/env python3
"""PreToolUse(Bash) guard: the hard-deny floor only.

Everything that Claude Code's own permission rules can express lives in
`permissions.deny` (see templates/settings.snippet.json), which the official
engine matches per subcommand, inside `$()` and loops, after stripping wrappers
and leading variable assignments. This hook keeps only what a deny rule cannot
express, as the permissions reference itself recommends ("To inspect the full
command text with your own logic before it runs, use a PreToolUse hook"):

  * `rm -r` whose target is the root, the home directory, the current or parent
    directory, or a bare glob: needs target analysis, not a prefix.
  * The same programs invoked as `/bin/rm`, `sudo rm`, `xargs rm` or inside
    `bash -c '...'`, which a `Bash(rm *)` rule does not match.
  * Fork bombs, `mkfs`, `dd`/redirects onto a block device, `shred`: matched on
    the raw text so a wrapper or path prefix cannot hide them.

Ownership stays disjoint with ccguard (secret exfiltration, AI attribution in
commits, self-modification of .claude/), which judges the same tool call from
its own hook.

Protocol (same as ccguard): tool input JSON on stdin; exit 2 with a reason on
stderr to deny; exit 0 to allow. Malformed input is allowed.

Turning it off uses official settings, not a custom switch: `disableAllHooks`
in any settings file, `--settings '{"disableAllHooks": true}'` for one run, or
`"enabledPlugins": {"ccharness@levnas-plugins": false}` in a project's
`.claude/settings.json`.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from typing import Optional

BLOCK_DEVICE = r"/dev/(sd|nvme|hd|vd|disk|mmcblk|xvd)"

FLOOR = [
    (re.compile(r"(^|[\s;]):\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;"), "fork bomb"),
    (re.compile(r"(^|[\s;&|/])mkfs(\.\w+)?\b"), "mkfs formats a filesystem"),
    (re.compile(r"(^|[\s;&|/])dd\b[^|;&]*\bof=" + BLOCK_DEVICE), "dd writes to a block device"),
    (re.compile(r">\s*" + BLOCK_DEVICE), "redirect writes to a block device"),
    (re.compile(r"(^|[\s;&|/])shred\b"), "shred destroys file contents"),
]

OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}
PREFIXES = {"sudo", "doas", "env", "nice", "time", "command", "builtin", "exec", "nohup", "xargs", "timeout", "stdbuf"}
PREFIX_OPTS_WITH_ARG = {"-u", "-g", "-C", "-n", "-o", "-e", "-i"}  # sudo -u USER, nice -n N, stdbuf -oL, ...
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
DANGEROUS_RM_TARGETS = {"/", "/*", "~", "~/", "~/*", "$HOME", "${HOME}", "$HOME/", "${HOME}/",
                        "$HOME/*", "${HOME}/*", ".", "./", "./*", "..", "../", "../*", "*", ":/"}


def _split_segments(tokens: list[str]) -> list[list[str]]:
    segs: list[list[str]] = [[]]
    for tok in tokens:
        if tok in OPERATORS:
            if segs[-1]:
                segs.append([])
        else:
            segs[-1].append(tok)
    return [s for s in segs if s]


def _strip_prefixes(seg: list[str]) -> list[str]:
    i = 0
    while i < len(seg):
        tok = seg[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            i += 1
            continue
        if os.path.basename(tok) in PREFIXES:
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                if seg[i] in PREFIX_OPTS_WITH_ARG:
                    i += 1
                i += 1
            continue
        break
    return seg[i:]


def _short_flags(tok: str) -> str:
    return tok[1:] if tok.startswith("-") and not tok.startswith("--") and len(tok) > 1 else ""


def _rm_reason(args: list[str]) -> Optional[str]:
    recursive = any("r" in _short_flags(t) or "R" in _short_flags(t) or t == "--recursive" for t in args)
    if not recursive:
        return None
    if "--no-preserve-root" in args:
        return "rm --no-preserve-root"
    for t in args:
        if t.startswith("-") and t != "-":
            continue
        if t in DANGEROUS_RM_TARGETS:
            return f"rm -r on {t!r}"
        if t.startswith("/"):
            parts = [p for p in t.rstrip("*").split("/") if p]
            if len(parts) <= 1 or (parts[0] == "home" and len(parts) <= 2):
                return f"rm -r on top-level path {t!r}"
    return None


def _segment_reason(seg: list[str], depth: int) -> Optional[str]:
    seg = _strip_prefixes(seg)
    for idx, tok in enumerate(seg):
        name = os.path.basename(tok)
        if name == "rm":
            r = _rm_reason(seg[idx + 1:])
            if r:
                return r
        elif name in SHELLS and depth < 3:
            # bash -c '<script>': judge the embedded script as a command of its own.
            rest = seg[idx + 1:]
            for j, t in enumerate(rest):
                if t in {"-c", "-lc", "-ic"} and j + 1 < len(rest):
                    r = judge(rest[j + 1], depth + 1)
                    if r:
                        return r
    return None


def _tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def judge(command: str, depth: int = 0) -> Optional[str]:
    """Return a block reason, or None when the command passes the floor."""
    if not command or not command.strip():
        return None
    for pat, why in FLOOR:
        if pat.search(command):
            return why
    try:
        tokens = _tokenize(command)
    except ValueError:
        tokens = []
    for seg in _split_segments(tokens):
        r = _segment_reason(seg, depth)
        if r:
            return r
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict) or data.get("tool_name", "Bash") != "Bash":
        return 0
    command = (data.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str):
        return 0
    reason = judge(command)
    if reason is None:
        return 0
    sys.stderr.write(
        "BLOCKED by ccharness bash guard (hard-deny floor): " + reason + ". "
        "This is never run from an agent session. If it is really intended, ask the user to run it "
        "manually; the guard is disabled only through settings (disableAllHooks or enabledPlugins).\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
