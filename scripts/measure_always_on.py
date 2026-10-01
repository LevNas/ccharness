#!/usr/bin/env python3
"""Measure the always-on context budget in bytes.

Counts what every session loads before any work starts:
  project  CLAUDE.md, .claude/CLAUDE.md, CLAUDE.local.md, .claude/rules/**/*.md,
           descriptions of .claude/skills/*/SKILL.md
  user     ~/.claude/CLAUDE.md, ~/.claude/rules/**/*.md,
           descriptions of ~/.claude/skills/*/SKILL.md
  plugins  descriptions of skills shipped by enabled plugins
           (~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/*/SKILL.md)

Skill bodies are not counted: they load only when the skill is used. Each
description is capped at the official `skillListingMaxDescChars` setting
(default 1536 characters), read from user, project and local settings.

CLAUDE.md files also get a line count against the official guideline of
200 lines ("Aim to keep CLAUDE.md under 200 lines by including only
essentials", https://code.claude.com/docs/en/costs). Files over it are flagged.

The skill listing is also estimated against its own budget. Officially the
listing gets 1% of the context window, measured in characters
(`skillListingBudgetFraction` changes the fraction,
`SLASH_COMMAND_TOOL_CHAR_BUDGET` sets a fixed character count); over budget,
the descriptions of the least-used skills are dropped
(https://code.claude.com/docs/en/skills). The estimate counts name plus
capped description of every skill file found above; Claude Code's built-in
skills have no file and are not counted, and `skillOverrides` /
`disable-model-invocation` are not applied. The window is `--window`, else
1,000,000 when the effective `model` setting ends in `[1m]`, else 200,000.

Usage: measure_always_on.py [--target DIR] [--window TOKENS] [--json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

DEFAULT_DESC_CAP = 1536
CLAUDE_MD_LINE_GUIDELINE = 200
DEFAULT_LISTING_FRACTION = 0.01
WINDOW_DEFAULT = 200_000
WINDOW_1M = 1_000_000


def _load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _settings_files(target: str, home: str) -> list[str]:
    return [os.path.join(home, ".claude", "settings.json"),
            os.path.join(target, ".claude", "settings.json"),
            os.path.join(target, ".claude", "settings.local.json")]


def _bytes(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _lines(path: str) -> int:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _field(skill_md: str, key: str) -> str:
    try:
        with open(skill_md, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    dm = re.search(rf"^{re.escape(key)}:\s*(.*?)(?=^\S|\Z)", m.group(1), re.S | re.M)
    return dm.group(1).strip() if dm else ""


def _description(skill_md: str) -> str:
    return _field(skill_md, "description")


def _skill_name(skill_md: str) -> str:
    return _field(skill_md, "name") or os.path.basename(os.path.dirname(skill_md))


def _listing_budget(settings: list[dict], window: int, env: dict) -> tuple[int, str]:
    """(budget in characters, how it was derived)."""
    fixed = env.get("SLASH_COMMAND_TOOL_CHAR_BUDGET", "").strip()
    if fixed.isdigit() and int(fixed) > 0:
        return int(fixed), "SLASH_COMMAND_TOOL_CHAR_BUDGET"
    fraction = DEFAULT_LISTING_FRACTION
    for data in settings:  # user < project < local
        v = data.get("skillListingBudgetFraction")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 1:
            fraction = float(v)
    return int(window * fraction), f"{fraction:g} of a {window:,}-token window"


def _window(settings: list[dict], override: int | None) -> tuple[int, str]:
    """(context window in tokens, where the figure came from)."""
    if override:
        return override, "--window"
    model = ""
    for data in settings:
        if isinstance(data.get("model"), str):
            model = data["model"]
    if model.endswith("[1m]"):
        return WINDOW_1M, f"model {model}"
    return WINDOW_DEFAULT, f"model {model}" if model else "default"


def _rules(dirpath: str) -> list[str]:
    return sorted(glob.glob(os.path.join(dirpath, "**", "*.md"), recursive=True))


def _skills(dirpath: str) -> list[str]:
    return sorted(glob.glob(os.path.join(dirpath, "*", "SKILL.md")))


def _enabled_plugins(settings: list[dict]) -> list[str]:
    names: list[str] = []
    for data in settings:
        for name, on in (data.get("enabledPlugins") or {}).items():
            if on and name not in names:
                names.append(name)
            if not on and name in names:
                names.remove(name)
    return names


def _plugin_skill_files(spec: str, home: str) -> list[str]:
    if "@" not in spec:
        return []
    plugin, market = spec.split("@", 1)
    base = os.path.join(home, ".claude", "plugins", "cache", market, plugin)
    versions = sorted(d for d in glob.glob(os.path.join(base, "*")) if os.path.isdir(d))
    return _skills(os.path.join(versions[-1], "skills")) if versions else []


def measure(target: str, home: str, window: int | None = None, env: dict | None = None) -> dict:
    env = os.environ if env is None else env
    settings = [_load_json(p) for p in _settings_files(target, home)]
    cap = DEFAULT_DESC_CAP
    for data in settings:  # later files take precedence: user < project < local
        v = data.get("skillListingMaxDescChars")
        if isinstance(v, int) and v > 0:
            cap = v

    def desc_bytes(path: str) -> int:
        return len(_description(path)[:cap].encode("utf-8"))

    rows: list[dict] = []

    def add(category: str, item: str, files: list[str], size_fn) -> None:
        rows.append({"category": category, "item": item, "files": len(files),
                     "bytes": sum(size_fn(f) for f in files)})

    project_md = [p for p in (os.path.join(target, "CLAUDE.md"),
                              os.path.join(target, ".claude", "CLAUDE.md"),
                              os.path.join(target, "CLAUDE.local.md")) if os.path.exists(p)]
    user_md = [p for p in (os.path.join(home, ".claude", "CLAUDE.md"),) if os.path.exists(p)]

    project_skills = _skills(os.path.join(target, ".claude", "skills"))
    user_skills = _skills(os.path.join(home, ".claude", "skills"))
    listed: list[tuple[str, str]] = [("", p) for p in project_skills + user_skills]

    add("project", "CLAUDE.md", project_md, _bytes)
    add("project", ".claude/rules", _rules(os.path.join(target, ".claude", "rules")), _bytes)
    add("project", "skill descriptions", project_skills, desc_bytes)
    add("user", "~/.claude/CLAUDE.md", user_md, _bytes)
    add("user", "~/.claude/rules", _rules(os.path.join(home, ".claude", "rules")), _bytes)
    add("user", "skill descriptions", user_skills, desc_bytes)
    for spec in _enabled_plugins(settings):
        files = _plugin_skill_files(spec, home)
        add("plugins", spec, files, desc_bytes)
        listed += [(spec.split("@", 1)[0] + ":", p) for p in files]

    claude_md_lines = [{"path": p, "lines": _lines(p), "over_guideline": _lines(p) > CLAUDE_MD_LINE_GUIDELINE}
                       for p in project_md + user_md]

    # One listing line per skill, roughly "- <prefix><name>: <description>".
    listing_chars = sum(len(prefix + _skill_name(p)) + len(_description(p)[:cap]) + 4
                        for prefix, p in listed)
    window_tokens, window_source = _window(settings, window)
    budget, budget_source = _listing_budget(settings, window_tokens, env)
    listing = {"skills": len(listed), "chars": listing_chars, "budget_chars": budget,
               "budget_source": budget_source, "window_tokens": window_tokens,
               "window_source": window_source, "over_budget": listing_chars > budget}

    return {"target": target, "desc_cap_chars": cap, "rows": rows,
            "total_bytes": sum(r["bytes"] for r in rows),
            "claude_md_line_guideline": CLAUDE_MD_LINE_GUIDELINE,
            "claude_md_lines": claude_md_lines,
            "skill_listing": listing}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=os.getcwd(), help="repository root (default: cwd)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    ap.add_argument("--window", type=int, default=None,
                    help="context window in tokens for the skill listing budget "
                         "(default: 1000000 when the model setting ends in [1m], else 200000)")
    args = ap.parse_args()
    target = os.path.abspath(args.target)
    result = measure(target, os.path.expanduser("~"), window=args.window)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"always-on context budget for {target} (skill descriptions capped at {result['desc_cap_chars']} chars)")
    print(f"{'category':<9} {'item':<40} {'files':>5} {'bytes':>9}")
    for r in result["rows"]:
        print(f"{r['category']:<9} {r['item']:<40} {r['files']:>5} {r['bytes']:>9,}")
    print(f"{'total':<9} {'':<40} {'':>5} {result['total_bytes']:>9,}")
    if result["claude_md_lines"]:
        print()
        print(f"CLAUDE.md lines (official guideline: under {CLAUDE_MD_LINE_GUIDELINE}):")
        for m in result["claude_md_lines"]:
            flag = "  OVER: move detail to skills or paths-scoped rules" if m["over_guideline"] else ""
            print(f"  {m['lines']:>5}  {m['path']}{flag}")
    s = result["skill_listing"]
    print()
    print(f"skill listing (estimate, built-in skills not counted): {s['skills']} skills, "
          f"{s['chars']:,} of {s['budget_chars']:,} chars "
          f"({s['budget_source']}; window from {s['window_source']})")
    if s["over_budget"]:
        print("  OVER: descriptions of the least-used skills are dropped from the listing; "
              "set low-priority skills to \"name-only\" in skillOverrides or shorten descriptions")
    print("Official audit of instruction files: /doctor prompt-audit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
