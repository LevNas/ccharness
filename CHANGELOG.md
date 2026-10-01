# Changelog

## 0.3.0

Long-session support (#3): prose and skills only, no new hook. Restoring state after compaction belongs to the plugin that owns the state (ccmemo 1.29).

- CLAUDE.md snippet (ja/en): a `Compact Instructions` section — keep modified files and uncommitted state, the unfinished checklist and issue / PR numbers, test and build commands with the latest result, and decisions made only in conversation. Snippet marker now v0.3.0.
- `arc-handoff` skill template (ja/en): at the boundary between two arcs of one session, write the state to the issue, task file or knowledge base, then hand the user a `/compact` line naming the next arc; `/rename` + `/clear` for unrelated work, `session-wrap` to end the session. Key steps sit at the top because only the first 5,000 tokens of a skill come back after compaction.
- `rules-and-skills-layering` (ja/en): a "mid-session edits" section — editing CLAUDE.md or rules keeps the cache but applies only at the next `/compact`, `/clear` or restart; only what is in files survives compaction.
- harness-budget: the skill listing estimated against its official budget (1% of the context window in characters; `skillListingBudgetFraction`, `SLASH_COMMAND_TOOL_CHAR_BUDGET`; `--window`, else 1M for a `[1m]` model, else 200k), with advice when over; points to `/doctor prompt-audit`.
- Tests: `tests/test_measure.py` (new); `tests/test_scaffold.sh` checks the new skill and snippet section in both languages.

## 0.2.2

- local-workspace-files (rule and skill templates, ja/en): carry gitignored files into worktrees with the official `.worktreeinclude` instead of copying by hand; document the skills read-through from the main checkout and `worktree.baseRef`; add `.claude/worktrees/` to the suggested `.gitignore`.
- harness-budget: CLAUDE.md line counts against the official 200-line guideline; a review step for unused instructions using `/context` and `/usage` attribution.

## 0.2.1

- SKILL.md frontmatter: `license` and `allowed-tools` on the plugin skills and on every scaffold skill template, as the levnas-plugins marketplace lint requires.

## 0.2.0

- Scaffold: behaviour skills as repository-owned copies under `.claude/skills/` (`session-wrap`, `session-end-cleanup`, `dev-shipper`, `pre-work-verification`, `local-workspace-files` detail; ja/en). Never overwritten; marker inserted after the frontmatter; `--no-skills` to skip. The plugin itself still ships only `scaffold` and `harness-budget`.
- Repository hygiene: `.gitignore` for `__pycache__`; tracked `.pyc` files removed.

## 0.1.0

- Scaffold: `scripts/scaffold.sh` and the `scaffold` skill copy rule templates into `.claude/rules/` with a version marker and never overwrite; create `.claude/settings.json` with the standard-tier `permissions.deny` rules when absent, otherwise list the missing rules; hand the `CLAUDE.md` snippet to the user for approval.
- Templates: `tool-call-resilience`, `discussion-phase-restraint`, `rules-and-skills-layering`, `local-workspace-files` (ja/en) and `tone` (ja); `CLAUDE.md` snippet (ja/en); `settings.snippet.json` (deny rules for force push, `reset --hard`, `clean -f`, worktree-discarding checkout/restore, `chmod -R 777`).
- Hook: `pretool_bash_guard.py` (PreToolUse/Bash) is the hard-deny floor only: `rm -r` on root/home/cwd/parent/glob (also via `/bin/rm`, `sudo`, `xargs`, `timeout`, `bash -c`), fork bomb, `mkfs`, `dd`/redirect onto a block device, `shred`. No plugin-specific switch: use `disableAllHooks` or `enabledPlugins`.
- Budget: `scripts/measure_always_on.py` and the `harness-budget` skill report always-on context bytes per category, with skill descriptions capped at `skillListingMaxDescChars`.
- Tests: `tests/test_bash_guard.py` (floor, protocol, deny-rule snippet), `tests/test_scaffold.sh`.
