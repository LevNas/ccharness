#!/usr/bin/env python3
"""Tests for scripts/worktree_sweep.py against real repositories. Run: python3 tests/test_worktree_sweep.py"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "worktree_sweep.py")
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
FAILURES = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)
        print(f"     {detail!r}"[:400])


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def commit(cwd, name, text="x\n"):
    with open(os.path.join(cwd, name), "w", encoding="utf-8") as f:
        f.write(text)
    git(cwd, "add", name)
    git(cwd, "commit", "-qm", f"add {name}")
    return git(cwd, "rev-parse", "HEAD")


def merged_branch(work, name, wt=None):
    """A branch with one commit, merged into main with --no-ff and pushed."""
    if wt:
        git(work, "worktree", "add", "-q", wt, "-b", name)
        commit(wt, f"{name}.txt")
    else:
        git(work, "switch", "-qc", name)
        commit(work, f"{name}.txt")
        git(work, "switch", "-q", "main")
    git(work, "merge", "-q", "--no-ff", "-m", f"merge {name}", name)
    git(work, "push", "-q", "origin", "main")


def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def snapshot(work):
    return (git(work, "for-each-ref", "--format=%(refname)", "refs/heads"),
            [l for l in git(work, "worktree", "list", "--porcelain").split("\n")
             if l.startswith("worktree ")])


def run(cwd, *args):
    return subprocess.run([sys.executable, SCRIPT, "--no-gh", *args], cwd=cwd,
                          capture_output=True, text=True, env=ENV)


def build(base):
    remote, work, other = (os.path.join(base, n) for n in ("remote.git", "work", "other"))
    git(base, "init", "-q", "--bare", "-b", "main", remote)
    git(base, "clone", "-q", remote, work)
    git(work, "switch", "-qc", "main")
    with open(os.path.join(work, ".gitignore"), "w", encoding="utf-8") as f:
        f.write("private/\n")
    git(work, "add", ".gitignore")
    git(work, "commit", "-qm", "init")
    git(work, "push", "-q", "-u", "origin", "main")
    git(work, "remote", "set-head", "origin", "main")
    wt = lambda n: os.path.join(base, "wt", n)  # noqa: E731

    merged_branch(work, "merged-plain")
    merged_branch(work, "merged-wt", wt("merged-wt"))
    merged_branch(work, "dirty-wt", wt("dirty-wt"))
    with open(os.path.join(wt("dirty-wt"), "notes.md"), "w", encoding="utf-8") as f:
        f.write("left behind\n")
    merged_branch(work, "ignored-wt", wt("ignored-wt"))
    os.makedirs(os.path.join(wt("ignored-wt"), "private"))
    with open(os.path.join(wt("ignored-wt"), "private", "key.txt"), "w", encoding="utf-8") as f:
        f.write("local only\n")

    # Same patch on main under another commit (cherry-pick): not an ancestor, cherry says "-".
    git(work, "switch", "-qc", "picked")
    sha = commit(work, "picked.txt")
    git(work, "switch", "-q", "main")
    commit(work, "between.txt")  # another parent, so the picked commit gets a new id
    git(work, "cherry-pick", sha)
    git(work, "push", "-q", "origin", "main")

    git(work, "switch", "-qc", "unmerged")
    commit(work, "unmerged.txt")
    git(work, "switch", "-q", "main")

    # [gone]: pushed, then deleted on the remote, never merged.
    git(work, "switch", "-qc", "gone-unmerged")
    commit(work, "gone.txt")
    git(work, "push", "-q", "-u", "origin", "gone-unmerged")
    git(work, "switch", "-q", "main")
    git(work, "push", "-q", "origin", "--delete", "gone-unmerged")

    # Every patch is on main, but the branch also has a merge commit of its own.
    git(work, "switch", "-qc", "with-merge")
    sha = commit(work, "with-merge.txt")
    git(work, "switch", "-q", "main")
    commit(work, "main-side.txt")
    git(work, "push", "-q", "origin", "main")
    git(work, "switch", "-q", "with-merge")
    git(work, "merge", "-q", "--no-ff", "-m", "update from main", "main")
    git(work, "switch", "-q", "main")
    git(work, "cherry-pick", sha)
    git(work, "push", "-q", "origin", "main")

    # A worktree whose `git status` fails.
    merged_branch(work, "broken-wt", wt("broken-wt"))
    with open(os.path.join(wt("broken-wt"), ".git"), "w", encoding="utf-8") as f:
        f.write("gitdir: /nonexistent/broken\n")

    # A detached worktree on a merged commit, and a worktree path with a space.
    git(work, "worktree", "add", "-q", "--detach", wt("detached"), "HEAD")
    merged_branch(work, "spaced-wt", wt("with space"))
    # A tag with the same name as a branch that has a worktree.
    git(work, "tag", "merged-wt")

    merged_branch(work, "locked-live", wt("locked-live"))
    git(work, "worktree", "lock", "--reason", f"claude session x (pid {os.getpid()} start 1)",
        wt("locked-live"))
    merged_branch(work, "locked-dead", wt("locked-dead"))
    git(work, "worktree", "lock", "--reason", f"claude session y (pid {dead_pid()} start 1)",
        wt("locked-dead"))

    # Someone else moves main: the main checkout falls behind. A branch merged there exists
    # locally but is not in the main checkout's HEAD until the fast-forward.
    git(base, "clone", "-q", remote, other)
    git(other, "switch", "-qc", "remote-merged")
    commit(other, "remote-merged.txt")
    git(other, "push", "-q", "origin", "remote-merged")
    git(other, "switch", "-q", "main")
    git(other, "merge", "-q", "--no-ff", "-m", "merge remote-merged", "remote-merged")
    commit(other, "upstream.txt")
    git(other, "push", "-q", "origin", "main")
    git(work, "fetch", "-q", "origin", "remote-merged:remote-merged")
    return work, wt


def main():
    with tempfile.TemporaryDirectory() as base:
        work, wt = build(base)
        before = snapshot(work)
        head_before = git(work, "rev-parse", "HEAD")

        r = run(work, "--json", "--no-pull")
        early = {i["branch"]: i for i in json.loads(r.stdout)["items"]}
        check("--no-pull leaves main alone", git(work, "rev-parse", "HEAD") == head_before)
        check("-d note when the main checkout's HEAD lacks the branch",
              early.get("remote-merged", {}).get("class") == "delete"
              and any("does not contain this branch" in n for n in early["remote-merged"]["notes"]),
              early.get("remote-merged"))

        r = run(work, "--json")
        check("json run exits 0", r.returncode == 0, r.stderr)
        data = json.loads(r.stdout)
        by = {i["branch"]: i for i in data["items"]}
        cls = lambda b: by.get(b, {}).get("class")  # noqa: E731
        reasons = lambda b: " | ".join(by.get(b, {}).get("reasons", []))  # noqa: E731

        check("base is origin/main", data["base"] == "origin/main", data["base"])
        check("main fast-forwarded", git(work, "rev-parse", "HEAD") == git(work, "rev-parse", "origin/main")
              and git(work, "rev-parse", "HEAD") != head_before, data["sync"])
        check("sync note says fast-forwarded", any("fast-forwarded 3" in n for n in data["sync"]),
              data["sync"])
        check("main is not listed", "main" not in by, list(by))

        check("merged, no worktree: delete with -d", cls("merged-plain") == "delete"
              and by["merged-plain"]["commands"] == ["git branch -d merged-plain"], by.get("merged-plain"))
        check("merged, clean worktree: delete with remove + -d", cls("merged-wt") == "delete"
              and by["merged-wt"]["commands"][0].startswith("git worktree remove ")
              and "--force" not in " ".join(by["merged-wt"]["commands"])
              and by["merged-wt"]["commands"][1] == "git branch -d merged-wt", by.get("merged-wt"))
        check("untracked file in worktree: review", cls("dirty-wt") == "review"
              and "notes.md" in reasons("dirty-wt"), by.get("dirty-wt"))
        check("ignored file in worktree: review", cls("ignored-wt") == "review"
              and "ignored" in reasons("ignored-wt") and "private/" in reasons("ignored-wt"),
              by.get("ignored-wt"))
        check("same patch already on main: delete with -D and the cherry proof",
              cls("picked") == "delete" and by["picked"]["commands"][0].startswith("git branch -D picked")
              and "cherry" in by["picked"]["commands"][0], by.get("picked"))
        check("unmerged: review with the commit", cls("unmerged") == "review"
              and "1 commit(s) not in origin/main" in reasons("unmerged")
              and "add unmerged.txt" in reasons("unmerged"), by.get("unmerged"))
        check("[gone] but unmerged: review, not delete", cls("gone-unmerged") == "review"
              and by["gone-unmerged"]["upstream"] == "[gone]", by.get("gone-unmerged"))
        check("locked by a live process: in-use", cls("locked-live") == "in-use", by.get("locked-live"))
        check("locked by a dead process: review (stale lock)", cls("locked-dead") == "review"
              and "stale lock" in reasons("locked-dead"), by.get("locked-dead"))
        check("own merge commit: review even though cherry is all '-'",
              cls("with-merge") == "review" and "merge commit" in reasons("with-merge"),
              by.get("with-merge"))
        check("git status failing in a worktree: review, not delete", cls("broken-wt") == "review"
              and "git status" in reasons("broken-wt"), by.get("broken-wt"))
        detached = [i for i in data["items"] if i["branch"] is None]
        check("detached merged worktree: delete with remove only", len(detached) == 1
              and detached[0]["class"] == "delete" and len(detached[0]["commands"]) == 1
              and detached[0]["commands"][0].startswith("git worktree remove"), detached)
        check("path with a space is quoted", cls("spaced-wt") == "delete"
              and "'" in by["spaced-wt"]["commands"][0] and "with space'" in by["spaced-wt"]["commands"][0],
              by.get("spaced-wt"))
        check("tag with the branch's name: worktree still found",
              by.get("merged-wt", {}).get("worktree") is not None, by.get("merged-wt"))
        check("-D carries the cherry proof and says git does not check it",
              "git does not check -D" in by["picked"]["commands"][0], by.get("picked"))
        check("no note once main has the branch", cls("remote-merged") == "delete"
              and not by["remote-merged"]["notes"], by.get("remote-merged"))
        check("review items carry no commands",
              all(not i["commands"] for i in data["items"] if i["class"] != "delete"))

        check("nothing was deleted", snapshot(work) == before, (snapshot(work), before))

        r = run(work, "--no-fetch")
        check("text report runs", r.returncode == 0 and "nothing was deleted" in r.stdout, r.stderr)
        check("text report groups", all(t in r.stdout for t in ("delete —", "review —", "in-use —")),
              r.stdout[:300])

        r = run(wt("merged-wt"))
        check("refuses from a linked worktree (exit 2)", r.returncode == 2
              and "linked worktree" in r.stderr, (r.returncode, r.stderr))
        check("still nothing deleted", snapshot(work) == before)

        # master as the base, no remote at all.
        solo = os.path.join(base, "solo")
        git(base, "init", "-q", "-b", "master", solo)
        commit(solo, "a.txt")
        git(solo, "switch", "-qc", "done")
        commit(solo, "b.txt")
        git(solo, "switch", "-q", "master")
        git(solo, "merge", "-q", "--no-ff", "-m", "merge done", "done")
        r = run(solo, "--json")
        d = json.loads(r.stdout) if r.returncode == 0 else {}
        check("no origin, master base: compares with local master", d.get("base") == "master"
              and [i["class"] for i in d.get("items", [])] == ["delete"], (r.returncode, r.stderr, d))

        os.makedirs(os.path.join(base, "plain"))
        r = run(os.path.join(base, "plain"))
        check("outside a repository: exit 2", r.returncode == 2, (r.returncode, r.stderr))

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
