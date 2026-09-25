# Handling tool-call failures

Rules for when tool calls repeatedly fail to parse (for example, a malformed call envelope). A call that does not parse never reaches a PreToolUse hook, so hooks cannot catch it. These rules limit the damage.

## Never retry the identical call after consecutive failures

- Do not repeat exactly the same call. Simplify the content or change approach (a different tool, a different split).
- If it still fails, report the situation to the user and suggest restarting the session or running the step manually. Restarting is the most reliable fix when interruptions continue.

## Keep calls simple (prevention)

- Write large, multi-line, or special-character content to a file first and reference it (for example, put the commit message in a file and use `git commit -F <file>`).
- One call, one purpose. Do not bundle unrelated operations into one huge call.
- Avoid command substitution, nested quoting, and excessive escaping.

## After the same failure three times, propose a rule

Propose promoting it to `.claude/rules/` or a skill. Do not add it on your own.
