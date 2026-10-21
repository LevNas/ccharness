---
name: diagnosing-bugs
description: Use when a bug or failure resists a first look (a symptom you cannot explain yet, a flake, a regression), and before writing a regression or behaviour test. Gives the gate - a check seen failing before any hypothesis or fix. Not for a question one answer settles.
license: MIT
allowed-tools: Read, Grep, Glob, Edit, Write, Bash
---

# diagnosing-bugs

Diagnose a hard bug by building a check that shows the symptom before forming any theory, and write tests that can fail. Rewritten, not copied, from the `diagnosing-bugs` and `tdd` skills of mattpocock/skills (`skills/engineering/diagnosing-bugs/`, `skills/engineering/tdd/` and their docs, commit `5beb35b`, MIT). The rules for writing a test are in [tests.md](tests.md); read it before writing any test, inside or outside a diagnosis.

## The core

Trust only a check you have seen fail. A check that cannot go red proves nothing when it goes green. None of these is evidence:

- an "ok" over zero items (zero tests collected, zero files matched, an empty input);
- an exit code alone, without the count or the output that shows what was checked;
- an expected value computed the way the code computes it.

## Redact

You will show commands, outputs and captured artifacts. Write `<REDACTED>` in place of every secret first. Keep credentials in the environment, not in the commands you show. From a captured artifact, quote only the lines that carry the symptom. If the redacted output is not enough to diagnose, say so and ask the user.

## Step 1: Build the check (the gate)

Build one command that shows the symptom, run it once, and show the command and its output. No hypothesis before it exists. The check must be:

- **The user's symptom**: it drives the code path of the bug and shows the exact symptom the user reported, so it goes red now and green once fixed.
- **Repeatable**: the same verdict every run. For a bug that shows up only sometimes, raise and pin the reproduction rate (loop the trigger, run in parallel, add stress, narrow the timing) until it is high enough to work against.
- **Fast**: seconds, not minutes.
- **Unattended**: you can run it without a person in the loop.

Ways to build one, roughly in order:

1. A failing test at a seam that reaches the bug.
2. A script against a running service (a request, a curl).
3. A CLI run with a fixed input, diffed against known-good output.
4. A captured input (request, payload, event log) replayed through the code path.
5. A throwaway harness: the smallest part of the system that reaches the bug with one call.
6. A loop over many inputs, for output that is only sometimes wrong.
7. A script `git bisect run` can call, when the bug appeared between two known states.
8. The same input through the old and the new version, outputs diffed.

For an environment problem (a service, a device, a network path, a configuration), a read-only command that shows the symptom counts: a service status, one request, a log query.

If you cannot build a check, stop and say so. List what you tried, and ask the user for one of: access to an environment that shows the bug, a captured artifact (redacted), or permission to add temporary instrumentation. Do not go on to hypotheses without a check.

## Step 2: Reproduce

Run the check and confirm that what it shows is the failure the user described, not a nearby one. Wrong bug, wrong fix. Record the exact symptom (the message, the wrong output, the timing) so the fix can be checked against it.

Shrinking the case is recommended: cut inputs, callers, configuration and steps one at a time, re-running the check after each cut, and keep what the failure needs. A smaller case leaves fewer suspects and becomes a cleaner regression test.

## Step 3: Hypotheses

Write 3-5 ranked hypotheses before testing any of them; with one, you anchor on the first idea that fits. Each must be falsifiable, stated as a prediction:

> If X is the cause, then changing Y makes the bug disappear (or changing Z makes it worse).

A hypothesis without a prediction is a hunch: sharpen it or drop it. Show the ranked list to the user before testing; they may know a recent change or a cause already ruled out.

## Step 4: Probe

- Each probe tests one prediction from step 3. Change one thing at a time.
- Prefer a debugger or a REPL to logs; prefer a few targeted logs at the boundaries that tell the hypotheses apart to logging everything.
- Tag every debug log with one unique prefix, such as `[DEBUG-a4f2]`, so one grep finds them all for cleanup.
- For a performance regression, logs usually mislead: measure a baseline first, then bisect.

## Step 5: Fix and regression test

- If a correct seam exists, write the regression test before the fix: turn the case into a failing test at that seam and watch it fail (see [tests.md](tests.md)). A correct seam exercises the bug as it happens at the call site; a test at a shallower seam gives false confidence.
- If no correct seam exists, that is a finding: write it down instead of writing a shallow test. The structure of the code is keeping the bug from being locked down.
- If you made the red by editing code, a fixture or data, diff it against an untouched copy to show the edit landed before you trust the red.
- The fix itself waits for whatever agreement the repository's instructions require (the ccharness `CLAUDE.md` snippet asks for the user's agreement before changing anything on a bug report).
- After the fix, watch the regression test pass, and run the step 1 check again against the original case.

## Done when

- The step 1 check no longer shows the symptom.
- The regression test passes, or the missing seam is written down.
- A grep for the debug prefix comes back empty.
- Throwaway harnesses and scripts are deleted, or moved to a place marked as debugging aids.
- The hypothesis that turned out right is stated in the commit or PR message.
