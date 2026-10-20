---
name: settle-decisions
description: Settle a plan, design or decision with the user in rounds of numbered questions, each with a recommended answer, and act only after the user confirms. Use when asked to think a plan through, stress-test or grill it, or from a skill that needs an interview.
license: MIT
allowed-tools: Read, Grep, Glob
---

# settle-decisions

Interview the user until you both understand a plan, a design or a decision the same way, before anyone acts on it. The technique is the `grilling` skill of mattpocock/skills (`skills/productivity/grilling/SKILL.md` and its docs, commit `5beb35b`, MIT), rewritten rather than copied, with a list of what is settled at the top of every round and numbering that runs through the session.

## The tree and the frontier

- Treat the subject as a design tree: each decision has the decisions that depend on it.
- The frontier is every open decision whose prerequisites are settled. Ask the whole frontier in one round, and nothing else.
- A question whose answer depends on another question still open in the same round waits for a later round. Then no answer in a round can make another question in that round wrong.
- After each round, work out the next frontier from what was settled. Later rounds ask what the earlier answers made possible to ask.

## A round

1. Start with what is settled: every decision settled so far, numbered by its question, each written as a sentence that reads without the question. An answer such as "all yes" means nothing once the questions are gone, for example after a compaction.
2. Then the questions. Number them on from the last round; never start again at 1.

   ```
   ❓ **Q<n>** - **<title>**: <body: the context the user needs, the options>

   ➡️ <your recommended answer>

   ---
   ```

3. Word each question so "yes" accepts your recommended answer.
4. Ask in the language of the conversation. The markers (`❓`, `➡️`, `---`) stay as they are.
5. When an answer shows that a settled decision should change, ask it again as `Q<n> (revisits Q<m>)` and say what changed it. Never change a settled decision silently.

- Use the `AskUserQuestion` tool only when the round has at most four questions and each is a choice between options; put the recommended option first. Otherwise write the round as text.
- If the user's instructions say to ask one question at a time, do that instead of rounds.

## Facts and decisions

- Facts are your job. Read files, run read-only commands, or dispatch a subagent, following the repository's rules for who looks things up. Never ask the user what you can find out.
- A lookup still running holds back only the questions that depend on it; ask the rest of the frontier now.
- Decisions are the user's. Put each one to them and wait. Never answer your own question and move on, even when another skill or a ticket started the interview.
- Some questions cannot be settled by talking (how something should look or feel). Say so and propose a throwaway prototype instead of asking again in other words.
- If the frontier keeps growing, the scope is too big: propose splitting the work and settling the parts one at a time.

## Ending

- The interview is done when the frontier is empty. Then list every settled decision and ask the user to confirm that you understand them the same way.
- Do not act on any decision before the user confirms: no file edits, no commits, no implementation. An empty frontier is not a confirmation.
- After the confirmation, suggest recording the decisions where they will last: an ADR or the knowledge base (with ccmemo installed, `/record-knowledge`). This skill writes no files itself.

## Not here

- No cap on the number of questions. The user ends a session by saying so.
- No front-door variants such as `grill-me` or `grill-with-docs`: a skill that names another skill does not reliably load it. Call this skill by name.
