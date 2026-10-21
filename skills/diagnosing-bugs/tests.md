# Writing tests

The rules for writing any test, and the acceptance criteria it checks: a regression test in step 5 of [diagnosing-bugs](SKILL.md), or a test for new behaviour. Rewritten from the `tdd` skill of mattpocock/skills (`skills/engineering/tdd/SKILL.md`, `tests.md`, `mocking.md`, commit `5beb35b`, MIT).

## Red first

- Write the test, run it, and watch it fail for the right reason (the missing behaviour, not a typo or an import error). Then write only enough code to make it pass.
- A test you have never seen fail has checked nothing.
- Read the count: look at the runner's count line (`Ran N tests`, `N passed`), not only the exit code. Zero tests collected exits 0 and is not a pass.

## Acceptance criteria

A plan's or a task's acceptance criteria are checks too. Rewritten from the docs of the `to-tickets` skill of mattpocock/skills (`docs/engineering/to-tickets.md`, commit `5beb35b`, MIT).

- For each criterion, name the observation that would show it false.
- Before the work starts, confirm the criterion is false at the commit the work starts from. A criterion already true there grades nothing.
- Three shapes grade nothing: one already true at the starting commit; one that only work outside this task can satisfy; one that restates the request instead of naming what to observe in the result.

## Seams

A seam is the public boundary you test at: the interface where you observe behaviour without reaching inside.

- Test through public interfaces only. A test describes what the code does, so it survives a change to how the code does it.
- Agree the seams under test when the way the work will be checked is agreed (a plan's Verification), not in a separate stop later.
- For each proposed seam, give one line on what it catches and what it misses, so the choice is not between bare names.

## Three anti-patterns

| Anti-pattern | The tell |
|---|---|
| Implementation-coupled | The test breaks on a refactor that kept the behaviour: it mocks your own collaborators, tests private functions, asserts call counts or order, or verifies through a side channel (querying the database instead of the interface). |
| Tautological | The expected value is computed the way the code computes it, so the test passes by construction. Take expected values from an independent source: a known literal, a worked example, the specification. |
| Horizontal slicing | A batch of tests lands before any implementation. Tests written in bulk check imagined behaviour and fix the test structure before the implementation is understood. |

A tautological test and its fix:

```python
# Bad: the expected value restates the implementation
def test_total_sums_line_items():
    items = [{"price": 10}, {"price": 5}]
    assert total(items) == sum(i["price"] for i in items)

# Good: the expected value is an independent literal
def test_total_sums_line_items():
    assert total([{"price": 10}, {"price": 5}]) == 15
```

## Mocks

Mock only at system boundaries: external APIs, time, randomness, and sometimes the filesystem or a database (prefer a test database). Never mock your own modules or anything else you control. At a boundary, pass the dependency in rather than creating it inside, so the test can hand in a fake.

## One slice at a time

One test at one seam, then the smallest implementation that passes it, then the next. The first test is a tracer bullet through one path end to end; each later test answers what the last cycle taught you.
