#!/usr/bin/env python3
"""Tests for hooks/pretool_bash_guard.py (the hard-deny floor) and the deny-rule snippet.
Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import pretool_bash_guard as g  # noqa: E402

# The floor: what a permissions.deny Bash rule cannot express or does not match.
MUST_BLOCK = [
    "rm -rf /",
    "rm -rf /*",
    "sudo rm -rf /",
    "/bin/rm -rf /",
    "rm -fr ~",
    "rm -rf $HOME",
    "rm -rf .",
    "rm -rf ..",
    "rm -rf *",
    "rm -r /usr",
    "rm -rf /home/alice",
    "rm --recursive --force /",
    "cd /tmp && rm -rf /",
    "echo ok; rm -rf ~/",
    "FOO=1 rm -rf /etc",
    "timeout 5 rm -rf /",
    "find . -name x | xargs rm -rf /",
    "bash -c 'rm -rf /'",
    "sh -c \"cd /tmp && rm -rf ~\"",
    "mkfs.ext4 /dev/sda1",
    "/sbin/mkfs.ext4 /dev/sda1",
    "dd if=/dev/zero of=/dev/sda bs=1M",
    "cat foo > /dev/sda",
    "shred -u secrets.txt",
    ":(){ :|:& };:",
]

# Allowed by the floor. Some of these are blocked by the scaffolded deny rules
# instead (git push --force, git reset --hard, ...), which is the point: the
# floor stays small and the opinionated tier is an official, per-repository rule.
MUST_PASS = [
    "",
    "ls -la",
    "rm -rf ./build",
    "rm -rf node_modules dist",
    "rm -rf /tmp/scratch/foo",
    "rm -rf /home/alice/project/build",
    "rm file.txt",
    "rm -r src/old",
    "git push --force origin main",
    "git reset --hard HEAD~3",
    "git clean -fdx",
    "git checkout -- .",
    "chmod -R 777 /var/www",
    "dd if=big.iso of=copy.iso bs=4M",
    "grep -r 'mkfs' docs/",
    "printf 'ok' | tee log.txt",
    "echo \"it's fine\"",
    "bash -c 'ls -la'",
    "git commit -m 'rm -rf / is dangerous'",
    "python3 -c \"print('unbalanced quote here')\"",
]


class Judge(unittest.TestCase):
    def test_blocks(self):
        for cmd in MUST_BLOCK:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(g.judge(cmd), cmd)

    def test_passes(self):
        for cmd in MUST_PASS:
            with self.subTest(cmd=cmd):
                self.assertIsNone(g.judge(cmd), cmd)


class Protocol(unittest.TestCase):
    script = os.path.join(ROOT, "hooks", "pretool_bash_guard.py")

    def run_hook(self, payload):
        p = subprocess.run([sys.executable, self.script], input=payload, capture_output=True, text=True)
        return p.returncode, p.stderr

    def test_deny_exit_2(self):
        code, err = self.run_hook(json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}))
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED by ccharness bash guard", err)

    def test_allow_exit_0(self):
        code, _ = self.run_hook(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        self.assertEqual(code, 0)

    def test_malformed_input_allows(self):
        self.assertEqual(self.run_hook("not json")[0], 0)
        self.assertEqual(self.run_hook("{}")[0], 0)

    def test_other_tool_allows(self):
        code, _ = self.run_hook(json.dumps({"tool_name": "Write", "tool_input": {"command": "rm -rf /"}}))
        self.assertEqual(code, 0)


class DenyRuleSnippet(unittest.TestCase):
    """The opinionated tier is shipped as official permission rules; keep the file well-formed."""
    path = os.path.join(ROOT, "templates", "settings.snippet.json")

    def test_valid_json_with_bash_deny_rules(self):
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        deny = data["permissions"]["deny"]
        self.assertGreaterEqual(len(deny), 8)
        for rule in deny:
            with self.subTest(rule=rule):
                self.assertTrue(rule.startswith("Bash(") and rule.endswith(")"), rule)
        # Rules must not be so broad that they block every rm or every git push.
        self.assertNotIn("Bash(rm *)", deny)
        self.assertNotIn("Bash(git push *)", deny)


if __name__ == "__main__":
    unittest.main()
