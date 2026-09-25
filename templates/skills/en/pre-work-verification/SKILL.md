---
name: pre-work-verification
description: Verification before presenting procedures, scripts or commands - confirm the target configuration, read release notes, search prior knowledge, verify against official references, adjust the plan, and check the remote execution environment. Six steps.
---

# Pre-work verification flow

Before presenting a procedure, script or command, do the following in order.

1. **Current state**: confirm the target system or service configuration (version, edition, environment).
2. **Release notes**: read the notes for that version and pick out breaking changes, deprecated parameters and behaviour changes relevant to the task.
3. **Prior knowledge**: search for known pitfalls and past findings (with ccmemo installed, `/recall-knowledge`).
4. **Official references**: verify commands and parameters against official documentation. Product-specific sources are listed in `.claude/rules/`.
5. **Plan review**: adjust the work plan based on steps 1–4.
6. **Remote execution check**: when commands run on a remote target (SSH, PSSession, Ansible and the like), verify the gap between client and target first (shell type, version, available modules) and put an environment-check command at the top of the command list.

When something is presented unverified, say so.
