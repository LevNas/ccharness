---
name: arc-handoff
description: Use at the boundary between two arcs of work inside one long session. Writes the state to the issue, task file or knowledge base, then hands the user a /compact line that names the next arc. To end the session, use session-wrap instead.
license: MIT
allowed-tools: Bash, Read, Edit, Write
---

# arc-handoff — switching arcs inside one session

Run this at the boundary between two arcs (units of work) when one session is used for a long time. Only what is in files survives compaction, so move the conversational state into files first, then `/compact`. `/compact` is a command the user types: this skill does not run it, it shows the line to type.

## Steps (in order)

1. **Confirm the boundary**: state in one line whether the current arc met its done criteria (tests, build, review) or is being paused without them.
2. **Write the state down**:
   - Progress: in the task file (`.claude/tasks/` or similar) or an issue comment — what is done, what remains, the next step.
   - Decisions: what the user decided in conversation that is not in a file yet. Decision records go to the knowledge base (`/record-knowledge` when ccmemo is installed).
   - Changes: commit uncommitted work. Push only when asked.
3. **Show the `/compact` line**: one or two sentences on the next arc's focus.
   Example: `/compact Next: implement <next issue>. <current issue> is merged in <PR>; the remaining items are in the issue.`
4. **Show the entry point of the next arc**: the files or issue to read first, and the first step.

## Choosing

- Moving to unrelated work: suggest `/rename`, then `/clear` — not `/compact`.
- Ending the session: use session-wrap.
- Nowhere to write to (no issue, no task file): ask the user whether to create one.

## Background

- CLAUDE.md and rules without `paths:` are re-read after compaction; only the first 5,000 tokens of recently used skills come back; instructions given only in conversation are lost.
- The `Compact Instructions` section of CLAUDE.md tells the summary what to keep. This skill writes the state to files first so the session does not depend on the summary.
