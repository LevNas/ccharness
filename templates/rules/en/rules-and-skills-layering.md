# Two layers: rules and skills

Behavioural rules under `.claude/` live in two layers.

| Layer | Location | How it loads | What goes there |
|---|---|---|---|
| Always-on | `.claude/rules/*.md` | Loaded in every session | Rules that cause an accident if unknown before starting |
| On demand | `.claude/skills/<name>/SKILL.md` | Only `description` is always loaded; the body loads when needed | Work procedures with a clear trigger |

Session context is append-only; nothing can be unloaded later. Design for "do not load until needed", not "release later".

## Deciding where something goes

Ask: "Would starting work without knowing this rule cause an accident?" If yes, rules. If reading it once the work starts is enough, skills. When both exist under the same name, rules hold the skeleton and skills hold the detail: keep prohibitions and procedures in rules, and move history, past cases and examples into the skill.

## Adding a new rule

- First decide whether it really must be always-on. Usually the skill side is right.
- In a skill, write the trigger ("use when ...") into `description`. It is the only cue the model gets.

## Guards

- Reshuffling layers (moving across layers, splitting skeleton/detail, growing or shrinking the always-on side) is proposed and approved first. Treat it like editing CLAUDE.md.
- Never add a file to `.claude/rules/` as a by-product of other work. The default home for a new rule is `.claude/skills/`.
- Treat the always-on side as a budget, not a folder. Measure it with `ccharness:harness-budget` and report the delta. If it grew, re-apply the question above and move anything that fails it into a skill.

## Editing mid-session

- Editing CLAUDE.md or `.claude/rules/` during a session keeps the cache, but the edit does not apply until the next `/compact`, `/clear` or restart. To make it take effect now, `/compact` at a natural break.
- What survives compaction is what is in files. CLAUDE.md and rules without `paths:` are re-read; only the start of recently used skills comes back. The skill listing (descriptions) does not come back, so name in CLAUDE.md or rules any skill that must stay usable after compaction. Decisions made only in conversation are lost, so write the ones that must last into a file.
