# ccharness

Harness for Claude Code: ship-time rules and guards for a repository, and the pieces that decide how work is distributed inside one session (a leaf agent catalog with pinned models, parallel worktrees, cleanup). It puts the behavioural rules that every session must know into the repository, blocks the few shell commands that must never run from an agent session, and keeps the rest as lazily loaded skills.

**Official first.** Wherever Claude Code already has a setting, an environment variable, a CLI flag or a memory mechanism for a job, ccharness uses it instead of a custom one. The plugin adds only what has no official equivalent.

## Why

Claude Code plugins cannot load a `CLAUDE.md` or `.claude/rules/` on their own: the only plugin components are skills, agents, hooks, MCP and LSP servers. Anything that must be in effect before work starts therefore has to live in the repository. ccharness scaffolds exactly that content, and nothing more:

- **Rules that cause an accident if unknown** are scaffolded into `.claude/rules/` (always-on).
- **Opinionated command blocking** is scaffolded as official `permissions.deny` rules into `.claude/settings.json` (per repository, committed, opt-in).
- **Behaviour skills** (session wrap-up, branch cleanup, Definition of Done, pre-work verification, local workspace files) are scaffolded into `.claude/skills/` so each repository owns and adapts them, and the plugin's always-on cost stays at the skill and agent descriptions (measure it with `harness-budget`).
- **Everything else** ships as plugin skills whose bodies load only when used.
- **Hooks** stay few: the hard-deny floor for the handful of commands a deny rule cannot express, two small hints around worktrees and merges, and, for the agent catalog, a tier guard and a ledger.
- **A leaf agent catalog** (below) pins the model and effort per leaf type, so how much a delegated step costs is decided by the definition, not by the main session's model.

The split follows one question: *would starting work without knowing this cause an accident?*

## What you get

| Component | Kind | Purpose |
|---|---|---|
| `scripts/scaffold.sh` + `skills/scaffold` | scaffold | Copy rule templates into `.claude/rules/` (never overwrites), create or complete `permissions.deny` in `.claude/settings.json`, hand the `CLAUDE.md` snippet to the user |
| `templates/rules/{ja,en}/` | templates | `tool-call-resilience`, `discussion-phase-restraint`, `rules-and-skills-layering`, `local-workspace-files`; `tone` (Japanese only) |
| `templates/skills/{ja,en}/` | templates | `session-wrap`, `arc-handoff` (switch arcs inside one long session), `session-end-cleanup`, `dev-shipper`, `pre-work-verification`, `local-workspace-files` (detail) - copied to `.claude/skills/` once, then owned by the repository (`--no-skills` to skip) |
| `templates/settings.snippet.json` | template | Standard-tier deny rules: force push, `reset --hard`, `clean -f`, worktree-discarding checkout/restore, `chmod -R 777` |
| `templates/CLAUDE.md.snippet.{ja,en}.md` | template | Workflow Rules, Response Quality, Safety, Output Approach, Host Resource Constraints, Compact Instructions |
| `hooks/pretool_bash_guard.py` | PreToolUse(Bash) hook | Hard-deny floor: `rm -r` on root/home/cwd/glob (also as `/bin/rm`, `sudo rm`, `bash -c`), fork bomb, `mkfs`, `dd`/redirect onto a block device, `shred` |
| `hooks/worktree_isolation_hint.py` | PostToolUse(EnterWorktree), PostToolUseFailure(Bash) hook | For a session isolated in a worktree: once on entry, the Bash forms that Claude Code's isolation check most often refuses (with measured rates) and the forms that pass; on a refusal, the rewrite for that kind, chosen from the refusal's words and the refused command's form (script file, literal values, Edit instead of sed, no `-C` to another checkout, `gh --body-file`, one plain command per call, and a note when the command runs no git, since the check also refuses those). Adds context only; never blocks or predicts the check |
| `hooks/post_merge_cleanup_hint.py` | PostToolUse(Bash) hook | After `gh pr merge` (not with `--auto` / `--disable-auto`): the cleanup order for two cases (in the merged branch's worktree: check for uncommitted files, ExitWorktree keep, `worktree-sweep` from the main checkout; in the PR's base branch's worktree, a stacked parent: `git pull --ff-only`), delete only when the user says so, never `--force`. Adds context only; runs and deletes nothing |
| `scripts/worktree_sweep.py` + `skills/worktree-sweep` | inventory | Run from the main checkout: fetch, fast-forward the base branch and every linked worktree's branch that is behind its upstream when that loses nothing (a worktree in use by a live session only gets the command printed), and classify local branches and worktrees as delete (merged by ancestry, `git cherry`, or a PR merged into a parent branch that contains it; nothing uncommitted, untracked or ignored left), review (with the reason) or in-use. Report only; `session-end-cleanup` calls it |
| `scripts/ship.py` + `skills/ship` | script + skill | After implementation: `commit` (listed files staged by name, staged set must equal the list, secret scan of added lines with optional `--scan-patterns`, refuses on the default branch), `push` (`-u origin <branch>`, never force or `--no-verify`), `check` (read-only PR summary: open, mergeable, clean, head and files match; GitHub only). The PR itself is created by a plain `gh pr create --body-file` between `push` and `check`, so PreToolUse guards see its title and body. Never merges |
| `agents/` | agent catalog | Eight leaf agent types with model, effort and tools pinned in the frontmatter; see [Agent catalog](#agent-catalog) |
| `hooks/agent_tier_guard.py` | PreToolUse(Agent\|Task) hook | For a `ccharness:<type>` of the catalog: denies a `model` override more than one tier above the model pinned in `agents/<type>.md` (haiku 1, sonnet 2, opus 3, fable and mythos 4; unknown model names are denied; `inherit` is allowed). The pinned tier is read from the frontmatter on every call. Off: `CCHARNESS_TIER_GUARD=off` |
| `hooks/agent_ledger.py` | PostToolUse(Agent\|Task) and SubagentStop hook | One JSON line per agent launch and stop in `<main checkout>/.claude/ccharness/ledger.jsonl` (resume handles; never prompt bodies). Add `.claude/ccharness/` to `.gitignore`. See [docs/ledger.md](docs/ledger.md) |
| `skills/parallel-worktree` | skill | Fan out file-disjoint tasks to `ccharness:worktree-worker` agents in worktrees (the limit is the official `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`), merge them with `--no-ff` in an integration worktree, ship that branch as a PR through the merge flow, and clean up only through `worktree-sweep` (no `--force`, no `git branch -D`) |
| `scripts/measure_always_on.py` + `skills/harness-budget` | measurement | Bytes of always-on context: CLAUDE.md, rules, skill descriptions (capped at `skillListingMaxDescChars`) across project, user and enabled plugins; CLAUDE.md line counts against the official 200-line guideline; the skill listing estimated against its budget (1% of the context window in characters) |

## Agent catalog

Leaf agents for steps that do not need the main session's model. Each is a `ccharness:<type>` subagent type; model, effort and tools are pinned in `agents/<type>.md`. The orchestrator gives a closed task and judges the result; a leaf never judges its own quality. If a leaf's output fails acceptance, re-run it one tier up, at most once (the tier guard denies a larger jump).

| Type | Purpose | Model | Effort |
|---|---|---|---|
| `web-research` | Questions needing three or more web sources; returns a cited digest | sonnet | low |
| `web-refuter` | Hunts for disconfirming evidence for a decision-grade claim | sonnet | high |
| `log-distiller` | Reduces test, build and log output to the lines that matter (read-only) | haiku | low |
| `kb-integrator` | Integrates ten or more knowledge-base entries into a cited synthesis map (read-only) | sonnet | medium |
| `knowledge-recorder` | Drafts knowledge-base entries the caller has already decided to record | sonnet | medium |
| `pbr-reviewer` | Reviews a document set through one assigned perspective | sonnet | medium |
| `worktree-worker` | One closed implementation task in an isolated worktree, with a file-ownership list | sonnet | low |
| `impl-verifier` | Runs the named checks against acceptance criteria and reports evidence; never fixes | sonnet | medium |

A single known URL needs no leaf: fetch it directly with WebFetch. The former `url-extract` leaf is retired, since WebFetch's tool description states that it answers through a small fast model, so a haiku wrapper would summarize twice and add the cost of a spawn.

These came from ccorch (0.4.0), which, if installed, keeps the `/ccor` tmux panes for splitting work into separate sessions. While ccorch 0.4.0 is still installed alongside, each spawn is recorded in both ledgers (harmless), and its `/ccor-parallel` (which still uses `--force` and `branch -D`) and its tier guard overlap with this release; ccorch 0.5.0 removes them, and until then use `parallel-worktree`.

Scaffolded rule files start with a marker line, `<!-- ccharness template v0.2.0 (ja) -->` (skills carry it right after the frontmatter), so a later version can be diffed against what is in the repository. Updates are proposed as diffs; the scaffold never overwrites.

## Install

```
/plugin marketplace add LevNas/claudecode-plugins
/plugin install ccharness@levnas-plugins
```

Then, in the repository you want to set up, ask Claude Code:

> Scaffold ccharness into this repository (Japanese templates).

or run the script directly. Always look at the dry run first; the real run creates `.claude/rules/*.md` and, when the file is absent, `.claude/settings.json`:

```bash
S=~/.claude/plugins/cache/levnas-plugins/ccharness/<version>/scripts/scaffold.sh
bash "$S" --lang ja --dry-run   # review the plan
bash "$S" --lang ja             # then create
```

When `.claude/settings.json` already exists (for example with `permissions.allow` rules), the scaffold never rewrites it. It prints the deny rules that are missing, and you add them under `permissions.deny` next to what is there:

```json
{
  "permissions": {
    "allow": ["Bash(npm test *)", "Bash(git status)"],
    "deny": ["Bash(git push --force *)", "Bash(git reset --hard*)"]
  }
}
```

## Two tiers of command blocking

| Tier | Mechanism | Scope | What it stops |
|---|---|---|---|
| Floor | plugin hook `pretool_bash_guard.py` | every repository where the plugin is enabled | `rm -r` on `/`, `~`, `$HOME`, `.`, `..`, `*`, a top-level path or `/home/<user>`; the same via `/bin/rm`, `sudo`, `xargs`, `timeout`, `bash -c`; fork bomb; `mkfs`; `dd`/`>` onto a block device; `shred` |
| Standard | `permissions.deny` rules from `templates/settings.snippet.json` | the repositories you scaffolded | `git push --force` / `-f` / `+refspec` / `--delete`, `git reset --hard`, `git clean -f`, `git checkout -- .`, `git restore .`, `chmod -R 777` |

The standard tier is opinionated. `git clean -f` in particular also stops routine cleanup of ignored build output; if your team runs it as a normal step, delete that rule from `.claude/settings.json` and the scaffold will not add it back. The scope is git and recursive chmod only: a single-file `chmod 777` is not blocked.

The standard tier uses Claude Code's own rule engine, which already splits compound commands, matches deny rules on any subcommand (including `$()` and loop bodies), strips wrappers such as `timeout` and `nice`, and looks past leading variable assignments. What it does not match, by the official reference's own account, is the same program in another form (`/bin/rm`, `bash -c '...'`, `git -C . push`); that is why the floor is a hook and why it stays small. Hook decisions never override deny rules, and an exit-2 hook blocks before allow rules are considered. See [Configure permissions](https://code.claude.com/docs/en/permissions).

`git push --force-with-lease` and `git restore --staged .` are deliberately not in the deny list.

### Turning things off (official settings only)

- One repository: `"enabledPlugins": {"ccharness@levnas-plugins": false}` in that repository's `.claude/settings.json` or `.claude/settings.local.json`.
- Every hook, temporarily: `"disableAllHooks": true` in a settings file, or `claude --settings '{"disableAllHooks": true}'` for one run.
- A deny rule you do not want: remove it from `.claude/settings.json`; the scaffold will only report it as missing, never re-add it.

The one ccharness-specific switch is `CCHARNESS_TIER_GUARD=off`, which turns off the agent tier guard only (for example in the `env` block of a settings file).

### Ownership: ccharness vs ccguard

| Concern | Owner |
|---|---|
| Destructive filesystem / block-device operations that need target analysis | ccharness floor hook |
| Opinionated git / chmod blocking | ccharness scaffold (`permissions.deny`) |
| Secret exfiltration, AI attribution in commits, self-modification of `.claude/` | ccguard |
| Behavioural rules as prose (including "do not edit CLAUDE.md proactively") | ccharness scaffold |

## Scopes: user, project, local

Claude Code already separates user (`~/.claude/`), shared project (`.claude/`), and local (`.claude/settings.local.json`, `CLAUDE.local.md`) scope. ccharness follows it:

- **Shared project**: what the scaffold writes (`.claude/rules/`, `.claude/settings.json`, the CLAUDE.md snippet).
- **User**: your own style across every repository belongs in `~/.claude/CLAUDE.md` and `~/.claude/rules/`. Keep work-specific content out of it; it loads in every repository.
- **Personal per-project**: `CLAUDE.local.md` (gitignored). To share personal instructions across worktrees, import a home file: `@~/.claude/my-project-instructions.md`.
- **Several repositories at once**: `claude --add-dir ../other-repo` grants access; set `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` (for example in the `env` block of `~/.claude/settings.json`) to also load that repository's `CLAUDE.md` and `.claude/rules/`.
- **Worktrees**: gitignored local files reach new worktrees through `.worktreeinclude` at the project root; the skills template explains it. ccharness ships no copy step of its own.

## Non-goals

- Markdown or Japanese style checks (they belong to a writing plugin).
- Secret patterns and meta-guards (ccguard). Without ccguard, the "never expose secrets" line in the CLAUDE.md snippet is advice only.
- Repository-specific cadence hooks such as periodic review reminders.
- Injecting rules through a SessionStart hook: scaffolded files work for team members who do not have the plugin; injection would not.
- Anything an official setting already does.

## Roadmap

- **0.1** scaffold, templates, deny-rule snippet, floor hook, budget measurement.
- **0.2** behaviour skills as scaffold templates (this release).
- **0.3** optional profiles (for example `--profile ops` with production-command safety rules).

## Development

```bash
python3 -m unittest discover -s tests   # floor hook + deny-rule snippet + worktree isolation hints
bash tests/test_scaffold.sh             # scaffold behaviour, settings handling, template budget
python3 tests/test_measure.py          # always-on budget measurement
python3 tests/test_worktree_sweep.py   # branch/worktree inventory against real repositories
python3 -m unittest discover -s tests  # includes the stacked-worktree sync and merged-into-parent tests
python3 tests/test_ship.py              # commit / push / check against temporary repositories
python3 -m unittest tests.test_agent_tier_guard tests.test_agent_ledger   # tier guard and ledger hooks
```

## License

MIT
