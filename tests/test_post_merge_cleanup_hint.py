#!/usr/bin/env python3
"""Tests for hooks/post_merge_cleanup_hint.py: a cleanup hint after `gh pr merge`.
Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(HERE), "hooks", "post_merge_cleanup_hint.py")


def run(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    out = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    if not out.stdout.strip():
        return None
    o = json.loads(out.stdout)["hookSpecificOutput"]
    return o["hookEventName"], o["additionalContext"]


def bash(command, event="PostToolUse", tool="Bash"):
    return run({"hook_event_name": event, "tool_name": tool, "tool_input": {"command": command}})


class Hint(unittest.TestCase):
    def test_merge_gets_the_cleanup_steps_in_order(self):
        event, text = bash("gh pr merge 12 --merge")
        self.assertEqual(event, "PostToolUse")
        positions = [text.index(w) for w in ("1. ", "uncommitted or untracked", "2. ", "ExitWorktree, action keep",
                                              "3. ", "worktree-sweep", "4. ", "--force")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("never add `--force`", text)

    def test_global_options_and_chains_still_match(self):
        for cmd in ("gh -R owner/repo pr merge 12", "gh pr merge --squash --delete-branch",
                    "cd /x && gh pr merge 3 --rebase", "gh pr merge"):
            self.assertIsNotNone(bash(cmd), cmd)

    def test_sweep_script_is_not_suggested_as_a_hook_action(self):
        self.assertNotIn("worktree_sweep.py", bash("gh pr merge 1")[1])

    def test_option_after_the_number_and_env_prefix_match(self):
        for cmd in ("gh pr merge 1 -R owner/repo", "GH_HOST=h gh pr merge 1", "gh --repo o/r pr merge 2"):
            self.assertIsNotNone(bash(cmd), cmd)

    def test_auto_merge_gets_nothing(self):
        for cmd in ("gh pr merge 12 --auto --squash", "gh pr merge --auto", "gh pr merge 1 --auto=true",
                    "gh pr merge 1 --disable-auto"):
            self.assertIsNone(bash(cmd), cmd)

    def test_auto_false_and_other_segments_do_not_suppress(self):
        self.assertIsNotNone(bash("gh pr merge 1 --auto=false"))
        self.assertIsNotNone(bash("gh pr merge 1 && gh pr merge 2 --auto"), "PR 1 did merge")


class Quiet(unittest.TestCase):
    def test_other_commands_get_nothing(self):
        for cmd in ("gh pr view 12", "gh pr create --title x", "gh pr list --state merged", "git merge main",
                    "gh issue merge", "merge gh pr", "ls", "gh pr view 3; git merge x",
                    "gh pr list && git merge main", "gh api x && gh pr view 1 && git merge b",
                    "echo gh pr merge", 'echo "gh pr merge 1"', "gh pr view 1\ngit merge x"):
            self.assertIsNone(bash(cmd), cmd)

    def test_other_events_and_tools_get_nothing(self):
        self.assertIsNone(bash("gh pr merge 12", event="PostToolUseFailure"))
        self.assertIsNone(bash("gh pr merge 12", tool="Edit"))
        self.assertIsNone(bash("gh pr merge 12", event="PreToolUse"))

    def test_malformed_input_is_ignored(self):
        self.assertIsNone(run("{not json"))
        self.assertIsNone(run("[1, 2]"))
        self.assertIsNone(run(""))
        self.assertIsNone(run({"hook_event_name": "PostToolUse", "tool_name": "Bash"}))
        self.assertIsNone(run({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {}}))
        self.assertIsNone(run({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": "gh pr merge"}))
        self.assertIsNone(run({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": 7}}))

    def test_unbalanced_quote_is_ignored(self):
        self.assertIsNone(bash("gh pr merge 12 --body 'unterminated"))


if __name__ == "__main__":
    unittest.main()
