# Changelog

## 0.2.0 (unreleased)

- Scaffold: behaviour skills as repository-owned copies under `.claude/skills/` (`session-wrap`, `session-end-cleanup`, `dev-shipper`, `pre-work-verification`, `local-workspace-files` detail; ja/en). Never overwritten; marker inserted after the frontmatter; `--no-skills` to skip. The plugin itself still ships only `scaffold` and `harness-budget`.
- Repository hygiene: `.gitignore` for `__pycache__`; tracked `.pyc` files removed.

## 0.1.0

- Scaffold: `scripts/scaffold.sh` and the `scaffold` skill copy rule templates into `.claude/rules/` with a version marker and never overwrite; create `.claude/settings.json` with the standard-tier `permissions.deny` rules when absent, otherwise list the missing rules; hand the `CLAUDE.md` snippet to the user for approval.
- Templates: `tool-call-resilience`, `discussion-phase-restraint`, `rules-and-skills-layering`, `local-workspace-files` (ja/en) and `tone` (ja); `CLAUDE.md` snippet (ja/en); `settings.snippet.json` (deny rules for force push, `reset --hard`, `clean -f`, worktree-discarding checkout/restore, `chmod -R 777`).
- Hook: `pretool_bash_guard.py` (PreToolUse/Bash) is the hard-deny floor only: `rm -r` on root/home/cwd/parent/glob (also via `/bin/rm`, `sudo`, `xargs`, `timeout`, `bash -c`), fork bomb, `mkfs`, `dd`/redirect onto a block device, `shred`. No plugin-specific switch: use `disableAllHooks` or `enabledPlugins`.
- Budget: `scripts/measure_always_on.py` and the `harness-budget` skill report always-on context bytes per category, with skill descriptions capped at `skillListingMaxDescChars`.
- Tests: `tests/test_bash_guard.py` (floor, protocol, deny-rule snippet), `tests/test_scaffold.sh`.
