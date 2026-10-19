---
name: session-wrap
description: Closing routine when the user signals the end of a session or a milestone - update progress, update issues, record knowledge, commit, in that order. Steps that do not apply may be skipped but must be reported as skipped.
license: MIT
allowed-tools: Bash, Read, Edit, Write
---

# session-wrap — closing routine

## Trigger

When the user signals the end of a session ("that's all for today", "thanks, wrapping up"), run this routine before committing, without waiting for an explicit instruction. A clear milestone in the work is also a valid trigger, and so is a merge-time review returning pass or fail.

## When a merge-time review fails

The session-wrap still runs. Record the verdict, a short summary of the blocking findings, the next step and how many fix rounds ran: in the task or progress file and as an issue comment; as knowledge only when there is a lesson. Put these records on a **separate branch and PR into the default branch**, not on the feature branch, which may be abandoned.

## Termination

A session-wrap's own branch or PR is never wrapped again, whatever its review returns. If its review fails, fix it in that PR.

## Steps (in order)

1. **Progress**: update the state of plans and tasks in progress (`.claude/tasks/` or the project's progress files).
2. **Issues**: comment on, label or close the related issues. Skip if there is none; propose opening one if it would help.
3. **Knowledge**: record design decisions, pitfalls, resolved problems and mistakes the user pointed out (with ccmemo installed, `/record-knowledge`).
4. **Repeated failures** (only with the ccevolve plugin): when the same tool call fails again in a session, ccevolve's hook adds a note that starts with `[ccevolve] 同じ失敗が` ("the same failure, for the Nth time") and carries a key in backticks, such as `Bash: <error line>`.
   - If this session got such notes, call `/promote-to-computation` and name their keys: ask for proposals for those keys only, even if its ledger report lists more. The report counts from the third time and the note comes from the second, so a key may be missing from the report. A proposal turns the failure into a check that runs by itself (a hook, lint rule, test or permission rule).
   - Put the proposals in the wrap report and apply none of them: the user decides on each. If the user puts them off, note them in the progress file.
   - If a note came but `/promote-to-computation` is not available, list the keys in the wrap report instead.
   - With no such note, or without ccevolve, skip this step and say so. The notes are only in the conversation, so failures from before a compaction are not picked up here; the ledger still has them for a periodic review.
5. **Commit**: commit the changes. Do not push unless told to. Follow the repository's language convention for commit messages.

## Skipping

- Steps that do not apply may be skipped.
- Always say which steps were skipped.
