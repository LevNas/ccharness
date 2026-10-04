# ccharness Ledger

The ledger is the thread-name → agentId registry for subagents. Agents do not know their own agentId, and `SendMessage` (resume) needs it — a missed record means a lost resume handle. One hook, `hooks/agent_ledger.py`, maintains the ledger; this file documents the format and its limits.

## Location

`<main checkout>/.claude/ccharness/ledger.jsonl` — one JSON object per line.

The hook resolves the main checkout as the parent of `git rev-parse --path-format=absolute --git-common-dir`, run in the `cwd` of the hook input. If git fails it falls back to `CLAUDE_PROJECT_DIR`, then to `cwd`. This matters in a session isolated in a linked worktree: a ledger written inside the worktree would be an ignored file there, and `worktree-sweep` classes a worktree with ignored files as "review", so every worktree that spawned an agent would stop being delete-class. In the main checkout the file is shared by all sessions of the repository; use `session_id` to tell them apart.

Operational state, not knowledge: **every repository that uses it should add `.claude/ccharness/` to its `.gitignore`** (this repository does). There is no automatic rotation; truncate or archive the file when a project accumulates history you no longer need.

## Records

Written by `hooks/agent_ledger.py`: registered for PostToolUse (matcher `Agent|Task`) and for SubagentStop.

### `launch`

```json
{"schema":"ccharness.ledger/1","ts":"2026-10-04T12:00:00Z","event":"launch",
 "session_id":"...","agent_id":"a1b2c3...","agent_type":"ccharness:worktree-worker",
 "model":null,"background":true,"thread":"implement parser task"}
```

- `agent_id` — extracted from the spawn response text (`agentId: <id>`); `null` when the pattern is absent. Observed in practice: background spawns carry the id in the response text, **synchronous spawns do not** — their launch record has `agent_id: null` and the id arrives on the matching `stop` record instead (SubagentStop input). Join launch↔stop via `agent_type` plus timestamps when resuming a synchronous thread.
- `model` — only an explicit per-call override; `null` means the agent definition's frontmatter (or inheritance) decided.
- `background` — `true` when the call does not say otherwise.
- `thread` — the short `description` parameter only. Prompt bodies are deliberately not persisted (secrets baseline for on-disk state).

### `stop`

```json
{"schema":"ccharness.ledger/1","ts":"2026-10-04T12:05:00Z","event":"stop",
 "session_id":"...","agent_id":"a1b2c3...","agent_type":"ccharness:worktree-worker",
 "stop_reason":"end_turn"}
```

## Parallel limit

The number of parallel subagents is limited by the official `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (the Agent tool refuses spawns past it), not by this ledger. Related official settings: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` and `CLAUDE_CODE_SUBAGENT_MODEL`.

## Derived state and its accuracy

`launches - stops` per `session_id` gives a rough count of running agents, but no guard uses it any more, and it is best effort:

- A resumed agent stops again → extra `stop` records → undercount.
- Synchronous spawns record launch and stop around the same time → net zero.
- Cross-check live state with `ListAgents` when it matters.

## Resume

To resume a thread, find its latest `launch` by `thread`/`ts` and use the `agent_id` with `SendMessage`. Ledger entries survive context compaction — that is their point: the registry outlives what the session window retains.

## While ccorch is also installed

If ccorch 0.4.0 (which wrote the same records to `.claude/ccorch/ledger.jsonl`) is installed alongside, each spawn is recorded in both ledgers. This is harmless.
