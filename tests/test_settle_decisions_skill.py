"""The settle-decisions skill keeps the round format and the rules that make it work."""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "settle-decisions", "SKILL.md")


def read_skill():
    with open(SKILL, encoding="utf-8") as f:
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


class SettleDecisionsSkillTest(unittest.TestCase):
    def setUp(self):
        self.text = read_skill()
        self.fields = frontmatter(self.text)

    def test_model_can_invoke_it(self):
        # Other skills call it as a building block, so the model must be able to invoke it.
        self.assertEqual(self.fields.get("name"), "settle-decisions")
        self.assertNotIn("disable-model-invocation", self.fields)

    def test_description_stays_short(self):
        # The description is always loaded; keep it to the trigger.
        self.assertLessEqual(len(self.fields.get("description", "")), 300)

    def test_round_format(self):
        for marker in ("❓ **Q<n>**", "➡️ <your recommended answer>", "\n   ---\n"):
            self.assertIn(marker, self.text, marker)

    def test_rules(self):
        for rule in (
            "Start with what is settled",
            "never start again at 1",
            'so "yes" accepts your recommended answer',
            "(revisits Q<m>)",
            "Never change a settled decision silently",
            "at most four questions and each is a choice between options",
            "Never ask the user what you can find out",
            "Never answer your own question and move on",
            "Do not act on any decision before the user confirms",
            "An empty frontier is not a confirmation",
            "This skill writes no files itself",
        ):
            self.assertIn(rule, self.text, rule)


if __name__ == "__main__":
    unittest.main()
