#!/usr/bin/env python3
"""Tests for hooks/agent_tier_guard.py: deny a model override more than one tier above the pinned tier.
Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(HERE), "hooks", "agent_tier_guard.py")


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "agents"))
        self.agent("worker", "sonnet")
        self.agent("distiller", "haiku")

    def agent(self, name, model):
        with open(os.path.join(self.root, "agents", name + ".md"), "w") as fh:
            fh.write(f"---\nname: {name}\ndescription: x\nmodel: {model}\neffort: low\n---\n\nbody\n")

    def run_hook(self, payload, **env):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        e = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_ROOT", "CCHARNESS_TIER_GUARD")}
        e["CLAUDE_PLUGIN_ROOT"] = self.root
        e.update(env)
        out = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True, env=e)
        self.assertEqual(out.returncode, 0, out.stderr)
        if not out.stdout.strip():
            return None
        o = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual(o["hookEventName"], "PreToolUse")
        self.assertEqual(o["permissionDecision"], "deny")
        return o["permissionDecisionReason"]

    def spawn(self, subagent_type="ccharness:worker", model=None, tool="Agent", **env):
        tool_input = {"subagent_type": subagent_type, "description": "d", "prompt": "p"}
        if model is not None:
            tool_input["model"] = model
        return self.run_hook({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}, **env)

    def test_no_model_is_allowed(self):
        self.assertIsNone(self.spawn())

    def test_inherit_and_empty_are_allowed(self):
        self.assertIsNone(self.spawn(model="inherit"))
        self.assertIsNone(self.spawn(model=""))

    def test_same_tier_and_lower_tier_are_allowed(self):
        self.assertIsNone(self.spawn(model="sonnet"))
        self.assertIsNone(self.spawn(model="haiku"))

    def test_one_tier_up_is_allowed(self):
        self.assertIsNone(self.spawn(model="opus"))
        self.assertIsNone(self.spawn("ccharness:distiller", "sonnet"))

    def test_two_tiers_up_is_denied_and_names_the_pinned_tier(self):
        reason = self.spawn(model="fable")
        self.assertIn("pinned to sonnet", reason)
        self.assertIn("tier 2", reason)
        self.assertIsNotNone(self.spawn("ccharness:distiller", "opus"))

    def test_full_model_names_count_by_family(self):
        self.assertIsNone(self.spawn(model="claude-opus-5-5"))
        self.assertIsNotNone(self.spawn(model="claude-fable-5-1"))
        self.assertIsNotNone(self.spawn(model="mythos"))

    def test_unknown_model_is_denied(self):
        self.assertIsNotNone(self.spawn(model="gpt-9"))

    def test_pinned_tier_is_read_from_the_frontmatter(self):
        self.agent("worker", "opus")
        self.assertIsNone(self.spawn(model="fable"))
        self.agent("worker", "haiku")
        self.assertIsNotNone(self.spawn(model="fable"))
        self.assertIsNotNone(self.spawn(model="opus"))
        self.assertIsNone(self.spawn(model="sonnet"))

    def test_quoted_pinned_value(self):
        self.agent("worker", '"opus"')
        self.assertIsNone(self.spawn(model="fable"))

    def test_task_tool_name_is_covered(self):
        self.assertIsNotNone(self.spawn(model="fable", tool="Task"))

    def test_non_catalog_type_is_allowed(self):
        self.assertIsNone(self.spawn("ccharness:nothing-here", "fable"))
        self.assertIsNone(self.spawn("general-purpose", "fable"))
        self.assertIsNone(self.spawn("claude", "fable"))

    def test_other_plugin_prefix_is_not_ours(self):
        self.assertIsNone(self.spawn("ccorch:worker", "fable"))
        self.assertIsNone(self.spawn("worker", "fable"))

    def test_type_cannot_reach_other_paths(self):
        with open(os.path.join(self.root, "evil.md"), "w") as fh:
            fh.write("---\nmodel: haiku\n---\n")
        self.assertIsNone(self.spawn("ccharness:../evil", "fable"))

    def test_file_without_a_model_line_or_unreadable_allows(self):
        with open(os.path.join(self.root, "agents", "worker.md"), "w") as fh:
            fh.write("---\nname: worker\n---\n")
        self.assertIsNone(self.spawn(model="fable"))
        with open(os.path.join(self.root, "agents", "worker.md"), "w") as fh:
            fh.write("---\nname: worker\n---\nmodel: haiku\n")  # outside the frontmatter
        self.assertIsNone(self.spawn(model="fable"))
        os.remove(os.path.join(self.root, "agents", "worker.md"))
        os.mkdir(os.path.join(self.root, "agents", "worker.md"))  # exists but cannot be read as a file
        self.assertIsNone(self.spawn(model="fable"))

    def test_pinned_inherit_allows(self):
        self.agent("worker", "inherit")
        self.assertIsNone(self.spawn(model="fable"))

    def test_off_switch(self):
        self.assertIsNone(self.spawn(model="fable", CCHARNESS_TIER_GUARD="off"))
        self.assertIsNotNone(self.spawn(model="fable", CCHARNESS_TIER_GUARD="on"))

    def test_other_tools_are_ignored(self):
        self.assertIsNone(self.run_hook({"tool_name": "Bash", "tool_input": {"subagent_type": "ccharness:worker",
                                                                             "model": "fable"}}))

    def test_malformed_input_exits_zero_without_output(self):
        for raw in ("{not json", "[1, 2]", "", {"tool_name": "Agent"}, {"tool_name": "Agent", "tool_input": "x"},
                    {"tool_name": "Agent", "tool_input": {"subagent_type": 7, "model": "fable"}},
                    {"tool_name": "Agent", "tool_input": {"subagent_type": "ccharness:worker", "model": 7}}):
            self.assertIsNone(self.run_hook(raw), raw)

    def test_real_catalog_pins_are_comparable(self):
        """Every shipped agent file pins a tier the guard understands (no silent fail-open)."""
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))
        import agent_tier_guard
        agents = os.path.join(os.path.dirname(HERE), "agents")
        names = sorted(f for f in os.listdir(agents) if f.endswith(".md"))
        self.assertEqual(len(names), 8)
        for name in names:
            pinned = agent_tier_guard.pinned_model(os.path.join(agents, name))
            self.assertGreater(agent_tier_guard.tier(pinned or ""), 0, name)


if __name__ == "__main__":
    unittest.main()
