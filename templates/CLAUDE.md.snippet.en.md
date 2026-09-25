<!-- ccharness template v0.1.0 (en): review, then append to CLAUDE.md with the user's approval -->

## Workflow Rules

- On bug reports: investigate autonomously (reproduce, read logs, trace code) → report findings and the proposed fix, get agreement before changing anything → if information is missing, ask in a form other team members can follow → if the investigation stalls, stop and report. No ad-hoc fixes without a plan
- Prove behaviour with tests or logs before calling a task complete
- Start in plan mode for tasks with three or more steps
- If a fix feels hacky, re-investigate the root cause
- If stuck, stop and re-plan. Never brute-force through
- **Do not edit CLAUDE.md proactively**: it is shared. Propose changes and edit only after approval. Where things persist: team behaviour rules → `.claude/rules/` (after approval) / personal rules → `~/.claude/` / lessons and findings → the knowledge base / sensitive personal context → `.claude/private/` (gitignored) / personal plans → `.claude/tasks/`

## Response Quality

- Self-review in three passes (broad → mid → narrow) before responding
- Disclose any command or code that has not been verified before presenting it
- When an error occurs, explain the intent behind the command you tried
- If the request is ambiguous or unstructured, restate it as a structured summary first
- Knowledge-first: search the knowledge base before anything else and build on what is there; otherwise go to external sources; if still uncertain, ask instead of guessing

## Safety

- Confirm before destructive operations (sudo, service restarts, overwriting config, rewriting history). Obvious ones are blocked by a hook
- If a task is ambiguous, ask for the missing constraints before producing a large diff
- Do not break existing behaviour (incremental changes, rollback-capable procedures)
- Never expose secrets (exclude `.env`, never commit plaintext credentials)

## Output Approach

- Prefer readability and maintainability; clear structure over clever one-liners

## Host Resource Constraints

- At most two or three parallel agents. Avoid bulk file reads and huge command output. Consider background execution for long builds or installs
