# Skill mechanics

The part of [writing-for-agents](SKILL.md) that applies only when the document is a skill: who can invoke it, and when to split one off. Everything else about writing it is in `SKILL.md`.

## Invocation

Two choices, trading the two loads:

- **Model-invoked**: keep a `description`, so the agent can run the skill on its own and other skills can reach it. The user can still call it by name. The description is the skill's top-level pointer and stays loaded at all times: permanent context load in exchange for discovery. Write it for the model, with the trigger branches; the pointer rules in `SKILL.md` apply in full. A model-invoked skill that is all reference is also a home for reference several skills need, since any of them can invoke it.
- **User-invoked**: set `disable-model-invocation: true`. Only a human typing its name can run it, and no other skill can. It costs no context load and spends cognitive load instead: the human must remember that it exists. The `description` becomes a one-line summary for the human, without trigger lists.

Choose model-invocation only when the agent must reach the skill on its own, or another skill must. A skill that only ever runs by hand is user-invoked and pays no context load.

Reference that two user-invoked skills both need belongs in neither: with no descriptions, neither can run the other. Put it in a plain file outside the skills, where any skill can point at it.

## Splitting by invocation

Split off a new model-invoked skill when a distinct leading word should trigger it on its own (a word you actually use in your prompts), or when another skill must reach it. The new description is always loaded, so that independent reach has to be worth it.
