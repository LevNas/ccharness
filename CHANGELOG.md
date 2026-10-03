# Changelog

## 0.5.0

After `EnterWorktree`, Claude Code checks each Bash command's literal text and refuses git it cannot show stays inside the worktree: a heredoc or `python3 -c` whose text names git, a variable where an option may stand, a loop, a long chain. Sessions kept hitting the check two or three times in a row with variations of the same form, although the rewrite is the same every time.

- `hooks/worktree_isolation_hint.py` (new), context only:
  - PostToolUse on `EnterWorktree`: once, the forms that are refused and the forms that pass.
  - PostToolUseFailure on Bash: when the error is the isolation refusal ("This session is isolated in the worktree"), the rewrite for that kind of refusal, plus "do not retry a variation of the same form". The kinds come from refusals worded by Claude Code in real sessions: a heredoc or `-c` script (write a file), a value computed at runtime, including `-C` and `cd` targets (spell it out), sed (use Edit), `git -C` to the shared checkout (run git in the worktree, or leave it first), gh with inline text (`--body-file`), and a command too complex to verify (one git command per call).
  - It does not predict the refusal in PreToolUse: the check is Claude Code's own and changes with it, so a guess would block good commands or miss. Fail-open.
- Tests: `tests/test_worktree_isolation_hint.py` (13 checks) with refusal texts worded as in real sessions; no advice suggests `git -C` to another checkout or a shell variable in a path, both of which the check refuses.

## 0.4.0

The end-of-session tidy-up (pull the base branch, check what is left, delete) was done by hand each time and kept going wrong in the same ways: `[gone]` read as merged, a check whose grep returned a false negative, a stale local main, a forgotten branch. The decision is the same for the same input, so it is now computed.

- `scripts/worktree_sweep.py` + `skills/worktree-sweep` (new): from the main checkout, fetch with `--prune`, fast-forward the base branch when it has no local commits and no tracked changes, and classify every local branch and linked worktree:
  - **delete**: an ancestor of `origin/<base>`, or every patch already there per `git cherry` and no merge commits of its own (then `git branch -D` with that proof; git does not check `-D`). Its worktree must have no uncommitted, untracked or ignored files, a working `git status`, and no live lock. Otherwise the commands are `git worktree remove` without `--force` and `git branch -d`, which git refuses if the report is wrong. Names in the commands are shell-quoted.
  - **review**: commits not on the base (with subjects and dates), an open PR (`gh`, optional), files left in the worktree (ignored ones too, since `git worktree remove` deletes those without asking), a lock whose pid is not running.
  - **in-use**: locked by a running process, or checked out in the main checkout.
  - Report only: nothing is deleted. Refuses to run from a linked worktree (exit 2), so a session isolated in a worktree does not read other worktrees around its isolation.
- `session-end-cleanup` template (ja/en): calls `ccharness:worktree-sweep`. The manual fallback no longer treats an upstream marked `[gone]` as safe to delete; it decides by `--is-ancestor`, then `git cherry`, and checks ignored files.
- Tests: `tests/test_worktree_sweep.py` (31 checks) builds a bare remote, a main checkout that has fallen behind and worktrees for each case (including a branch with its own merge commit, a worktree whose `git status` fails, a detached worktree, a path with a space, a tag named like a branch, and a `master` base with no remote), and checks each classification, the fast-forward, and that no branch or worktree disappears.

## 0.3.1

The skill listing does not come back after compaction (https://code.claude.com/docs/en/context-window, "What survives compaction"): only the bodies of invoked skills are re-injected. A skill that has not been used yet in the session is then out of Claude's sight unless something re-injected names it.

- CLAUDE.md snippet (ja/en): the `Compact Instructions` section names `arc-handoff` (arc boundary) and `session-wrap` (end of session), so both stay usable after compaction. Snippet marker v0.3.1.
- `rules-and-skills-layering` (ja/en): the mid-session note says the listing does not come back and that skills needed after compaction are named in CLAUDE.md or rules.
- `arc-handoff` (ja/en): the background notes the same and that `/arc-handoff` works by name.

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
