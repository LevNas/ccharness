#!/usr/bin/env python3
"""Tests for the stacked-worktree parts of scripts/worktree_sweep.py: parent worktrees brought up to
date, and a branch merged into a non-default base. Temporary repositories only (bare origin, clones,
`git worktree add`). Run: python3 -m unittest discover -s tests"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "worktree_sweep.py")
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")

spec = importlib.util.spec_from_file_location("worktree_sweep", SCRIPT)
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


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


def sweep(cwd, *args):
    r = subprocess.run([sys.executable, SCRIPT, "--no-gh", *args], cwd=cwd, capture_output=True,
                       text=True, env=ENV)
    assert r.returncode == 0, r.stderr
    return r.stdout


class Repo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = self._tmp.name
        self.remote = os.path.join(self.base, "remote.git")
        self.work = os.path.join(self.base, "work")
        self.other = os.path.join(self.base, "other")
        git(self.base, "init", "-q", "--bare", "-b", "main", self.remote)
        git(self.base, "clone", "-q", self.remote, self.work)
        git(self.work, "switch", "-qc", "main")
        commit(self.work, "init.txt")
        git(self.work, "push", "-q", "-u", "origin", "main")
        git(self.work, "remote", "set-head", "origin", "main")
        git(self.base, "clone", "-q", self.remote, self.other)

    def wt(self, name):
        return os.path.join(self.base, "wt", name)

    def stacked(self, name, parent="origin/main"):
        """A branch with a worktree, pushed with its upstream set."""
        git(self.work, "worktree", "add", "-q", self.wt(name), "-b", name, parent)
        commit(self.wt(name), f"{name}.txt")
        git(self.wt(name), "push", "-q", "-u", "origin", name)

    def push_from_other(self, name, file):
        git(self.other, "fetch", "-q", "origin")
        git(self.other, "switch", "-q", "-C", name, f"origin/{name}")
        commit(self.other, file)
        git(self.other, "push", "-q", "origin", name)

    def head(self, name):
        return git(self.wt(name), "rev-parse", "HEAD")


class ParentSync(Repo):
    def setUp(self):
        super().setUp()
        for n in ("behind", "dirty", "ahead", "locked"):
            self.stacked(n)
            self.push_from_other(n, f"{n}-remote.txt")
        with open(os.path.join(self.wt("dirty"), "behind-edit.txt"), "w", encoding="utf-8") as f:
            f.write("tracked\n")
        git(self.wt("dirty"), "add", "behind-edit.txt")  # a tracked (staged) change
        commit(self.wt("ahead"), "ahead-local.txt")
        git(self.work, "worktree", "lock", "--reason",
            f"claude session x (pid {os.getpid()} start 1)", self.wt("locked"))
        self.before = {n: self.head(n) for n in ("behind", "dirty", "ahead", "locked")}

    def test_behind_clean_worktree_is_fast_forwarded_and_others_only_get_notes(self):
        out = sweep(self.work)
        self.assertNotEqual(self.head("behind"), self.before["behind"])
        self.assertEqual(self.head("behind"), git(self.work, "rev-parse", "origin/behind"))
        self.assertIn("behind fast-forwarded 1 commit(s) in ", out)
        for n in ("dirty", "ahead", "locked"):
            self.assertEqual(self.head(n), self.before[n], n)
        self.assertIn("has tracked changes: not pulled", out)
        self.assertIn("has 1 local commit(s) and is 1 behind origin/ahead", out)

    def test_live_lock_prints_the_command_and_runs_nothing(self):
        out = sweep(self.work)
        rel = ws.rel(self.work, self.wt("locked"))
        self.assertIn(f"git -C {rel} merge --ff-only origin/locked", out)
        self.assertIn("git pull --ff-only", out)
        self.assertEqual(self.head("locked"), self.before["locked"])

    def test_no_pull_turns_everything_into_notes(self):
        out = sweep(self.work, "--no-pull")
        for n in ("behind", "dirty", "ahead", "locked"):
            self.assertEqual(self.head(n), self.before[n], n)
        rel = ws.rel(self.work, self.wt("behind"))
        self.assertIn(f"(--no-pull): run `git -C {rel} merge --ff-only origin/behind`", out)

    def test_branch_without_upstream_is_skipped_silently(self):
        git(self.work, "worktree", "add", "-q", self.wt("local-only"), "-b", "local-only")
        out = sweep(self.work)
        self.assertNotIn("local-only", out.split("\n\n")[0])


class MergedIntoParent(Repo):
    def setUp(self):
        super().setUp()
        self.stacked("feat-a")
        self.stacked("feat-b", parent="feat-a")
        # The PR feat-b -> feat-a is merged on the remote.
        git(self.other, "fetch", "-q", "origin")
        git(self.other, "switch", "-q", "-C", "feat-a", "origin/feat-a")
        git(self.other, "merge", "-q", "--no-ff", "-m", "merge feat-b", "origin/feat-b")
        git(self.other, "push", "-q", "origin", "feat-a")
        git(self.work, "fetch", "-q", "origin")
        self.pr = {"number": 7, "state": "MERGED", "baseRefName": "feat-a"}
        self._orig = ws.open_pr
        ws.open_pr = lambda top, branch, use_gh: self.pr if branch == "feat-b" else None
        self.addCleanup(lambda: setattr(ws, "open_pr", self._orig))

    def item(self, name="feat-b"):
        items = ws.classify(self.work, "main", "origin/main", True)
        return next(i for i in items if i["branch"] == name)

    def test_classified_delete_with_the_parent_proof_next_to_D(self):
        it = self.item()
        self.assertEqual(it["class"], "delete", it)
        self.assertEqual(it["merged"], "ancestor of origin/feat-a (PR #7 base)")
        rel = ws.rel(self.work, self.wt("feat-b"))
        self.assertEqual(it["commands"][0], f"git worktree remove {rel}")
        self.assertTrue(it["commands"][1].startswith("git branch -D feat-b  # ancestor of origin/feat-a;"))
        self.assertIn("-d compares with HEAD or a gone upstream and refuses", it["commands"][1])
        self.assertNotIn("--force", " ".join(it["commands"]))

    def test_parent_gone_falls_back_to_the_base_comparison(self):
        git(self.work, "push", "-q", "origin", "--delete", "feat-a")
        git(self.work, "fetch", "-q", "origin", "--prune")
        it = self.item()
        self.assertEqual(it["class"], "review", it)
        self.assertIn("not in origin/main", " ".join(it["reasons"]))

    def test_branch_not_contained_in_the_parent_stays_review(self):
        commit(self.wt("feat-b"), "late.txt")  # after the PR was merged
        it = self.item()
        self.assertEqual(it["class"], "review", it)

    def test_pr_into_the_base_itself_is_not_special(self):
        self.pr = {"number": 7, "state": "MERGED", "baseRefName": "main"}
        self.assertEqual(self.item()["class"], "review")

    def test_open_pr_into_parent_is_not_merged(self):
        self.pr = {"number": 7, "state": "OPEN", "baseRefName": "feat-a"}
        it = self.item()
        self.assertEqual(it["class"], "review")
        self.assertIn("PR #7 is open", " ".join(it["reasons"]))


if __name__ == "__main__":
    unittest.main()
