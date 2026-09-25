---
name: session-wrap
description: Closing routine when the user signals the end of a session or a milestone - update progress, update issues, record knowledge, commit, in that order. Steps that do not apply may be skipped but must be reported as skipped.
license: MIT
allowed-tools: Bash, Read, Edit, Write
---

# session-wrap — closing routine

## Trigger

When the user signals the end of a session ("that's all for today", "thanks, wrapping up"), run this routine before committing, without waiting for an explicit instruction. A clear milestone in the work is also a valid trigger.

## Steps (in order)

1. **Progress**: update the state of plans and tasks in progress (`.claude/tasks/` or the project's progress files).
2. **Issues**: comment on, label or close the related issues. Skip if there is none; propose opening one if it would help.
3. **Knowledge**: record design decisions, pitfalls, resolved problems and mistakes the user pointed out (with ccmemo installed, `/record-knowledge`).
4. **Commit**: commit the changes. Do not push unless told to. Follow the repository's language convention for commit messages.

## Skipping

- Steps that do not apply may be skipped.
- Always say which steps were skipped.
