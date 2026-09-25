# ccharness

Ship-time harness for Claude Code. It puts the behavioural rules that every session must know into the repository, blocks the few shell commands that must never run from an agent session, and keeps the rest as lazily loaded skills.

**Official first.** Wherever Claude Code already has a setting, an environment variable, a CLI flag or a memory mechanism for a job, ccharness uses it instead of a custom one. The plugin adds only what has no official equivalent.

## Why

Claude Code plugins cannot load a `CLAUDE.md` or `.claude/rules/` on their own: the only plugin components are skills, agents, hooks, MCP and LSP servers. Anything that must be in effect before work starts therefore has to live in the repository. ccharness scaffolds exactly that content, and nothing more:

- **Rules that cause an accident if unknown** are scaffolded into `.claude/rules/` (always-on).
- **Opinionated command blocking** is scaffolded as official `permissions.deny` rules into `.claude/settings.json` (per repository, committed, opt-in).
- **Behaviour skills** (session wrap-up, branch cleanup, Definition of Done, pre-work verification, local workspace files) are scaffolded into `.claude/skills/` so each repository owns and adapts them, and the plugin's always-on cost stays at two skill descriptions.
- **Everything else** ships as plugin skills whose bodies load only when used.
- **One hook** stays in the plugin: the hard-deny floor, for the handful of commands a deny rule cannot express.

The split follows one question: *would starting work without knowing this cause an accident?*

## What you get

| Component | Kind | Purpose |
|---|---|---|
| `scripts/scaffold.sh` + `skills/scaffold` | scaffold | Copy rule templates into `.claude/rules/` (never overwrites), create or complete `permissions.deny` in `.claude/settings.json`, hand the `CLAUDE.md` snippet to the user |
| `templates/rules/{ja,en}/` | templates | `tool-call-resilience`, `discussion-phase-restraint`, `rules-and-skills-layering`, `local-workspace-files`; `tone` (Japanese only) |
| `templates/skills/{ja,en}/` | templates | `session-wrap`, `session-end-cleanup`, `dev-shipper`, `pre-work-verification`, `local-workspace-files` (detail) - copied to `.claude/skills/` once, then owned by the repository (`--no-skills` to skip) |
| `templates/settings.snippet.json` | template | Standard-tier deny rules: force push, `reset --hard`, `clean -f`, worktree-discarding checkout/restore, `chmod -R 777` |
| `templates/CLAUDE.md.snippet.{ja,en}.md` | template | Workflow Rules, Response Quality, Safety, Output Approach, Host Resource Constraints |
| `hooks/pretool_bash_guard.py` | PreToolUse(Bash) hook | Hard-deny floor: `rm -r` on root/home/cwd/glob (also as `/bin/rm`, `sudo rm`, `bash -c`), fork bomb, `mkfs`, `dd`/redirect onto a block device, `shred` |
| `scripts/measure_always_on.py` + `skills/harness-budget` | measurement | Bytes of always-on context: CLAUDE.md, rules, skill descriptions (capped at `skillListingMaxDescChars`) across project, user and enabled plugins |

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

There is no ccharness-specific switch or environment variable.

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
python3 -m unittest discover -s tests   # floor hook + deny-rule snippet
bash tests/test_scaffold.sh             # scaffold behaviour, settings handling, template budget
```

## License

MIT
