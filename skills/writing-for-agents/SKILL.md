---
name: writing-for-agents
description: How to write what an agent reads - a skill, CLAUDE.md, a rule, or a prompt for a subagent or pane. Use when creating, editing or trimming one, to decide what stays always loaded, what goes behind a pointer, and which sentences to delete.
license: MIT
allowed-tools: Read
---

# Writing for agents

A reference for any text an agent reads: a skill, `CLAUDE.md`, a file in `.claude/rules/`, a prompt for a subagent or a pane, a document a pointer leads to. The packaging differs; the levers do not. They make the agent take the same process on every run (not produce the same output). Rewritten from the `writing-for-agents` skill of mattpocock/skills (commit `5beb35b`, MIT).

If the document is a skill, also read [skill-mechanics.md](skill-mechanics.md): who can invoke it, and when to split one off.

The default fix is to delete. Asked to write for another model, a model explains what its reader already knows.

## Context pointers

A context pointer is a line in the agent's context that names material outside it and says when to reach it: a skill's `description`, a line in `CLAUDE.md` naming a document, a rule's `paths:`. Its wording, not its target, decides whether the agent reaches the material and how reliably. When a must-have target is reached unreliably, sharpen the pointer first; inline the material only if that fails.

A pointer says what the material is and lists the branches that should trigger it (a branch is a distinct case the document handles, so different runs take different paths through it). An always-loaded pointer is paid on every turn, so prune it harder than a body:

- Put the leading word first: that is where the triggering happens.
- One trigger per branch. Synonyms that name the same branch are one branch written twice; keep one.
- Leave out what the body already says about itself.

## The two loads

Every document and pointer spends one of two budgets:

- **Context load**: what sits in the window on every turn, whether it fires or not. In Claude Code: `CLAUDE.md` and the files it imports, `.claude/rules/` files without `paths:`, and every skill and agent description. `harness-budget` measures it.
- **Cognitive load**: what the human must remember - which documents exist and when to reach for each. It is the price of human agency: spend it where the human's judgement matters, remove it where it does not.

Material behind a pointer costs only the pointer's line until it fires. Material with no pointer at all costs only cognitive load. Material that one session in ten needs pays context load in the other nine.

## Information hierarchy

A document holds two kinds of content: **steps** (what the agent does, in order) and **reference** (definitions, rules and facts consulted on demand). They mix freely. Place each piece on a ladder by how soon the agent needs it:

1. In-file step.
2. In-file reference. A flat set of peer rules on one rung is fine.
3. Disclosed reference: a separate file behind a pointer, read only when the pointer fires (a sibling file, or one anywhere else).

Push down too little and the top bloats; push down too much and the agent misses what it needs.

- **Progressive disclosure** moves material down the ladder to keep the top legible. The test is branching: inline what every branch needs, and disclose what only some branches reach. Reference left among the steps buries them, and following them becomes a coin flip.
- **Co-location**: keep a concept's definition, rules and caveats under one heading, so reading one part brings the rest. The document should read like documentation written for the agent.
- **Sprawl**: a document too long, even when every line is live. Attention thins across it. Cure it with the ladder: disclose reference, and split by branch or by sequence so each path carries only what it needs.

## Steps and completion criteria

Every step ends on a completion criterion: how the agent tells done from not done.

- **Clarity.** A vague bound ("understanding reached") invites premature completion: the steps still ahead pull attention towards being done. Sharpen the bound first. Only if it stays fuzzy and you see the rush, hide the later steps by splitting the sequence. Hiding works only across a real context boundary (a handoff or a subagent); an inline call leaves the later steps in view.
- **Demand.** "Every modified model accounted for" drives more legwork than "produce a change list". Demand binds reference too: "every rule applied" holds a flat set of rules to the same bar as "every step done".

The strongest criteria are checkable and exhaustive.

## When to split

A split spends one of the two loads, so split only when the cut pays for it.

- **By sequence**: when the steps after the current one tempt the agent to rush it. Keeping them out of view drives more legwork on the step in front. Merging sequences does the reverse.
- **By invocation** (skills only): see [skill-mechanics.md](skill-mechanics.md).

## Leading words

A leading word is a concept the model already holds from pretraining and thinks with while it runs the document (_lesson_, _fog of war_, _tracer bullet_). Repeat it as a word, never as a sentence: each use adds to its meaning, and it anchors a region of behaviour in a few tokens. Prefer an existing word; a coined one recruits nothing and must be paid for in definition.

It works in two places. In the body it steers execution, and inside a flat reference it focuses attention on one class of thing to look for. In a pointer it triggers invocation, most reliably when the same word lives in your prompts, documents and code.

Look for passages that collapse into one word: a triad spelled out at three sites ("fast, deterministic, low-overhead" becomes _tight_), or a fuzzy gate turned into an observable state ("a loop you believe in" becomes _red_).

**Negation**: a ban names the banned behaviour and makes it more available, not less. Write the positive target instead ("write one-line comments"), so the banned behaviour is never spoken. Keep a prohibition only for a hard guardrail you cannot phrase positively, and pair it with the positive target.

## Pruning

- **Single source of truth**: one meaning in one place, so changing the behaviour is one edit. Duplication costs tokens and upkeep, and lifts the meaning above its rank on the ladder. (A leading word repeats a word on purpose, never a meaning.)
- **The environment is a source of truth too** (scripts, config files, the directory layout, `--help`). A document that restates it is a cache, worth its load only when the lookup is expensive. Write down what looking cannot find: the unwritten convention, the reason behind a choice, the gotcha no config admits.
- **Relevance**: every line must still bear on what the document does. A line loses it by never bearing on the task, or by going stale as the behaviour it describes changes. Without pruning, the result is sediment: stale layers that stay because adding feels safe and removing feels risky.
- **No-ops**: an instruction the model already follows by default costs load and changes nothing. The test is whether behaviour changes against the default, so the answer depends on the model, not on the reader; settle a disagreement by running the document, not by argument. Delete a failing sentence whole rather than trimming words from it. A word too weak to beat the default (_be thorough_, for an agent that already is) is a no-op as well: replace it with a stronger word (_relentless_), not a different technique.
