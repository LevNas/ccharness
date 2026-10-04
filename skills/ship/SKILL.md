---
name: ship
description: After implementation, commit the listed files, push the branch and check the pull request with scripts/ship.py - stage by name, secret scan of added lines, no force push, one summary line for the PR check. Use to commit, push and verify a PR; it never merges.
license: MIT
allowed-tools: Bash, Read, Write
---

# ship

The steps after implementation (stage, commit, push, check the PR) give the same answer every time, so a script runs them. Hand-written versions kept failing: `git add -A` refused by a commit-scope rule, compound git commands refused by the worktree isolation check, several calls strung together per PR.

## Order

commit → push → plain `gh pr create --body-file` → check.

1. Write the commit message to a file (Write tool). English, neutral, describing what the commit does to the repository.
2. Commit, listing every file by name. Paths are relative to the current directory and may be deleted files:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ship.py" commit --files path/a path/b --message-file /abs/msg.txt
   ```

   It refuses on the default branch (the `origin/HEAD` target, `main` and `master`) and during a merge or rebase, stages each path by name as a literal path (never `git add -A` or `.`), and stops if the staged set differs from the listed set (it prints both and unstages nothing). It scans the added lines of each staged file for private key headers, common token prefixes and `password`/`secret`/`token` assignments with a quoted value; a hit prints file, line and pattern name only, and nothing is committed. `--scan-patterns FILE` adds your own regexes (one per line, `#` comments), for example private names that must stay out of the repository. On success it prints the new short SHA.

   What the scan does not cover: binary files and submodule pointer bumps (no text lines are scanned in a binary file), unquoted values, and key names it does not know (it looks for `password`, `passwd`, `secret` and `token` in the name). It is a net for common mistakes, not a proof that nothing secret is staged.

   After a scan hit, never run a plain `git commit` to get past it. Change the content so the hit goes away; for a suspected false positive, ask the user.
3. Push: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ship.py" push`. It runs `git push -u origin <branch>`, refuses on the default branch, and never uses `--force` or `--no-verify`, so a pre-push hook (if installed) keeps running.
4. Create the PR yourself, as a plain command, with the body in a file: `gh pr create --draft --title "..." --body-file /abs/body.md`. The script does not do this on purpose: a `gh pr create` inside a script would hide its title and body from PreToolUse guards that check what gh posts.
5. Check: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ship.py" check [--pr N] [--expect-files path/a path/b] [--wait SECONDS]`. Read-only. It polls while `mergeable` is UNKNOWN or the PR's head is not yet the local HEAD (default 30 seconds, `--wait` must be finite; each `gh` call has a timeout) and prints one line: `READY: ...` or `NOT READY: ...` with the reasons.

## Exit codes

- `0`: done; for `check`, the PR is OPEN, MERGEABLE, CLEAN (a draft also accepts DRAFT; BLOCKED is never ready, since it also means failing or pending checks), its head is the local HEAD and its files are the expected files.
- `1`: a refusal or a failed check stopped it. Read the printed reason and fix the cause; do not work around the refusal (no `git add -A`, no `--force`, no `--no-verify`).
- `2`: usage or environment error (not a repository, `gh` missing, unreadable file).

## Notes

- `check` covers GitHub only. GitLab is not covered yet.
- Merging stays with the user. This skill never merges, and a ready PR is not a request to merge.
- Keep message and body files outside the repository (a temporary directory), so they are never part of the staged set.
