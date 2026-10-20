"""The writing-for-agents skill keeps its sections, its key rules and its disclosed skill mechanics."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(ROOT, "skills", "writing-for-agents")
SKILL = os.path.join(SKILL_DIR, "SKILL.md")
MECHANICS = os.path.join(SKILL_DIR, "skill-mechanics.md")
BUDGET = os.path.join(ROOT, "skills", "harness-budget", "SKILL.md")


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


class WritingForAgentsSkillTest(unittest.TestCase):
    def setUp(self):
        self.text = read(SKILL)
        self.fields = frontmatter(self.text)

    def test_model_can_invoke_it(self):
        # Claude must open it on its own when it writes a skill, CLAUDE.md, a rule or a prompt.
        self.assertEqual(self.fields.get("name"), "writing-for-agents")
        self.assertNotIn("disable-model-invocation", self.fields)

    def test_description_stays_short(self):
        # The description is always loaded; keep it to the trigger.
        self.assertLessEqual(len(self.fields.get("description", "")), 300)

    def test_sections(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        for section in (
            "Context pointers",
            "The two loads",
            "Information hierarchy",
            "Steps and completion criteria",
            "When to split",
            "Leading words",
            "Pruning",
        ):
            self.assertIn(section, headings, section)

    def test_rules(self):
        for rule in (
            "The default fix is to delete",
            "sharpen the pointer first",
            "One trigger per branch",
            "inline what every branch needs, and disclose what only some branches reach",
            "Sharpen the bound first",
            "Write the positive target instead",
            "one meaning in one place",
            "A document that restates it is a cache",
            "settle a disagreement by running the document, not by argument",
            "Delete a failing sentence whole rather than trimming words from it",
        ):
            self.assertIn(rule, self.text, rule)

    def test_skill_mechanics_is_disclosed(self):
        # Only the skill branch needs it, so it sits behind a pointer.
        self.assertIn("[skill-mechanics.md](skill-mechanics.md)", self.text)
        mechanics = read(MECHANICS)
        for rule in (
            "disable-model-invocation: true",
            "Choose model-invocation only when the agent must reach the skill on its own, or another skill must",
            "## Splitting by invocation",
        ):
            self.assertIn(rule, mechanics, rule)


class HarnessBudgetNoOpTest(unittest.TestCase):
    def test_no_op_test_in_step_4(self):
        text = read(BUDGET)
        step4 = text[text.index("4. Look for instructions nobody uses"):text.index("5. For outdated")]
        for rule in (
            "the answer depends on the model, not on the reader",
            "running the document with and without the sentence, not by argument",
            "Delete a sentence that fails whole",
            "`writing-for-agents`",
        ):
            self.assertIn(rule, step4, rule)


if __name__ == "__main__":
    unittest.main()
