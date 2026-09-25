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

Usage: measure_always_on.py [--target DIR] [--json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

DEFAULT_DESC_CAP = 1536


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


def _description(skill_md: str) -> str:
    try:
        with open(skill_md, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    dm = re.search(r"^description:\s*(.*?)(?=^\S|\Z)", m.group(1), re.S | re.M)
    return dm.group(1).strip() if dm else ""


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


def measure(target: str, home: str) -> dict:
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

    add("project", "CLAUDE.md", [p for p in (os.path.join(target, "CLAUDE.md"),
                                           os.path.join(target, ".claude", "CLAUDE.md"),
                                           os.path.join(target, "CLAUDE.local.md")) if os.path.exists(p)], _bytes)
    add("project", ".claude/rules", _rules(os.path.join(target, ".claude", "rules")), _bytes)
    add("project", "skill descriptions", _skills(os.path.join(target, ".claude", "skills")), desc_bytes)
    add("user", "~/.claude/CLAUDE.md", [p for p in (os.path.join(home, ".claude", "CLAUDE.md"),) if os.path.exists(p)], _bytes)
    add("user", "~/.claude/rules", _rules(os.path.join(home, ".claude", "rules")), _bytes)
    add("user", "skill descriptions", _skills(os.path.join(home, ".claude", "skills")), desc_bytes)
    for spec in _enabled_plugins(settings):
        add("plugins", spec, _plugin_skill_files(spec, home), desc_bytes)

    return {"target": target, "desc_cap_chars": cap, "rows": rows,
            "total_bytes": sum(r["bytes"] for r in rows)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=os.getcwd(), help="repository root (default: cwd)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args()
    target = os.path.abspath(args.target)
    result = measure(target, os.path.expanduser("~"))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"always-on context budget for {target} (skill descriptions capped at {result['desc_cap_chars']} chars)")
    print(f"{'category':<9} {'item':<40} {'files':>5} {'bytes':>9}")
    for r in result["rows"]:
        print(f"{r['category']:<9} {r['item']:<40} {r['files']:>5} {r['bytes']:>9,}")
    print(f"{'total':<9} {'':<40} {'':>5} {result['total_bytes']:>9,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
