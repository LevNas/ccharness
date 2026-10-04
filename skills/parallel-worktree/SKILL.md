---
name: parallel-worktree
description: Fan out file-ownership-disjoint implementation tasks to parallel worktree-isolated subagents (ccharness:worktree-worker), preserve their captures, merge the worker branches in an integration worktree, then ship the integration branch as a PR through the repository's merge flow. Use for two or more closed tasks in one repository that share no files.
license: MIT
allowed-tools: Bash, Read, Write, Grep, Glob, Agent, Skill, EnterWorktree, ExitWorktree
---

# parallel-worktree

Parallel implementation across isolated git worktrees, inside one session, using the bundled `ccharness:worktree-worker` agent type (and `ccharness:impl-verifier` for checking).

## Division of labor

The harness already provides worktree creation, branch creation (`worktree-agent-<id>`), locking (owned by this session, released on agent completion) and automatic cleanup of **unchanged** worktrees. Do not reimplement any of that. This skill adds only what the harness does not: **pin the origin, preserve captures, merge, ship, clean up through `worktree-sweep`**.

## When to Use

- Two or more implementation tasks in THIS repository with **disjoint file ownership** (no shared files between tasks).
- Each task is closed and mechanically specified (spec, ownership list, acceptance criteria). SDD-style task decompositions are the ideal input.

Do NOT use when tasks share files (serialize those), when the work needs design judgment mid-flight (keep it in the main session), or for work in separate repositories or separate sessions.

**Never run this from inside a worktree-isolated session**: such sessions cannot run git against the shared checkout. Orchestrate from the main checkout.

## Phase 0 — Pin the origin

With `worktree.baseRef: head` (project setting), the orchestrator's cwd HEAD determines the fan-out base of every spawned worktree.

```bash
git rev-parse --abbrev-ref HEAD                          # branch name, for the report only (prints HEAD when detached)
git rev-parse HEAD                                       # record this commit hash as BASE
git status --short                                       # expect clean
grep -rs '"baseRef"' .claude/settings.json .claude/settings.local.json
```

- BASE is the commit hash, not the branch name. Record it in your working notes; every later phase uses that hash (`git diff --name-only BASE..<branch>`, `git worktree add ... BASE`), because the base branch may move during the wave and a branch name would then point at a different commit than the workers started from.
- Do not `cd` elsewhere or move HEAD between launches — all workers of one wave must share the same base.
- With `baseRef: fresh` (default), the base is origin's default branch; fetch first if that is intended, or set the project to `head` for local-stacked work. With `fresh`, record `git rev-parse origin/<default>` after the fetch as BASE instead of the local HEAD, since that is the commit the workers start from.

## Phase 1 — Fan out in waves

- A wave has at most 3 workers, whatever the settings say, and fewer when `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` is set lower (the Agent tool refuses spawns past that official cap, whose default of 20 is far above what a host should run; this plugin adds no cap of its own). Split excess tasks into waves.
- Spawn `ccharness:worktree-worker` per task, background, with this prompt shape:

```
Task: <closed spec>
Ownership — you may modify ONLY these files: <explicit list>
Acceptance criteria: <list>
Commit message to use: <message>
Verification commands to run: <commands or "none">
```

(The worker's own definition carries the hard rules: no `.claude/` writes, explicit-path `git add` only, no push, no branch switching.)

- Wait for completion notifications; do not poll. Record thread→agentId pairs; the ledger hook records them automatically in `.claude/ccharness/ledger.jsonl` of the main checkout (see `docs/ledger.md`) — cross-check with `ListAgents` if in doubt.

## Phase 2 — Preserve captures (BEFORE any removal)

For each completed worker with changes, its worktree (`.claude/worktrees/agent-<id>`) and branch survive; unchanged workers are already auto-cleaned.

1. List untracked **and ignored** files in the worker worktree: `git -C <worktree> status --porcelain --ignored --untracked-files=all` (look for session-capture files, for example the context files of a memory plugin, if installed, under `.claude/tasks/`). Ignored files such as `__pycache__` show as `!!`. `worktree-sweep` treats a worktree that still holds untracked or ignored files as "review", not "delete", so what is left here decides whether the later cleanup is a plain delete.
2. Move captures worth keeping to the main checkout's `.claude/tasks/<slug>/`, appending a worker suffix to the filename to avoid same-second collisions: `context-<ts>.md` → `context-<ts>-<worker>.md`.
3. Decide explicitly about every other untracked or ignored file; removal destroys it. Delete what is disposable in the worker worktree yourself, with the user's word, so the sweep can classify the worktree as delete.

## Phase 3 — Integration merge

1. Verify each worker's report: the commit exists and only owned files changed: `git diff --name-only BASE..<branch>` — abort integration of a branch that touches `.claude/` or files outside its ownership list.
2. Create the integration worktree off BASE, under the worktrees directory so the session can enter it later — never merge on the base branch:
   `git worktree add .claude/worktrees/integration-<slug> -b integration/<slug> BASE`
3. Merge each worker branch with `--no-ff` (symmetric history):
   `git -C .claude/worktrees/integration-<slug> merge --no-ff <branch>`
4. Disjoint ownership means conflicts should not occur. If one does, stop and re-examine the ownership split — do not resolve silently.
5. Optionally spawn `ccharness:impl-verifier` against the integration worktree before proceeding.

## Phase 4 — Ship the integration branch, then clean up

The integration branch goes through the repository's normal merge flow; this skill never merges and never touches the base branch.

1. Enter the integration worktree with `EnterWorktree`, `path` set to `.claude/worktrees/integration-<slug>` (this is the one deliberate entry into a worktree, after Phase 3 is complete; the rule above is about orchestrating). `ship push` pushes the CURRENT branch, and the orchestrator itself sits on the base branch in the main checkout, so the push must run from inside the integration worktree.
2. Commit anything left, with the `ship` skill (`ship commit --files ... --message-file ...`), then `ship push`.
3. Open the PR with a plain `gh pr create --draft --body-file <file>` (as the `ship` skill describes) and run the repository's merge-time review. Merge **only on the user's word**, and with a **merge commit**.
4. After the merge, leave the integration worktree (`ExitWorktree`, action `keep`) and run the `worktree-sweep` skill from the main checkout. Remove the worker worktrees and branches, and the integration worktree and branch, only through the sweep's delete-class commands, on the user's word. Do not add `--force` to `git worktree remove` and do not use `git branch -D` on your own.

Why no force and no `-D`: each worker branch was merged with `--no-ff` into the integration branch, and the integration branch was merged into the base with a merge commit, so every worker commit is an ancestor of the base. The sweep classifies such a branch as delete once nothing is left in its worktree (nothing uncommitted, untracked or ignored), and git's own refusal (`git branch -d`, `git worktree remove` without `--force`) stays as the last check. A squash or rebase merge of the integration PR leaves the worker branches as non-ancestors; the sweep then reports them as review, which is correct — decide those with the user, do not force them.

## Escalation (deterministic)

If a worker's output fails acceptance, re-run the same prompt with the model one tier up (`sonnet` → `opus`), at most once, and record the escalation in your report. The orchestrator decides this — never ask a leaf to judge its own quality. The tier guard hook denies an override more than one tier above the pinned model.

## Later

Phase 0 and the Phase 3 checks (the ownership diff, the `.claude/` check, the ancestry check) give the same answer every time. They are candidates for a script, as `ship` was for commit, push and check.

## Report to the user

- BASE commit, wave layout, per-task: branch, commit, verify result, deviations.
- Captures preserved (paths), branches merged, integration branch name, PR URL.
- Ledger location for resume handles.
