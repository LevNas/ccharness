# Changelog

## 0.9.1

The worktree isolation hint described the check as narrower than it is. Replaying every isolation refusal in one user's session transcripts (150 refused Bash commands) showed that 83 of them ran no git at all: the check refuses chains, heredocs, `python3 -c`, variables and loops whether or not git is involved, and it counts `git` inside another word (a `github.com` path) once the command is not a single plain one. The hook still answered most of those with "one git command per call" (74 of the 83). Refusals fell from 4–25 a day to 2–3 a day after 0.5.0 added the hook; this targets the rest.

- `hooks/worktree_isolation_hint.py`: on a refusal, the rewrite is now also chosen from the refused command (`tool_input.command`, which the PostToolUseFailure input carries; at most the first 8,000 characters are scanned, so a huge command cannot stall the hook):
  - a heredoc (not `<<<`, not `<<` inside quotes), `python3 -c` / `python3 -`, `node`/`perl`/`ruby -e` or `bash -c` → the script-file rewrite;
  - `$(...)`, `${...}`, `$NAME`, `$?`, `$1`, a leading `NAME=` or a `for`/`while`/`until` … `do` loop → the literal-values rewrite (`$NF` inside single quotes, as in awk, and `-f title=x` arguments do not count);
  - quoted text naming git passed to `gh` or `tmux` → the file rewrite;
  - no `git` command in the text → a note that the check refuses such commands too (saying when the command contains `github.com`), in place of the general split rewrite, which speaks of git. `git` counts as a command when it stands alone or as a path or helper (`/usr/bin/git`, `git-lfs`), not inside `.git`, `.gitignore`, `legit`, `digit` or `github`. The test errs towards "git": a false "git" only drops the note.

  Without a usable `tool_input`, the refusal's words alone choose, as before.
- The general rewrite no longer says "one git command per call": it says to split into plain commands, one per call, and to put several steps in a script file. A refusal worded "runs tmux with the text" now gets the file rewrite instead of the general one.
- The entry hint says the check refuses forms whether or not they run git, and that a `github.com` path counts.
- On the replayed refusals, the new hook gives the no-git note for 83 commands. Checked independently of the hook's own test: 74 of them contain no `git` outside `github`; the other 9 were read by hand (`digit`, `.gitignore`, `.git` paths, a file name with `git-` in it) and none runs git. 0.9.0 told 74 of those 83 "one git command per call"; this release tells none, and never gives the no-git note together with the git split advice.
- Tests: refusals and commands from real sessions (paths replaced), git by path and helper, words that contain `git`, single-quoted `$`, here-strings, huge one-line commands, and payloads without `tool_input` or with a non-string one. 13 of the file's 27 tests fail on 0.9.0.

## 0.9.0

The leaf agent catalog, the parallel worktree skill, the tier guard and the agent ledger move here from ccorch (0.4.0). The two plugins are re-split by axis: ccharness is how work is distributed INSIDE one session (who does a step: script, least-privilege subagent or main session; at what cost: model and effort pinned per leaf type; cleanup). ccorch keeps only the splitting of work into SEPARATE sessions (`/ccor` panes). A second reason: ccorch's `/ccor-parallel` cleaned up with `git worktree remove --force` and `git branch -D`, which contradicts `worktree-sweep` (no `--force`; `-D` only with proof). With the skill here, one cleanup path wins.

- `agents/` (new): `web-research`, `web-refuter`, `log-distiller`, `kb-integrator`, `knowledge-recorder`, `pbr-reviewer`, `worktree-worker`, `impl-verifier`, copied from ccorch with their model, effort and tools frontmatter unchanged (types are `ccharness:<name>`). `web-research`'s description now says to fetch a single page directly with WebFetch.
  - `url-extract` is retired and not carried over. WebFetch's tool description states that it answers through a small fast model, so a haiku wrapper around it would summarize twice and add the cost of a spawn.
- `skills/parallel-worktree` (new, rebuilt from `/ccor-parallel`): origin pinning, waves, capture preservation, `--no-ff` integration worktree, as before, with these changes:
  - the parallel limit is the official `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (the plugin adds no cap);
  - Phase 2 also lists ignored files, since `worktree-sweep` classes a worktree that holds them as review;
  - Phase 4 is replaced: the integration branch is pushed from inside its worktree (`ship push` pushes the current branch, and the orchestrator sits on the base branch in the main checkout), opened as a PR and merged through the repository's merge flow (review, then merge on the user's word, with a merge commit). Worker worktrees and branches are removed only through `worktree-sweep`'s delete-class commands, on the user's word. Every `--force` and `git branch -D` instruction is gone: worker branches merged with `--no-ff` into an integration branch that is merged into the base become ancestors of the base, so the sweep classifies them as delete, with git's own refusal as the last check;
  - a "Later" note: Phase 0 and the Phase 3 checks give the same answer every time and are candidates for a script, as `ship` is.
- `hooks/agent_tier_guard.py` (new), PreToolUse on `Agent|Task`: for a `ccharness:<type>` of the catalog, denies a `model` override more than one tier above the pinned tier (haiku 1, sonnet 2, opus 3, fable and mythos 4; an unknown model name is denied; `inherit` and empty are allowed). The pinned tier is read from the `model:` line of `agents/<type>.md` on every call, so it cannot drift from the frontmatter; a type is a catalog type when that file exists. An unreadable file or a file without a `model:` line allows. Off switch: `CCHARNESS_TIER_GUARD=off`.
- `hooks/agent_ledger.py` (new), PostToolUse on `Agent|Task` and SubagentStop: one JSON line per launch and stop (schema `ccharness.ledger/1`) in `<main checkout>/.claude/ccharness/ledger.jsonl`. The main checkout is resolved from `git rev-parse --git-common-dir`, because a ledger written inside a linked worktree is an ignored file there, and `worktree-sweep` classes a worktree with ignored files as review, so every worktree that spawned an agent would stop being delete-class. Prompt bodies are never recorded. See `docs/ledger.md`; add `.claude/ccharness/` to the `.gitignore` of every repository that uses it (this repository does).
- Ledger details: the main checkout is the parent of the git common dir only when that dir is named `.git` (otherwise `git rev-parse --show-toplevel`, then `CLAUDE_PROJECT_DIR`), only an existing directory is ever used (a removed worker worktree is not recreated; with no existing candidate nothing is written), `agent_id` is the last `agentId:` match in the response, `background` is `run_in_background` as given (null when absent), and `stop_reason` is kept but null when the SubagentStop input has none.
- `parallel-worktree`: BASE is the commit hash recorded in Phase 0 (the base branch may move during a wave), and a wave has at most 3 workers whatever the settings say, fewer when `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` is lower.
- While ccorch 0.4.0 is still installed alongside, each spawn is recorded in both ledgers (harmless), and ccorch's `/ccor-parallel` (which still uses `--force` and `branch -D`) and its tier guard overlap with this release. ccorch 0.5.0 removes them; until then use `parallel-worktree`.
- Tests: `tests/test_agent_tier_guard.py`, `tests/test_agent_ledger.py`.

## 0.8.0

The steps after implementation (stage, commit, push, check the PR) give the same answer every time, yet hand-written versions kept failing: `git add -A` refused by a commit-scope rule, compound git commands refused by the worktree isolation check, several calls strung together per PR. They are now a script.

- `scripts/ship.py` (new; Python 3 stdlib only, every git/gh call an argument list, no shell):
  - `commit --files F [F ...] --message-file M [--scan-patterns P]`: refuses on the default branch (`origin/HEAD`, falling back to main/master) and during a merge or rebase; stages each listed path by name (a deleted path as a removal; never `git add -A` or `.`); the staged set must equal the listed set, otherwise it prints both and stops without unstaging; scans the added lines of the staged diff for private key headers, common token prefixes and quoted `password|secret|token` values, plus extra regexes from `--scan-patterns` (one per line, `#` comments). A hit prints file, line and pattern name only, never the matched text, and nothing is committed. Then `git commit -F M` and the new short SHA.
  - `push`: refuses on the default branch; `git push -u origin <branch>`; never `--force`, never `--no-verify`, so a pre-push hook keeps running.
  - `check [--pr N] [--expect-files F ...] [--wait SECONDS]`: read-only `gh pr view`; polls while `mergeable` is UNKNOWN (default 30 s); one summary line; exit 0 only for OPEN, MERGEABLE, CLEAN (a draft also accepts DRAFT; BLOCKED is never ready, it also means failing or pending checks), head equal to local HEAD and, when given, files equal to the expected files. GitHub only; GitLab is not covered yet.
  - Hardening: the scan reads one `git --literal-pathspecs diff --cached ... -- <path>` per path from the `-z` staged list and takes only hunk headers and `+` lines, crediting its own path (no path is parsed from diff text, so quoted names, `diff.noprefix`, `diff.mnemonicPrefix` and added lines beginning `++ ` cannot hide a file); output is decoded with `errors="replace"`. The default branch is the union of the `origin/HEAD` target, main and master. `push` uses `refs/heads/<b>:refs/heads/<b>`. Paths are literal pathspecs, resolved with `realpath` and checked by components. `check` has a timeout on every `gh` call, rejects non-finite `--wait` and keeps polling while the PR head differs from local HEAD.
  - It does not create or post the PR: a `gh pr create` inside a script would hide its title and body from PreToolUse guards that check what gh posts.
- `skills/ship` (new): when to use it and the order commit → push → plain `gh pr create --body-file` → check, the exit codes, and that merging stays with the user.
- Tests: `tests/test_ship.py` (temporary repositories with a local bare remote; `gh` replaced by a stub on PATH).

## 0.7.0

Parallel work is split into stacked worktrees: worktree 1 from main, worktree 2 from worktree 1, and worktree 2's PR is merged into worktree 1's branch with `gh pr merge`. After that merge the parent branch has to be brought up to date where it is checked out, and the child branch is not an ancestor of the default branch, so the sweep only ever called it "review". `worktree-sweep` knew only the default branch.

- `scripts/worktree_sweep.py`:
  - After the base sync, every linked worktree whose branch has an upstream that exists after the fetch is fast-forwarded in that worktree when it is behind, has no commits of its own and no tracked changes, and is not locked by a live process (note: `<branch> fast-forwarded N commit(s) in <path>`). Locked by a live process: nothing runs, the note carries `git -C <path> merge --ff-only <upstream>` (or `git pull --ff-only` from inside it). Ahead and behind, tracked changes, a failed fast-forward: a note. No upstream: skipped. `--no-pull` turns all of it into notes.
  - `gh` is asked for `baseRefName` too. A branch that is not merged into `origin/<base>` but whose PR is MERGED into another branch, with `origin/<that branch>` existing and containing it, is **delete**, with `merged: ancestor of origin/<parent> (PR #N base)` and `git branch -D <branch>  # ancestor of origin/<parent>; -d compares with HEAD or a gone upstream and refuses`. If `origin/<parent>` is gone the existing comparison with `origin/<base>` applies; nothing is guessed.
- `hooks/post_merge_cleanup_hint.py`: the hint gives two cases, since the hook cannot tell which applies: in the merged branch's worktree (check files, ExitWorktree keep, `worktree-sweep` from the main checkout); in the PR's base branch's worktree (`git pull --ff-only` there). It says that `worktree-sweep` also fast-forwards the PR's base branch, or prints the command when that worktree is in use. "Session captures" is replaced by a generic phrase.
- `templates/skills/{ja,en}/session-wrap`: also triggered by a merge-time review returning pass or fail. On fail: record the verdict, the blocking findings, the next step and the number of fix rounds on a separate branch and PR into the default branch, not on the feature branch. A session-wrap's own branch or PR is never wrapped again.
- Tests: `tests/test_worktree_sweep_stacked.py` (temporary repositories: bare origin, clones, worktrees; `gh` replaced by a stub of `open_pr`), and the hint tests.

## 0.6.0

The tidy-up after a merge (leave the worktree, update the base, remove what is left) is computed by `worktree-sweep`, whose description says "after a merge", yet in real sessions it was never called: five merges in a row were cleaned up by hand, and the skill listing does not come back after compaction. Prose cannot create the moment to call it, so a hook does.

- `hooks/post_merge_cleanup_hint.py` (new), PostToolUse on Bash, context only: when one simple command of the Bash command (`shlex`, split at `;`, `&&`, `||`, `|`, `&`, newline) is `gh` [options] `pr` [options] `merge`, it returns the cleanup steps: check the worktree for uncommitted or untracked files, leave it with ExitWorktree (action keep), run `worktree-sweep` from the main checkout, run its delete-class commands only when the user says so and never with `--force`.
  - `--auto` and `--disable-auto` in that command give no hint (nothing was merged). Success is not checked: PostToolUse fires only on exit 0. The tool result is not read, since its field name differs between sources.
  - It does not run `worktree_sweep.py`: the session is usually in a linked worktree, which the script refuses, and the script fetches and fast-forwards, side effects a hook should not have. It deletes nothing. Fail-open.
- `worktree-sweep` description: says that the post-merge hint calls it.
- Tests: `tests/test_post_merge_cleanup_hint.py`.

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
