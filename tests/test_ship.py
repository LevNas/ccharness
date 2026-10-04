#!/usr/bin/env python3
"""Tests for scripts/ship.py against temporary repositories with a local bare remote."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "ship.py")
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")

FAKE_GH = """#!/bin/sh
# Canned `gh pr view`: prints response N from $FAKE_GH_DIR (the last one repeats).
n=$(cat "$FAKE_GH_DIR/count" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$FAKE_GH_DIR/count"
f="$FAKE_GH_DIR/resp$n.json"
[ -f "$f" ] || f="$FAKE_GH_DIR/resp_last.json"
cat "$f"
"""


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class ShipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = self.tmp.name
        self.remote = os.path.join(base, "remote.git")
        self.work = os.path.join(base, "work")
        git(base, "init", "-q", "--bare", "-b", "main", self.remote)
        git(base, "clone", "-q", self.remote, self.work)
        git(self.work, "checkout", "-q", "-b", "main")
        write(os.path.join(self.work, "README"), "hello\n")
        git(self.work, "add", "README")
        git(self.work, "commit", "-qm", "init")
        git(self.work, "push", "-q", "-u", "origin", "main")
        git(self.work, "remote", "set-head", "origin", "main")
        self.msg = os.path.join(base, "msg.txt")
        write(self.msg, "add things\n")

    def feature(self):
        git(self.work, "checkout", "-q", "-b", "feature")

    def ship(self, *args, env=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.work, capture_output=True,
                              text=True, env=env or ENV)

    def commit(self, files, *extra):
        return self.ship("commit", "--files", *files, "--message-file", self.msg, *extra)

    # commit
    def test_commit_stages_by_name_and_prints_sha(self):
        self.feature()
        write(os.path.join(self.work, "a.txt"), "a\n")
        write(os.path.join(self.work, "untracked.txt"), "left alone\n")
        r = self.commit(["a.txt"])
        self.assertEqual(r.returncode, 0, r.stderr)
        sha = git(self.work, "rev-parse", "--short", "HEAD")
        self.assertIn(sha, r.stdout)
        self.assertEqual(git(self.work, "show", "--name-only", "--format=", "HEAD"), "a.txt")
        self.assertEqual(git(self.work, "log", "-1", "--format=%s"), "add things")

    def test_commit_stages_deleted_path_as_removal(self):
        self.feature()
        os.remove(os.path.join(self.work, "README"))
        r = self.commit(["README"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.work, "show", "--name-status", "--format=", "HEAD"), "D\tREADME")

    def test_refuses_on_default_branch(self):
        write(os.path.join(self.work, "a.txt"), "a\n")
        r = self.commit(["a.txt"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("default branch", r.stderr)
        self.assertEqual(git(self.work, "diff", "--cached", "--name-only"), "")
        self.assertEqual(self.ship("push").returncode, 1)

    def test_refuses_during_merge(self):
        self.feature()
        write(os.path.join(self.work, "README"), "feature\n")
        git(self.work, "commit", "-qam", "f")
        git(self.work, "checkout", "-q", "main")
        write(os.path.join(self.work, "README"), "main\n")
        git(self.work, "commit", "-qam", "m")
        git(self.work, "checkout", "-q", "feature")
        subprocess.run(["git", "merge", "main"], cwd=self.work, capture_output=True, env=ENV)
        write(os.path.join(self.work, "b.txt"), "b\n")
        r = self.commit(["b.txt"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("MERGE_HEAD", r.stderr)

    def test_staged_set_mismatch_stops_and_keeps_staging(self):
        self.feature()
        write(os.path.join(self.work, "a.txt"), "a\n")
        write(os.path.join(self.work, "pre.txt"), "pre\n")
        git(self.work, "add", "pre.txt")
        before = git(self.work, "rev-parse", "HEAD")
        r = self.commit(["a.txt"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("pre.txt", r.stdout)
        self.assertIn("a.txt", r.stdout)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), before)
        self.assertEqual(set(git(self.work, "diff", "--cached", "--name-only").split()), {"a.txt", "pre.txt"})

    def test_scan_hit_prints_no_secret_and_does_not_commit(self):
        self.feature()
        secret = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
        write(os.path.join(self.work, "cfg.txt"), "ok\nkey = %s\n" % secret)
        before = git(self.work, "rev-parse", "HEAD")
        r = self.commit(["cfg.txt"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("cfg.txt:2", r.stdout)
        self.assertIn("github-token", r.stdout)
        self.assertNotIn(secret, r.stdout + r.stderr)
        self.assertNotIn("A1b2C3d4", r.stdout + r.stderr)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), before)

    def test_scan_credential_assignment_and_key_header(self):
        self.feature()
        write(os.path.join(self.work, "c.txt"), 'pass' + 'word = "hunter2hunter2"\n')
        r = self.commit(["c.txt"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("credential-assignment", r.stdout)
        self.assertNotIn("hunter2", r.stdout)
        git(self.work, "reset", "-q")
        write(os.path.join(self.work, "c.txt"), "-----BEGIN RSA PRIV" + "ATE KEY-----\n")
        r = self.commit(["c.txt"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("private-key-header", r.stdout)

    def test_removed_lines_are_not_scanned(self):
        write(os.path.join(self.work, "old.txt"), 'tok' + 'en = "abcdefghijkl"\n')
        git(self.work, "add", "old.txt")
        git(self.work, "commit", "-qm", "old")
        self.feature()
        write(os.path.join(self.work, "old.txt"), "clean\n")
        r = self.commit(["old.txt"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def assert_key_blocked(self, name, content=None, config=()):
        self.feature()
        for k, v in config:
            git(self.work, "config", k, v)
        header = "-----BEGIN OPENSSH PRIV" + "ATE KEY-----\n"
        with open(os.path.join(self.work, name), "wb") as f:
            f.write(content if content is not None else header.encode())
        before = git(self.work, "rev-parse", "HEAD")
        r = self.commit([name])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("private-key-header", r.stdout)
        self.assertNotIn("OPENSSH", r.stdout + r.stderr)
        self.assertEqual(git(self.work, "rev-parse", "HEAD"), before)

    def test_scan_unicode_name(self):
        self.assert_key_blocked("日本語.txt")

    def test_scan_name_with_space(self):
        self.assert_key_blocked("my key.txt")

    def test_scan_diff_noprefix(self):
        self.assert_key_blocked("key.txt", config=[("diff.noprefix", "true")])

    def test_scan_diff_mnemonic_prefix(self):
        self.assert_key_blocked("key.txt", config=[("diff.mnemonicPrefix", "true")])

    def test_scan_line_starting_with_plus_plus_space(self):
        header = "-----BEGIN OPENSSH PRIV" + "ATE KEY-----"
        # the '++ ' line is added as '+++ ...' and must not be read as a file header
        self.assert_key_blocked("k.txt", ("++ x\n" + header + "\n").encode())
        git(self.work, "reset", "-q")
        with open(os.path.join(self.work, "k.txt"), "wb") as f:
            f.write(("++ " + header + "\n").encode())
        self.assertEqual(self.commit(["k.txt"]).returncode, 1)

    def test_scan_non_utf8_file_does_not_crash(self):
        self.assert_key_blocked("latin.txt", b"caf\xe9 \xff\n-----BEGIN RSA PRIV" + b"ATE KEY-----\n")
        git(self.work, "reset", "-q")
        with open(os.path.join(self.work, "latin.txt"), "wb") as f:
            f.write(b"caf\xe9 \xff\n")
        r = self.commit(["latin.txt"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_glob_characters_in_path_are_literal(self):
        self.feature()
        write(os.path.join(self.work, "a*.txt"), "star\n")
        write(os.path.join(self.work, "a1.txt"), "one\n")
        r = self.commit(["a*.txt"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(self.work, "show", "--name-only", "--format=", "HEAD"), "a*.txt")

    def test_path_outside_repository_refused(self):
        self.feature()
        r = self.commit(["../outside.txt"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a file inside", r.stderr)

    def test_refuses_on_master_even_when_origin_head_is_main(self):
        git(self.work, "checkout", "-q", "-b", "master")
        write(os.path.join(self.work, "a.txt"), "a\n")
        r = self.commit(["a.txt"])
        self.assertEqual(r.returncode, 1)
        self.assertIn("default branch", r.stderr)

    def test_scan_patterns_file(self):
        self.feature()
        pats = os.path.join(self.tmp.name, "pats.txt")
        write(pats, "# private names\n\nacme-internal\n")
        write(os.path.join(self.work, "n.txt"), "see acme-internal for details\n")
        r = self.commit(["n.txt"], "--scan-patterns", pats)
        self.assertEqual(r.returncode, 1)
        self.assertIn("n.txt:1", r.stdout)
        self.assertNotIn("acme-internal", r.stdout + r.stderr)
        self.assertEqual(git(self.work, "log", "-1", "--format=%s"), "init")
        git(self.work, "reset", "-q")
        r = self.commit(["n.txt"])  # without the patterns the same file is fine
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # push
    def test_push_sets_upstream(self):
        self.feature()
        write(os.path.join(self.work, "a.txt"), "a\n")
        self.assertEqual(self.commit(["a.txt"]).returncode, 0)
        r = self.ship("push")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.work, "rev-parse", "--abbrev-ref", "feature@{upstream}"), "origin/feature")
        self.assertEqual(git(self.remote, "rev-parse", "feature"), git(self.work, "rev-parse", "HEAD"))

    # check
    def fake_gh(self, *responses):
        d = os.path.join(self.tmp.name, "ghdir")
        os.makedirs(d, exist_ok=True)
        for i, resp in enumerate(responses, 1):
            write(os.path.join(d, f"resp{i}.json"), json.dumps(resp))
        write(os.path.join(d, "resp_last.json"), json.dumps(responses[-1]))
        exe = os.path.join(d, "gh")
        write(exe, FAKE_GH)
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR)
        return dict(ENV, PATH=d + os.pathsep + ENV["PATH"], FAKE_GH_DIR=d), d

    def pr(self, **kw):
        base = {"number": 7, "url": "https://example.test/pr/7", "state": "OPEN", "isDraft": False,
                "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "baseRefName": "main",
                "headRefOid": git(self.work, "rev-parse", "HEAD"), "files": [{"path": "a.txt"}]}
        base.update(kw)
        return base

    def check(self, env, *args):
        return self.ship("check", "--poll-interval", "0.05", *args, env=env)

    def test_push_branch_named_with_plus(self):
        git(self.work, "checkout", "-q", "-b", "+x")
        write(os.path.join(self.work, "a.txt"), "a\n")
        self.assertEqual(self.commit(["a.txt"]).returncode, 0)
        r = self.ship("push")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/+x"), git(self.work, "rev-parse", "HEAD"))

    def test_check_ready(self):
        env, _ = self.fake_gh(self.pr())
        r = self.check(env, "--expect-files", "a.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1)
        self.assertIn("READY", r.stdout)

    def test_check_draft_blocked_is_ready(self):
        env, _ = self.fake_gh(self.pr(isDraft=True, mergeStateStatus="DRAFT"))
        self.assertEqual(self.check(env).returncode, 0)

    def test_check_draft_blocked_is_not_ready(self):
        env, _ = self.fake_gh(self.pr(isDraft=True, mergeStateStatus="BLOCKED"))
        r = self.check(env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("BLOCKED", r.stdout)

    def test_check_draft_clean_is_ready(self):
        # what GitHub reports for a draft whose checks pass
        env, _ = self.fake_gh(self.pr(isDraft=True, mergeStateStatus="CLEAN"))
        self.assertEqual(self.check(env).returncode, 0)

    def test_check_non_draft_with_draft_status_is_not_ready(self):
        env, _ = self.fake_gh(self.pr(mergeStateStatus="DRAFT"))
        self.assertEqual(self.check(env).returncode, 1)

    def test_check_rejects_non_finite_wait(self):
        env, _ = self.fake_gh(self.pr())
        for bad in ("inf", "nan", "-1"):
            self.assertEqual(self.check(env, "--wait=" + bad).returncode, 2, bad)

    def test_check_polls_while_head_differs_then_ready(self):
        env, d = self.fake_gh(self.pr(headRefOid="0" * 40), self.pr())
        r = self.check(env, "--wait", "5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(d, "count")) as f:
            self.assertEqual(f.read().strip(), "2")

    def test_check_unknown_then_ready(self):
        env, d = self.fake_gh(self.pr(mergeable="UNKNOWN"), self.pr(mergeable="UNKNOWN"), self.pr())
        r = self.check(env, "--wait", "5")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(d, "count")) as f:
            self.assertEqual(f.read().strip(), "3")

    def test_check_unknown_gives_up_after_wait(self):
        env, _ = self.fake_gh(self.pr(mergeable="UNKNOWN"))
        r = self.check(env, "--wait", "0.2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("mergeable UNKNOWN", r.stdout)

    def test_check_files_mismatch(self):
        env, _ = self.fake_gh(self.pr(files=[{"path": "a.txt"}, {"path": "extra.txt"}]))
        r = self.check(env, "--expect-files", "a.txt")
        self.assertEqual(r.returncode, 1)
        self.assertIn("extra.txt", r.stdout)

    def test_check_head_mismatch(self):
        env, _ = self.fake_gh(self.pr(headRefOid="0" * 40))
        r = self.check(env, "--wait", "0.2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("head", r.stdout)

    def test_check_not_clean_or_closed(self):
        env, _ = self.fake_gh(self.pr(mergeStateStatus="BEHIND"))
        self.assertEqual(self.check(env).returncode, 1)
        env, _ = self.fake_gh(self.pr(state="MERGED"))
        self.assertEqual(self.check(env).returncode, 1)


if __name__ == "__main__":
    unittest.main()
