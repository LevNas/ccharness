"""The diagnosing-bugs skill keeps its gate, its steps and its test rules in tests.md."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(ROOT, "skills", "diagnosing-bugs")
SKILL = os.path.join(SKILL_DIR, "SKILL.md")
TESTS = os.path.join(SKILL_DIR, "tests.md")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    head, sep, _ = text[4:].partition("\n---\n")
    if not text.startswith("---\n") or not sep:
        raise AssertionError("SKILL.md has no frontmatter")
    fields = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


class DiagnosingBugsSkillTest(unittest.TestCase):
    def setUp(self):
        self.text = read(SKILL)
        self.fields = frontmatter(self.text)

    def test_model_can_invoke_it(self):
        # The bug-report line of the CLAUDE.md snippet and dev-shipper must reach it.
        self.assertEqual(self.fields.get("name"), "diagnosing-bugs")
        self.assertNotIn("disable-model-invocation", self.fields)

    def test_description_is_short_and_excludes_quick_questions(self):
        # Always loaded; upstream fired on plain questions, so the description rules them out.
        description = self.fields.get("description", "")
        self.assertLessEqual(len(description), 300)
        self.assertIn("before writing a regression or behaviour test", description)
        self.assertIn("Not for a question one answer settles", description)

    def test_sections(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        for section in (
            "The core",
            "Redact",
            "Step 1: Build the check (the gate)",
            "Step 2: Reproduce",
            "Step 3: Hypotheses",
            "Step 4: Probe",
            "Step 5: Fix and regression test",
            "Done when",
        ):
            self.assertIn(section, headings, section)

    def test_rules(self):
        for rule in (
            "Trust only a check you have seen fail",
            "an \"ok\" over zero items",
            "run it once, and show the command and its output. No hypothesis before it exists",
            "a read-only command that shows the symptom counts",
            "Do not go on to hypotheses without a check",
            "not a nearby one",
            "Write 3-5 ranked hypotheses before testing any of them",
            "Show the ranked list to the user before testing",
            "Change one thing at a time",
            "`[DEBUG-a4f2]`",
            "If no correct seam exists, that is a finding",
            "diff it against an untouched copy",
            "waits for whatever agreement the repository's instructions require",
            "`<REDACTED>`",
            "commit `5beb35b`, MIT",
        ):
            self.assertIn(rule, self.text, rule)

    def test_points_at_test_rules(self):
        self.assertIn("[tests.md](tests.md)", self.text)


class TestRulesFileTest(unittest.TestCase):
    def setUp(self):
        self.text = read(TESTS)

    def test_rules(self):
        for rule in (
            "watch it fail for the right reason",
            "Zero tests collected exits 0 and is not a pass",
            "Test through public interfaces only",
            "Agree the seams under test when the way the work will be checked is agreed",
            "what it catches and what it misses",
            "| Implementation-coupled |",
            "| Tautological |",
            "| Horizontal slicing |",
            "Mock only at system boundaries",
            "Never mock your own modules",
            "One test at one seam",
            "commit `5beb35b`, MIT",
        ):
            self.assertIn(rule, self.text, rule)


if __name__ == "__main__":
    unittest.main()
