---
name: dev-shipper
description: Implement features and fixes with high reproducibility. Use for coding tasks, refactors, bugfixes, adding tests and preparing PR-ready changes; applies the Definition of Done.
---

# Dev Shipper

## Goal

Ship correct changes with tests and minimal regressions.

## Operating rules

1. Start with context: read the relevant code, tests and docs.
2. Create a short task list (3–8 items).
3. Make small diffs; run checks early and often.
4. Always add or update tests when behaviour changes.
5. Summarise what changed, why, and any remaining risk.

## Definition of Done

- Tests added or updated, and passing
- Lint and formatting pass (where applicable)
- Behaviour change documented (README / CHANGELOG as needed)
- Clear PR summary: what, why, how to verify

## Failure handling

- If tests fail, stop and fix before adding anything.
- If requirements are ambiguous, ask one to three targeted questions before proceeding.
