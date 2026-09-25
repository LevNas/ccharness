---
name: scaffold
description: Scaffold ccharness into a repository - always-on rule templates into .claude/rules/, behaviour skills into .claude/skills/, standard-tier permissions.deny rules into .claude/settings.json, and the CLAUDE.md snippet for the user to approve. Use when setting up a new repository's harness or when asked to scaffold ccharness. Never overwrites.
license: MIT
allowed-tools: Bash, Read, Edit
---

# Scaffold

Puts the always-on part of the harness into the target repository using only official files (`.claude/rules/`, `.claude/settings.json`, `CLAUDE.md`). Everything that must be in the repository (because a session that does not know it would cause an accident) is scaffolded; everything else stays in this plugin as a lazily loaded skill.

## Steps

1. Dry run from the repository root and show the plan to the user:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.sh" --lang ja --dry-run
   ```

   Use `--lang en` for English templates (`tone.md` is Japanese-only), `--target DIR` when not at the repository root, `--no-settings` to leave `.claude/settings.json` alone, `--no-skills` to skip the behaviour skills.
2. Existing rule files and skills are never overwritten. A "differs" diff (truncated to 20 lines; the full command is printed) is information for the user, not something to resolve automatically.
3. Run the same command without `--dry-run`.
4. `.claude/settings.json`: when the file did not exist, the scaffold created it with the standard-tier `permissions.deny` rules. When it existed, the scaffold printed the rules that are missing; add them only with the user's approval (an Edit to the existing file, keeping everything else).
5. `CLAUDE.md` is a shared file. Read `templates/CLAUDE.md.snippet.<lang>.md`, present it, and append it only after the user explicitly approves. Never edit CLAUDE.md on your own.
6. Propose `.gitignore` entries for local workspace files if they are missing: `.claude/tasks/`, `.claude/private/`, `.claude/settings.local.json`.
7. Report what was created and skipped, and the always-on budget after scaffolding (`ccharness:harness-budget`).

## Rules of thumb

- Only content that causes an accident if unknown goes into `.claude/rules/`. Anything that can be read once the work starts stays a skill.
- Command blocking that a permission rule can express goes into `permissions.deny` (official engine, per repository). The plugin hook keeps only the hard-deny floor.
- Behaviour skills are scaffolded, not shipped by the plugin: each repository adapts them (issue tracker, knowledge base, branch names), and their descriptions count against that repository's always-on budget only where they are wanted.
- Hooks are not scaffolded: the plugin registers them itself, so updates arrive with plugin updates.
- Deterministic enforcement of secrets, AI attribution and self-modification belongs to ccguard, not here.
- User-wide style belongs in `~/.claude/CLAUDE.md` and `~/.claude/rules/`, not in a repository; personal per-project notes go in `CLAUDE.local.md`.
