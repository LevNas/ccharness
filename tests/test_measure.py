#!/usr/bin/env python3
"""Tests for scripts/measure_always_on.py. Run: python3 tests/test_measure.py"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import measure_always_on as m  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        FAILURES.append(name)
        print(f"     {detail!r}"[:300])


def skill(base, name, desc):
    d = os.path.join(base, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\nbody that is never counted\n")


def settings(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def fixture(base, model=None, desc_len=100, n=3):
    home, target = os.path.join(base, "home"), os.path.join(base, "repo")
    for i in range(n):
        skill(os.path.join(target, ".claude", "skills"), f"s{i}", "x" * desc_len)
    if model:
        settings(os.path.join(home, ".claude", "settings.json"), {"model": model})
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
    return home, target


def test_listing_counts_name_and_capped_description():
    with tempfile.TemporaryDirectory() as base:
        home, target = fixture(base, desc_len=2000, n=2)
        s = m.measure(target, home, env={})["skill_listing"]
        # each line: len("s0") + 1536 (cap) + 4
        check("two skills listed", s["skills"] == 2, s)
        check("description capped at 1536", s["chars"] == 2 * (2 + 1536 + 4), s)


def test_window_from_model():
    with tempfile.TemporaryDirectory() as base:
        home, target = fixture(base, model="opus[1m]")
        s = m.measure(target, home, env={})["skill_listing"]
        check("[1m] model: 1M window", s["window_tokens"] == 1_000_000, s)
        check("[1m] model: budget 10,000 chars", s["budget_chars"] == 10_000, s)
    with tempfile.TemporaryDirectory() as base:
        home, target = fixture(base, model="sonnet")
        s = m.measure(target, home, env={})["skill_listing"]
        check("other model: 200k window", s["window_tokens"] == 200_000, s)
        check("other model: budget 2,000 chars", s["budget_chars"] == 2_000, s)


def test_overrides():
    with tempfile.TemporaryDirectory() as base:
        home, target = fixture(base, model="opus[1m]")
        settings(os.path.join(target, ".claude", "settings.json"), {"skillListingBudgetFraction": 0.02})
        s = m.measure(target, home, env={})["skill_listing"]
        check("project fraction overrides default", s["budget_chars"] == 20_000, s)
        s = m.measure(target, home, window=300_000, env={})["skill_listing"]
        check("--window overrides the model", s["window_tokens"] == 300_000 and s["budget_chars"] == 6_000, s)
        s = m.measure(target, home, env={"SLASH_COMMAND_TOOL_CHAR_BUDGET": "123"})["skill_listing"]
        check("env fixed budget wins", s["budget_chars"] == 123
              and s["budget_source"] == "SLASH_COMMAND_TOOL_CHAR_BUDGET", s)


def test_over_budget_flag_and_output():
    with tempfile.TemporaryDirectory() as base:
        home, target = fixture(base, model="sonnet", desc_len=1000, n=3)  # ~3,000 chars > 2,000
        s = m.measure(target, home, env={})["skill_listing"]
        check("over budget flagged", s["over_budget"], s)
        env = {k: v for k, v in os.environ.items() if k != "SLASH_COMMAND_TOOL_CHAR_BUDGET"}
        env["HOME"] = home
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "measure_always_on.py"),
                              "--target", target], capture_output=True, text=True, env=env).stdout
        check("table prints the listing line", "skill listing (estimate" in out, out)
        check("table prints OVER advice", "OVER: descriptions of the least-used skills" in out, out)
        check("table points to /doctor prompt-audit", "/doctor prompt-audit" in out, out)


def main():
    for t in sorted(k for k in globals() if k.startswith("test_")):
        globals()[t]()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nall tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
