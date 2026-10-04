#!/usr/bin/env python3
"""Inventory the branches and worktrees left behind after work is merged. Report only.

Run from the main checkout (not a linked worktree):

    python3 scripts/worktree_sweep.py [--target DIR] [--json] [--no-fetch] [--no-pull] [--no-gh]

1. Sync: `git fetch origin --prune`, then fast-forward the base branch (origin/HEAD, else main)
   when the main checkout is on it, has no local commits and no tracked changes. A
   fast-forward loses nothing; anything else is reported, not forced.
   Then every linked worktree whose branch has an upstream (`<branch>@{u}`) that exists after
   the fetch is brought up to date the same way, in that worktree: behind, no commits of its
   own, no tracked changes, not locked by a live process -> `git merge --ff-only`. This is
   what a stacked worktree needs after its child's PR was merged into it. Locked by a live
   process: nothing is run, the command is printed. Ahead and behind, tracked changes, a
   failed fast-forward: a note. Branches without an upstream are skipped. `--no-pull` turns
   all of it into notes.
2. Classify every local branch and linked worktree against origin/<base>:
   - delete: merged (an ancestor, or every patch already there per `git cherry` and no merge
     commits of its own; or, for a stacked branch, its PR is MERGED into another branch whose
     origin/<branch> exists and contains it), and its worktree, if any, has no uncommitted,
     untracked or ignored files and is not in use. `git worktree remove` (no --force) and
     `git branch -d` are refused by git when that is not true; `git branch -D`, shown only with
     the cherry or parent-ancestor proof, is not, so that one rests on this script's check.
     If origin/<parent> is gone (the parent was merged and deleted too), the branch is compared
     with origin/<base> only; nothing is guessed.
   - review: needs a person — commits not on the base, an open PR, files left in the
     worktree (ignored ones too: `git worktree remove` deletes those silently), a stale lock.
   - in-use: locked by a live process, or checked out in the main checkout. Left alone.
   Protected branches (main, master, develop, release, the base) are skipped.

Nothing is deleted. `[gone]` (the remote branch was deleted) is not taken as merged.
Exit 0; exit 2 when run from a linked worktree or outside a repository.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys

PROTECTED = {"main", "master", "develop", "release"}
SHOW = 3  # paths or commits listed per reason


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C"))
    return r.returncode, r.stdout.rstrip("\n"), r.stderr.strip()


def out(cwd, *args):
    rc, stdout, _ = git(cwd, *args)
    return stdout if rc == 0 else None


def lines(text):
    return [l for l in (text or "").split("\n") if l]


# ------------------------------------------------------------------ discovery

def repo_top(target):
    top = out(target, "rev-parse", "--show-toplevel")
    if top is None:
        raise SystemExit(f"worktree-sweep: {target} is not inside a git repository")
    git_dir = out(top, "rev-parse", "--absolute-git-dir")
    common = out(top, "rev-parse", "--git-common-dir")
    common = os.path.realpath(os.path.join(top, common))
    if os.path.realpath(git_dir) != common:
        main = os.path.dirname(common) if os.path.basename(common) == ".git" else common
        print(f"worktree-sweep: {top} is a linked worktree. Run this from the main checkout "
              f"({main}); from a session isolated in a worktree, leave it first "
              "(ExitWorktree with keep).", file=sys.stderr)
        raise SystemExit(2)
    return top


def base_branch(top):
    head = out(top, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head and head.startswith("origin/"):
        return head[len("origin/"):], head
    for name in ("main", "master"):
        if out(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}"):
            return name, f"origin/{name}"
    for name in ("main", "master"):
        if out(top, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            return name, name  # no remote: compare with the local branch
    raise SystemExit("worktree-sweep: cannot find the base branch (origin/HEAD, main or master)")


def worktrees(top):
    """Linked worktrees as dicts; the first porcelain block is the main checkout."""
    blocks, cur = [], {}
    for line in (out(top, "worktree", "list", "--porcelain") or "").split("\n"):
        if not line:
            if cur:
                blocks.append(cur)
            cur = {}
            continue
        key, _, value = line.partition(" ")
        cur[key] = value
    if cur:
        blocks.append(cur)
    result = []
    for b in blocks[1:]:
        branch = b.get("branch", "")
        result.append({
            "path": b.get("worktree", ""),
            "branch": branch[len("refs/heads/"):] if branch.startswith("refs/heads/") else None,
            "head": b.get("HEAD", ""),
            "locked": b.get("locked"),  # None, "" (no reason) or the reason
            "prunable": "prunable" in b,
        })
    return result


def lock_pid(reason):
    """The pid Claude Code writes into its lock reason: `... (pid 123 start 456)`."""
    words = (reason or "").replace("(", " ").replace(")", " ").split()
    for k, w in enumerate(words[:-1]):
        if w == "pid" and words[k + 1].isdigit():
            return int(words[k + 1])
    return None


def alive(pid):
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OverflowError, ValueError):
        return False
    except PermissionError:
        return True
    return True


def open_pr(top, branch, use_gh):
    if not use_gh or not shutil.which("gh"):
        return None
    try:
        r = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "all", "--limit", "5",
                            "--json", "number,state,baseRefName"], cwd=top, capture_output=True, text=True,
                           timeout=20)
        prs = json.loads(r.stdout) if r.returncode == 0 else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    for state in ("OPEN", "MERGED"):
        for pr in prs:
            if pr.get("state") == state:
                return pr
    return prs[0] if prs else None


# ---------------------------------------------------------------------- sync

def sync(top, base, upstream, fetch, pull):
    notes = []
    if fetch and out(top, "remote", "get-url", "origin") is not None:
        rc, _, err = git(top, "fetch", "origin", "--prune")
        notes.append("fetched origin (pruned)" if rc == 0 else
                     f"fetch failed, so origin/* may be stale: {(err.splitlines() or [rc])[-1]}")
    notes += sync_base(top, base, upstream, pull)
    notes += sync_worktrees(top, pull)
    return notes


def sync_worktrees(top, pull):
    """Fast-forward each linked worktree's branch to its upstream, where that loses nothing."""
    notes = []
    for wt in worktrees(top):
        branch = wt["branch"]
        if not branch or wt["prunable"] or not os.path.isdir(wt["path"]):
            continue
        up = out(top, "rev-parse", "--abbrev-ref", f"{branch}@{{u}}")
        if not up or not out(top, "rev-parse", "--verify", "--quiet", f"{up}^{{commit}}"):
            continue  # no upstream, or it is gone
        behind = int(out(top, "rev-list", "--count", f"{branch}..{up}") or 0)
        if not behind:
            continue
        where = rel(top, wt["path"])
        ahead = int(out(top, "rev-list", "--count", f"{up}..{branch}") or 0)
        command = f"git -C {shlex.quote(where)} merge --ff-only {shlex.quote(up)}"
        pid = lock_pid(wt["locked"]) if wt["locked"] is not None else None
        rc, dirty, _ = git(wt["path"], "status", "--porcelain", "--untracked-files=no")
        if ahead:
            notes.append(f"{branch} in {where} has {ahead} local commit(s) and is {behind} behind "
                         f"{up}: not pulled (decide how to integrate)")
        elif pid is not None and alive(pid):
            notes.append(f"{branch} in {where} is {behind} behind {up} and in use (locked by "
                         f"process {pid}): not touched. Run `{command}`, or `git pull --ff-only` "
                         "from inside it")
        elif rc:
            notes.append(f"{branch} in {where} is {behind} behind {up}, but `git status` failed "
                         "there: not pulled")
        elif dirty:
            notes.append(f"{branch} in {where} is {behind} behind {up} but has tracked changes: "
                         "not pulled")
        elif not pull:
            notes.append(f"{branch} in {where} is {behind} behind {up} (--no-pull): "
                         f"run `{command}`")
        else:
            rc, _, err = git(wt["path"], "merge", "--ff-only", "--quiet", up)
            notes.append(f"{branch} fast-forwarded {behind} commit(s) in {where}" if rc == 0 else
                         f"{branch} in {where}: fast-forward to {up} failed: "
                         f"{err.splitlines()[-1] if err else rc}")
    return notes


def sync_base(top, base, upstream, pull):
    notes = []
    if upstream == base:
        return notes
    current = out(top, "symbolic-ref", "--short", "-q", "HEAD")
    if current != base:
        notes.append(f"main checkout is on {current or 'a detached HEAD'}, not {base}: "
                     f"local {base} not updated")
        return notes
    ahead = int(out(top, "rev-list", "--count", f"{upstream}..HEAD") or 0)
    behind = int(out(top, "rev-list", "--count", f"HEAD..{upstream}") or 0)
    if not behind:
        notes.append(f"{base} is up to date with {upstream}")
    elif ahead:
        notes.append(f"{base} has {ahead} local commit(s) and is {behind} behind {upstream}: "
                     "not pulled (decide how to integrate)")
    elif out(top, "status", "--porcelain", "--untracked-files=no"):
        notes.append(f"{base} is {behind} behind {upstream} but has tracked changes: not pulled")
    elif not pull:
        notes.append(f"{base} is {behind} behind {upstream} (--no-pull): "
                     "run `git pull --ff-only`")
    else:
        before = out(top, "rev-parse", "--short", "HEAD")
        rc, _, err = git(top, "merge", "--ff-only", "--quiet", upstream)
        after = out(top, "rev-parse", "--short", "HEAD")
        notes.append(f"{base} fast-forwarded {behind} commit(s) ({before}..{after})" if rc == 0
                     else f"{base} fast-forward failed: {err.splitlines()[-1] if err else rc}")
    return notes


# ------------------------------------------------------------------ classify

def worktree_state(wt):
    reasons = []
    if wt["prunable"] or not os.path.isdir(wt["path"]):
        return ["the worktree directory is missing: `git worktree prune` cleans the record"]
    rc, stdout, err = git(wt["path"], "status", "--porcelain", "--untracked-files=all")
    if rc:
        return [f"`git status` failed in the worktree, so its files could not be checked: {err}"]
    status = lines(stdout)
    if status:
        shown = ", ".join(s[3:] for s in status[:SHOW]) + (" ..." if len(status) > SHOW else "")
        reasons.append(f"{len(status)} uncommitted or untracked file(s): {shown}")
    rc, stdout, err = git(wt["path"], "status", "--porcelain", "--ignored", "--untracked-files=all")
    if rc:
        return reasons + [f"`git status --ignored` failed in the worktree: {err}"]
    ignored = [s[3:] for s in lines(stdout) if s.startswith("!! ")]
    if ignored:
        shown = ", ".join(ignored[:SHOW]) + (" ..." if len(ignored) > SHOW else "")
        reasons.append(f"{len(ignored)} ignored path(s), which `git worktree remove` deletes "
                       f"without asking: {shown}")
    return reasons


def merge_state(top, rev, upstream):
    """(merged, how, reasons) of a branch or commit against the base."""
    rc, _, err = git(top, "merge-base", "--is-ancestor", rev, upstream)
    if rc == 0:
        return True, "ancestor", []
    if rc != 1:
        return False, "", [f"could not compare with {upstream}: {err}"]
    cherry = lines(out(top, "cherry", upstream, rev))
    plus = [c[2:] for c in cherry if c.startswith("+ ")]
    merges = lines(out(top, "rev-list", "--merges", f"{upstream}..{rev}"))
    if cherry and not plus and merges:
        return False, "", [f"git cherry finds every patch in {upstream}, but the branch has "
                           f"{len(merges)} merge commit(s) of its own, which git cherry does not "
                           "compare (a conflict resolution would be lost by -D)"]
    if cherry and not plus:
        return True, f"cherry: all {len(cherry)} patch(es) already in {upstream}", []
    commits = lines(out(top, "log", "--format=%h %ad %s", "--date=short", f"{upstream}..{rev}"))
    shown = "; ".join(commits[:SHOW]) + (" ..." if len(commits) > SHOW else "")
    count = len(plus) if plus else len(commits)
    return False, "", [f"{count} commit(s) not in {upstream}: {shown}"]


def merged_into_parent(top, branch, upstream, pr):
    """`ancestor of origin/<parent> (PR #N base)` when the branch's PR was merged into a branch
    other than the base and origin/<parent> still exists and contains the branch; else None."""
    parent = pr.get("baseRefName")
    if pr.get("state") != "MERGED" or not parent or f"origin/{parent}" == upstream:
        return None
    ref = f"origin/{parent}"
    if not out(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/{ref}"):
        return None  # the parent is gone too: fall back to the base comparison, do not guess
    if git(top, "merge-base", "--is-ancestor", branch, ref)[0] != 0:
        return None
    return f"ancestor of {ref} (PR #{pr['number']} base)"


def rel(top, path):
    r = os.path.relpath(path, top)
    return path if r.startswith("..") else r


def classify(top, base, upstream, use_gh):
    current = out(top, "symbolic-ref", "--short", "-q", "HEAD")
    wts = worktrees(top)
    by_branch = {w["branch"]: w for w in wts if w["branch"]}
    refs = lines(out(top, "for-each-ref", "--format=%(refname:lstrip=2)%09%(upstream:track)%09"
                     "%(committerdate:short)", "refs/heads"))
    items = []
    for row in refs:
        branch, track, date = (row.split("\t") + ["", ""])[:3]
        if branch in PROTECTED or branch == base:
            continue
        items.append(item(top, upstream, branch, track, date, by_branch.get(branch), current,
                          use_gh))
    for wt in wts:
        if not wt["branch"]:  # detached HEAD
            items.append(item(top, upstream, None, "", "", wt, current, use_gh))
    return items


def item(top, upstream, branch, track, date, wt, current, use_gh):
    it = {"branch": branch, "worktree": rel(top, wt["path"]) if wt else None,
          "upstream": track or None, "last_commit": date or None, "pr": None,
          "class": None, "merged": None, "reasons": [], "notes": [], "commands": []}
    if branch and branch == current:
        it.update({"class": "in-use", "reasons": ["checked out in the main checkout"]})
        return it
    if wt and wt["locked"] is not None:
        pid = lock_pid(wt["locked"])
        if pid is not None and alive(pid):
            it.update({"class": "in-use", "reasons": [f"locked by running process {pid}"]})
            return it
        it["reasons"].append(f"stale lock (pid {pid} is not running): `git worktree unlock` "
                             "after checking" if pid is not None
                             else f"locked ({wt['locked'] or 'no reason'})")
    merged, how, reasons = merge_state(top, branch or wt["head"], upstream)
    pr = open_pr(top, branch, use_gh) if branch else None
    parent_proof = False
    if not merged and pr:
        proof = merged_into_parent(top, branch, upstream, pr)
        if proof:
            merged, how, reasons, parent_proof = True, proof, [], True
    it["merged"] = how or False
    it["reasons"] += reasons
    if pr:
        it["pr"] = f"#{pr['number']} {pr['state']}"
        if pr["state"] == "OPEN":
            it["reasons"].append(f"PR #{pr['number']} is open")
    if wt:
        it["reasons"] += worktree_state(wt)
    if it["reasons"]:
        it["class"] = "review"
        return it
    it["class"] = "delete"
    if wt:
        it["commands"].append(f"git worktree remove {shlex.quote(it['worktree'])}")
    if branch:
        if parent_proof:
            it["commands"].append(f"git branch -D {shlex.quote(branch)}  # {how.split(' (')[0]}; "
                                  "-d compares with HEAD or a gone upstream and refuses")
        elif how != "ancestor":
            it["commands"].append(f"git branch -D {shlex.quote(branch)}  # {how}; git does not "
                                  "check -D")
        else:
            it["commands"].append(f"git branch -d {shlex.quote(branch)}")
            if git(top, "merge-base", "--is-ancestor", branch, "HEAD")[0] != 0:
                it["notes"].append(f"`git branch -d` compares with the main checkout's HEAD, which "
                                   f"does not contain this branch yet: update the base from "
                                   f"{upstream} first, or git refuses")
    return it


# -------------------------------------------------------------------- report

TITLES = {"delete": "delete — merged, nothing left behind",
          "review": "review — needs your decision",
          "in-use": "in-use — left alone"}


def report(top, upstream, notes, items):
    print(f"worktree-sweep: {top} (base {upstream})")
    for n in notes:
        print(f"  sync: {n}")
    if not items:
        print("\nnothing to sweep")
    for cls in ("delete", "review", "in-use"):
        group = [i for i in items if i["class"] == cls]
        if not group:
            continue
        print(f"\n{TITLES[cls]} ({len(group)})")
        for i in group:
            label = i["branch"] or "(detached)"
            extra = [x for x in (f"[{i['worktree']}]" if i["worktree"] else "",
                                 i["upstream"] or "", f"PR {i['pr']}" if i["pr"] else "",
                                 i["last_commit"] or "") if x]
            print(f"  {label}  {' '.join(extra)}")
            if i["merged"]:
                print(f"      merged: {i['merged']}")
            for r in i["reasons"]:
                print(f"      - {r}")
            for n in i["notes"]:
                print(f"      note: {n}")
            for c in i["commands"]:
                print(f"      $ {c}")
    print("\nnothing was deleted")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", default=".", help="repository (main checkout) to inspect")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-fetch", action="store_true", help="skip `git fetch origin --prune`")
    ap.add_argument("--no-pull", action="store_true", help="do not fast-forward the base branch")
    ap.add_argument("--no-gh", action="store_true", help="do not look up pull requests with gh")
    args = ap.parse_args()

    top = repo_top(os.path.abspath(args.target))
    base, upstream = base_branch(top)
    notes = sync(top, base, upstream, not args.no_fetch, not args.no_pull)
    items = classify(top, base, upstream, not args.no_gh)
    if args.json:
        json.dump({"repository": top, "base": upstream, "sync": notes, "items": items},
                  sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        report(top, upstream, notes, items)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            sys.exit(2)
        raise
