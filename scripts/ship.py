#!/usr/bin/env python3
"""ship.py - the mechanical steps after implementation: commit, push, check.

Every step here gives the same answer for the same input, so it is a script and
not a set of commands a model writes by hand. Python 3 standard library only;
every git/gh call is an argument list (no shell).

Subcommands
  commit --files F [F ...] --message-file M [--scan-patterns P]
      Refuses on the default branch and during a merge/rebase. Stages each
      listed path by name (never `git add -A` or `.`), requires the staged set
      to equal the listed set, scans the ADDED lines of the staged diff for
      secrets, then runs `git commit -F M`.
  push
      Refuses on the default branch. `git push -u origin <branch>`; never
      --force, never --no-verify, so a pre-push hook keeps running.
  check [--pr N] [--expect-files F ...] [--wait SECONDS]
      Read-only. Asks `gh pr view` and exits 0 only when the PR is open,
      mergeable, clean (or blocked only by being a draft), its head is the local
      HEAD and, when given, its files are the expected files. GitHub only; GitLab
      is not covered yet.

Exit codes: 0 ok; 1 a check or refusal stopped it (nothing hidden, nothing
forced); 2 usage or environment error (not a repository, `gh` missing, bad file).

This script does NOT create or post the pull request. A `gh pr create` inside a
script would hide its title and body from PreToolUse guards that check what gh
posts. Run `gh pr create --title ... --body-file <file>` as a plain command of
your own between `push` and `check`.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

BUILTIN_PATTERNS = [
    ("private-key-header", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}")),
    ("slack-token", re.compile(r"\bxox[abp]-[A-Za-z0-9-]{10,}")),
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("credential-assignment", re.compile(
        r"""(?i)(?:password|passwd|secret|token)\w*["']?\s*[=:]\s*(?:"[^"\n]{8,}"|'[^'\n]{8,}')""")),
]


class Stop(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


def run(argv, cwd=None):
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        raise Stop(f"{argv[0]}: command not found", 2)


def git(*args, cwd=None):
    return run(["git", *args], cwd=cwd)


def git_ok(*args, cwd=None):
    r = git(*args, cwd=cwd)
    if r.returncode:
        raise Stop(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def toplevel():
    r = git("rev-parse", "--show-toplevel")
    if r.returncode:
        raise Stop("not inside a git repository", 2)
    return r.stdout.strip()


def current_branch(top):
    r = git("symbolic-ref", "--short", "-q", "HEAD", cwd=top)
    if r.returncode:
        raise Stop("HEAD is detached; check out a branch first")
    return r.stdout.strip()


def default_branches(top):
    """Names that count as the default branch: origin/HEAD, else main and master."""
    r = git("symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD", cwd=top)
    if r.returncode == 0 and r.stdout.strip():
        return {r.stdout.strip().split("/", 1)[-1]}
    return {"main", "master"}


def refuse_default_branch(top):
    branch = current_branch(top)
    if branch in default_branches(top):
        raise Stop(f"refusing on the default branch '{branch}'; work on a feature branch")
    return branch


def operation_in_progress(top):
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        p = git_ok("rev-parse", "--git-path", name, cwd=top).strip()
        if not os.path.isabs(p):
            p = os.path.join(top, p)
        if os.path.exists(p):
            return name
    return None


def split_z(text):
    return {p for p in text.split("\0") if p}


def load_extra_patterns(path):
    extra = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise Stop(f"cannot read --scan-patterns {path}: {e}", 2)
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            extra.append((f"extra-pattern(line {n})", re.compile(line)))
        except re.error as e:
            raise Stop(f"--scan-patterns line {n} is not a valid regex: {e}", 2)
    return extra


def scan_staged(top, patterns):
    """Hits as (file, line number, pattern name); the matched text is never kept."""
    out = git_ok("diff", "--cached", "--no-renames", "--no-color", "-U0", cwd=top)
    hits, path, lineno = [], None, 0
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.match(r"@@ -\S+ \+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and path is not None:
            for name, rx in patterns:
                if rx.search(line[1:]):
                    hits.append((path, lineno, name))
            lineno += 1
    return hits


def cmd_commit(args):
    top = toplevel()
    refuse_default_branch(top)
    op = operation_in_progress(top)
    if op:
        raise Stop(f"a merge/rebase-like operation is in progress ({op}); finish or abort it first")
    if not os.path.isfile(args.message_file):
        raise Stop(f"message file not found: {args.message_file}", 2)
    message_file = os.path.abspath(args.message_file)
    extra = load_extra_patterns(args.scan_patterns) if args.scan_patterns else []

    listed = []
    for f in args.files:
        rel = os.path.relpath(os.path.abspath(f), top)
        if rel == "." or rel.startswith(".."):
            raise Stop(f"path is not a file inside the repository: {f}")
        listed.append(rel)
    for rel in listed:
        r = git("add", "--", rel, cwd=top)
        if r.returncode:
            raise Stop(f"git add -- {rel} failed: {r.stderr.strip()}")

    staged = split_z(git_ok("diff", "--cached", "--no-renames", "--name-only", "-z", cwd=top))
    want = set(listed)
    if staged != want:
        print("staged set differs from the listed set; nothing committed, nothing unstaged.")
        print("listed:  " + (", ".join(sorted(want)) or "(none)"))
        print("staged:  " + (", ".join(sorted(staged)) or "(none)"))
        print("only staged: " + (", ".join(sorted(staged - want)) or "(none)"))
        print("only listed: " + (", ".join(sorted(want - staged)) or "(none)"))
        return 1

    hits = scan_staged(top, BUILTIN_PATTERNS + extra)
    if hits:
        print("scan hit in added lines; nothing committed (the staged files stay staged):")
        for path, lineno, name in hits:
            print(f"  {path}:{lineno}: {name}")
        return 1

    r = git("commit", "-F", message_file, cwd=top)
    if r.returncode:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise Stop("git commit failed")
    print(f"committed {git_ok('rev-parse', '--short', 'HEAD', cwd=top).strip()}")
    return 0


def cmd_push(args):
    top = toplevel()
    branch = refuse_default_branch(top)
    r = git("push", "-u", "origin", branch, cwd=top)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode:
        raise Stop(f"git push failed for '{branch}'")
    print(f"pushed {branch} to origin")
    return 0


PR_FIELDS = "number,url,state,isDraft,mergeable,mergeStateStatus,baseRefName,headRefOid,files"


def pr_view(top, number):
    argv = ["gh", "pr", "view"] + ([str(number)] if number else []) + ["--json", PR_FIELDS]
    r = run(argv, cwd=top)
    if r.returncode:
        raise Stop(f"gh pr view failed: {r.stderr.strip()}", 2)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        raise Stop("gh pr view did not return JSON", 2)


def cmd_check(args):
    top = toplevel()
    deadline = time.monotonic() + max(args.wait, 0)
    while True:
        pr = pr_view(top, args.pr)
        if pr.get("mergeable") != "UNKNOWN" or time.monotonic() >= deadline:
            break
        time.sleep(args.poll_interval)

    head = git_ok("rev-parse", "HEAD", cwd=top).strip()
    problems = []
    state, mergeable = pr.get("state"), pr.get("mergeable")
    status, draft = pr.get("mergeStateStatus"), bool(pr.get("isDraft"))
    if state != "OPEN":
        problems.append(f"state {state}")
    if mergeable != "MERGEABLE":
        problems.append(f"mergeable {mergeable}")
    draft_only = draft and status in ("DRAFT", "BLOCKED")
    if status != "CLEAN" and not draft_only:
        problems.append(f"mergeStateStatus {status}")
    if pr.get("headRefOid") != head:
        problems.append(f"head {str(pr.get('headRefOid'))[:7]} != local {head[:7]}")
    if args.expect_files is not None:
        got = {f.get("path") for f in pr.get("files") or []}
        want = {os.path.relpath(os.path.abspath(f), top) for f in args.expect_files}
        if got != want:
            problems.append("files differ (only in PR: %s; only expected: %s)" % (
                ", ".join(sorted(got - want)) or "-", ", ".join(sorted(want - got)) or "-"))

    summary = (f"PR #{pr.get('number')} {pr.get('url')} {state}"
               f"{' draft' if draft else ''} {mergeable} {status} base={pr.get('baseRefName')}"
               f" head={str(pr.get('headRefOid'))[:7]}")
    if problems:
        print(f"NOT READY: {summary}; " + "; ".join(problems))
        return 1
    print(f"READY: {summary}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="commit, push and check a pull request (see module docstring)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("commit", help="stage listed files by name, scan, commit")
    c.add_argument("--files", nargs="+", required=True, metavar="F")
    c.add_argument("--message-file", required=True, metavar="M")
    c.add_argument("--scan-patterns", metavar="P", help="file of extra regexes, one per line, # comments")
    c.set_defaults(fn=cmd_commit)
    p = sub.add_parser("push", help="git push -u origin <current branch>")
    p.set_defaults(fn=cmd_push)
    k = sub.add_parser("check", help="read-only pull request check (GitHub only)")
    k.add_argument("--pr", type=int, metavar="N")
    k.add_argument("--expect-files", nargs="+", metavar="F")
    k.add_argument("--wait", type=float, default=30, metavar="SECONDS")
    k.add_argument("--poll-interval", type=float, default=2, help=argparse.SUPPRESS)
    k.set_defaults(fn=cmd_check)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except Stop as e:
        print(f"ship: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
