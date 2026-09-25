---
name: harness-budget
description: Measure the always-on context budget in bytes (CLAUDE.md, .claude/rules, skill descriptions of project, user and enabled plugins, capped at skillListingMaxDescChars). Use during periodic review, after scaffolding, or whenever rules feel bloated, to report the delta and decide what moves to a skill.
license: MIT
allowed-tools: Bash, Read
---

# Harness budget

Always-on content is a budget, not a folder. This skill produces the number so the rule "measure and report the delta" does not depend on memory.

## Steps

1. Measure from the repository root:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/measure_always_on.py"
   ```

   Add `--json` for machine-readable output, `--target DIR` for another repository.
2. Compare with the previous figure if one is recorded (periodic review notes, an issue, the knowledge base). Report the delta per category.
3. If the always-on side grew, re-apply the question "would starting work without this rule cause an accident?" to each new or grown file. Anything that fails moves to `.claude/skills/`. Propose the move; do not reshuffle on your own.

## What the number covers

| Category | Counted |
|---|---|
| project | `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/**/*.md`, descriptions of `.claude/skills/*/SKILL.md` |
| user | `~/.claude/CLAUDE.md`, `~/.claude/rules/**/*.md`, descriptions of `~/.claude/skills/*/SKILL.md` |
| plugins | descriptions of skills shipped by enabled plugins (from `enabledPlugins` in user, project and local settings) |

Skill bodies are excluded because they load only when used. Each description is capped at the official `skillListingMaxDescChars` setting (default 1536 characters), which is what Claude actually sees in the skill listing. Files imported with `@path` from CLAUDE.md are not followed; count them by hand if you use imports heavily.
