#!/usr/bin/env python3
"""Tests for hooks/agent_ledger.py: launch and stop records in the main checkout's ledger.
Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(HERE), "hooks", "agent_ledger.py")
GIT_ENV = dict(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
PROMPT_MARKER = "PROMPT-BODY-MARKER-7f3a"


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=dict(os.environ, **GIT_ENV))
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class Ledger(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)
        self.ceiling = os.path.dirname(self.tmp)  # never discover a repository above the temp directory

    def run_hook(self, payload, project_dir=None):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")}
        env["GIT_CEILING_DIRECTORIES"] = self.ceiling
        if project_dir:
            env["CLAUDE_PROJECT_DIR"] = project_dir
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        out = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "")
        return out

    def repo(self, name="main"):
        path = os.path.join(self.tmp, name)
        os.makedirs(path)
        git(path, "init", "-q", "-b", "main")
        with open(os.path.join(path, "f.txt"), "w") as fh:
            fh.write("x\n")
        git(path, "add", "f.txt")
        git(path, "commit", "-qm", "init")
        return path

    def records(self, root):
        path = os.path.join(root, ".claude", "ccharness", "ledger.jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            return [json.loads(line) for line in fh]

    def launch(self, cwd, response, **tool_input):
        base = {"subagent_type": "ccharness:worktree-worker", "description": "implement parser",
                "prompt": PROMPT_MARKER}
        base.update(tool_input)
        return {"hook_event_name": "PostToolUse", "tool_name": "Agent", "session_id": "s1", "cwd": cwd,
                "tool_input": base, "tool_response": response}

    def test_launch_with_agent_id(self):
        main = self.repo()
        self.run_hook(self.launch(main, "Async agent launched.\nagentId: a1b2-C3_d4 (resume with SendMessage)",
                                  model="opus", run_in_background=True))
        (rec,) = self.records(main)
        self.assertEqual(rec["schema"], "ccharness.ledger/1")
        self.assertEqual(rec["event"], "launch")
        self.assertEqual(rec["session_id"], "s1")
        self.assertEqual(rec["agent_id"], "a1b2-C3_d4")
        self.assertEqual(rec["agent_type"], "ccharness:worktree-worker")
        self.assertEqual(rec["model"], "opus")
        self.assertIs(rec["background"], True)
        self.assertEqual(rec["thread"], "implement parser")
        self.assertRegex(rec["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_launch_without_agent_id(self):
        main = self.repo()
        self.run_hook(self.launch(main, "finished: done", run_in_background=False))
        (rec,) = self.records(main)
        self.assertIsNone(rec["agent_id"])
        self.assertIsNone(rec["model"])
        self.assertIs(rec["background"], False)

    def test_agent_id_in_a_structured_response_and_defaults(self):
        main = self.repo()
        payload = self.launch(main, {"content": [{"type": "text", "text": "agentId: zz9"}]})
        del payload["tool_input"]["subagent_type"]
        self.run_hook(payload)
        (rec,) = self.records(main)
        self.assertEqual(rec["agent_id"], "zz9")
        self.assertEqual(rec["agent_type"], "claude")
        self.assertIsNone(rec["background"])  # recorded as given: null when the call did not say

    def test_last_agent_id_wins_over_quoted_text(self):
        main = self.repo()
        self.run_hook(self.launch(main, "the subagent wrote: agentId: fake-1 earlier\nagentId: real-2"))
        self.run_hook(self.launch(main, {"content": [{"type": "text", "text": "agentId: fake-1 ... agentId: real-3"}]}))
        self.assertEqual([r["agent_id"] for r in self.records(main)], ["real-2", "real-3"])

    def test_stop_reason_absent_is_null(self):
        main = self.repo()
        self.run_hook({"hook_event_name": "SubagentStop", "cwd": main, "agent_id": "a1"})
        (rec,) = self.records(main)
        self.assertIsNone(rec["stop_reason"])

    def test_common_dir_not_named_dot_git_stays_out_of_git_metadata(self):
        sep = os.path.join(self.tmp, "sep.git")
        work = os.path.join(self.tmp, "work")
        os.makedirs(work)
        git(work, "init", "-q", "-b", "main", "--separate-git-dir", sep)
        self.run_hook(self.launch(work, "agentId: a1"))
        self.assertEqual(len(self.records(work)), 1)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".claude")), "parent of the common dir")
        self.assertFalse(os.path.exists(os.path.join(sep, ".claude")), "inside git metadata")

    def test_submodule_does_not_write_into_git_modules(self):
        main = self.repo()
        other = self.repo("other")
        git(main, "-c", "protocol.file.allow=always", "submodule", "add", "-q", other, "sub")
        sub = os.path.join(main, "sub")
        self.run_hook(self.launch(sub, "agentId: a1"))
        self.assertFalse(os.path.exists(os.path.join(main, ".git", "modules", ".claude")))
        self.assertFalse(os.path.exists(os.path.join(main, ".git", ".claude")))
        self.assertEqual(len(self.records(sub)), 1)

    def test_removed_cwd_is_never_recreated(self):
        gone = os.path.join(self.tmp, "main", ".claude", "worktrees", "agent-x")
        self.run_hook({"hook_event_name": "SubagentStop", "cwd": gone, "agent_id": "a1"})
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "main")))
        project = os.path.join(self.tmp, "project")
        os.makedirs(project)
        self.run_hook({"hook_event_name": "SubagentStop", "cwd": gone, "agent_id": "a1"}, project_dir=project)
        self.assertEqual(len(self.records(project)), 1)
        self.assertFalse(os.path.exists(gone))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "main")))

    def test_project_dir_that_does_not_exist_is_not_created(self):
        missing = os.path.join(self.tmp, "nope")
        self.run_hook(self.launch(os.path.join(self.tmp, "also-gone"), "agentId: a1"), project_dir=missing)
        self.assertFalse(os.path.exists(missing))

    def test_stop_record(self):
        main = self.repo()
        self.run_hook({"hook_event_name": "SubagentStop", "session_id": "s1", "cwd": main, "agent_id": "a1",
                       "agent_type": "ccharness:worktree-worker", "stop_reason": "end_turn"})
        (rec,) = self.records(main)
        self.assertEqual({k: rec[k] for k in ("schema", "event", "session_id", "agent_id", "agent_type",
                                              "stop_reason")},
                         {"schema": "ccharness.ledger/1", "event": "stop", "session_id": "s1", "agent_id": "a1",
                          "agent_type": "ccharness:worktree-worker", "stop_reason": "end_turn"})

    def test_records_append_in_order(self):
        main = self.repo()
        self.run_hook(self.launch(main, "agentId: a1"))
        self.run_hook({"hook_event_name": "SubagentStop", "cwd": main, "agent_id": "a1"})
        self.assertEqual([r["event"] for r in self.records(main)], ["launch", "stop"])

    def test_no_prompt_text_is_written(self):
        main = self.repo()
        self.run_hook(self.launch(main, "agentId: a1"))
        with open(os.path.join(main, ".claude", "ccharness", "ledger.jsonl")) as fh:
            self.assertNotIn(PROMPT_MARKER, fh.read())

    def test_linked_worktree_writes_to_the_main_checkout(self):
        main = self.repo()
        wt = os.path.join(self.tmp, "wt")
        git(main, "worktree", "add", "-q", wt, "-b", "feature")
        self.run_hook(self.launch(wt, "agentId: a1"))
        self.assertEqual(len(self.records(main)), 1)
        self.assertFalse(os.path.exists(os.path.join(wt, ".claude", "ccharness")))

    def test_subdirectory_cwd_writes_to_the_checkout_root(self):
        main = self.repo()
        sub = os.path.join(main, "a", "b")
        os.makedirs(sub)
        self.run_hook(self.launch(sub, "agentId: a1"))
        self.assertEqual(len(self.records(main)), 1)
        self.assertFalse(os.path.exists(os.path.join(sub, ".claude")))

    def test_not_a_repository_falls_back_to_project_dir_then_cwd(self):
        plain = os.path.join(self.tmp, "plain")
        project = os.path.join(self.tmp, "project")
        os.makedirs(plain)
        os.makedirs(project)
        self.run_hook(self.launch(plain, "agentId: a1"), project_dir=project)
        self.assertEqual(len(self.records(project)), 1)
        self.assertEqual(self.records(plain), [])
        self.run_hook(self.launch(plain, "agentId: a2"))
        self.assertEqual(len(self.records(plain)), 1)

    def test_unwritable_directory_exits_zero(self):
        main = self.repo()
        with open(os.path.join(main, ".claude"), "w") as fh:  # a file where the directory must go
            fh.write("x")
        self.run_hook(self.launch(main, "agentId: a1"))
        blocker = os.path.join(self.tmp, "blocker")
        with open(blocker, "w") as fh:
            fh.write("x")
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        self.run_hook(self.launch(plain, "agentId: a1"), project_dir=os.path.join(blocker, "sub"))

    def test_other_tools_and_malformed_input_write_nothing(self):
        main = self.repo()
        self.run_hook({"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": main,
                       "tool_input": {"command": "ls"}})
        for raw in ("{not json", "[1]", "", {"tool_name": "Agent"}):
            self.run_hook(raw)
        self.assertEqual(self.records(main), [])


if __name__ == "__main__":
    unittest.main()
