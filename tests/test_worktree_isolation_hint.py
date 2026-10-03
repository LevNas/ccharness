#!/usr/bin/env python3
"""Tests for hooks/worktree_isolation_hint.py: context on EnterWorktree and on the isolation refusal.
Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(HERE), "hooks", "worktree_isolation_hint.py")
WT = "/repo/.claude/worktrees/x"

# Refusals as Claude Code worded them in real sessions (paths replaced).
HEREDOC = (f"This session is isolated in the worktree {WT}, but this command feeds python text naming git in a "
           f"plain command, which cannot be shown to stay inside the worktree. Refusing to run it — a "
           f"worktree-isolated session's git operations must target its own worktree. Run the plain command from {WT}.")
COMPLEX = (f"This session is isolated in the worktree {WT}, but this command names git in a form too complex to "
           f"verify that it stays inside the worktree. Refusing to run it — a worktree-isolated session's git "
           f"operations must target its own worktree. Run the plain command from {WT}.")
VARIABLE = (f"This session is isolated in the worktree {WT}, but this command runs sed with a value computed at "
            f"runtime (the variable f) where an option may stand (a value that is not double-quoted, or whose first "
            f"character is matched or computed rather than spelled out, may begin with -; put -- before it) in a "
            f"plain command, so what it runs cannot be shown not to be git. Refusing to run it — a "
            f"worktree-isolated session's git operations must target its own worktree. Run the plain command from {WT}.")
SHARED_C = (f"This session is isolated in the worktree {WT}, but this command redirects git to the shared checkout "
            f"via -C. Refusing to run it — a worktree-isolated session's git operations must target its own worktree.")
GH_TEXT = (f"This session is isolated in the worktree {WT}, but this command runs gh with the text of a body that "
           f"names git. Refusing to run it — a worktree-isolated session's git operations must target its own worktree.")
CD = (f"This session is isolated in the worktree {WT}, but this command changes directory to a location computed "
      f"at runtime before running git. Refusing to run it — a worktree-isolated session's git operations must "
      f"target its own worktree.")


def run(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    out = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    if not out.stdout.strip():
        return None
    o = json.loads(out.stdout)["hookSpecificOutput"]
    return o["hookEventName"], o["additionalContext"]


def failure(error, tool="Bash"):
    return run({"hook_event_name": "PostToolUseFailure", "tool_name": tool,
                "tool_input": {"command": "x"}, "error": error})


class OnEnter(unittest.TestCase):
    def test_enter_worktree_gets_the_forms_once(self):
        event, text = run({"hook_event_name": "PostToolUse", "tool_name": "EnterWorktree",
                           "tool_input": {"name": "x"}, "tool_response": {}})
        self.assertEqual(event, "PostToolUse")
        for words in ("heredoc", "python3 -c", "Edit/Write", "ExitWorktree", "--body-file"):
            self.assertIn(words, text)
        # `git -C` to the main checkout is itself refused; a shell variable in a path would be too.
        self.assertNotIn("git -C <path>", text)
        self.assertNotIn("$CLAUDE_JOB_DIR", text)

    def test_other_tools_get_nothing(self):
        self.assertIsNone(run({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {}}))
        self.assertIsNone(run({"hook_event_name": "PostToolUse", "tool_name": "ExitWorktree", "tool_input": {}}))


class OnRefusal(unittest.TestCase):
    def test_heredoc_refusal_points_to_a_script_file(self):
        event, text = failure(HEREDOC)
        self.assertEqual(event, "PostToolUseFailure")
        self.assertIn("python3 /abs/path/to/x.py", text)
        self.assertNotIn("Edit tool instead of sed", text)

    def test_complex_refusal_points_to_single_commands_and_other_repositories(self):
        _, text = failure(COMPLEX)
        self.assertIn("one git command per call", text)
        self.assertIn("ExitWorktree", text)
        self.assertNotIn("heredoc", text)

    def test_variable_refusal_points_to_literal_values_and_the_edit_tool(self):
        _, text = failure(VARIABLE)
        self.assertIn("Spell values out", text)
        self.assertIn("Edit tool", text)

    def test_git_c_to_the_shared_checkout_points_to_leaving_the_worktree(self):
        _, text = failure(SHARED_C)
        self.assertIn("run git in the worktree itself", text)
        self.assertNotIn("one git command per call", text, "a specific rewrite replaces the general one")

    def test_gh_with_inline_text_points_to_a_body_file(self):
        self.assertIn("--body-file", failure(GH_TEXT)[1])

    def test_computed_cd_points_to_literal_values(self):
        self.assertIn("computed `-C` / `cd` targets", failure(CD)[1])

    def test_no_rewrite_suggests_a_shell_variable(self):
        for error in (HEREDOC, COMPLEX, VARIABLE, SHARED_C, GH_TEXT, CD):
            self.assertNotIn("$CLAUDE_JOB_DIR", failure(error)[1])

    def test_unknown_wording_still_gets_the_general_rewrite(self):
        _, text = failure(f"This session is isolated in the worktree {WT}, but this command does something new.")
        self.assertIn("one git command per call", text)

    def test_every_hint_says_not_to_retry_the_same_form(self):
        for error in (HEREDOC, COMPLEX, VARIABLE):
            self.assertIn("Do not retry a variation of the same form", failure(error)[1])


class Quiet(unittest.TestCase):
    def test_other_failures_get_nothing(self):
        self.assertIsNone(failure("Exit code 1\nNo such file or directory"))
        self.assertIsNone(failure(HEREDOC, tool="Edit"), "only Bash refusals")
        self.assertIsNone(run({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash"}))

    def test_malformed_input_is_ignored(self):
        self.assertIsNone(run("{not json"))
        self.assertIsNone(run("[1, 2]"))
        self.assertIsNone(run({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "error": 42}))


if __name__ == "__main__":
    unittest.main()
