#!/usr/bin/env python3
"""Agent ledger: one JSON line per subagent launch and stop (PostToolUse matcher Agent|Task, SubagentStop).

Agents do not know their own agentId, and `SendMessage` (resume) needs it. The orchestrator side records it
at spawn time, so the resume handle survives context compaction. See docs/ledger.md for the record format.

Records (schema `ccharness.ledger/1`):
  launch: ts, event, session_id, agent_id, agent_type, model, background, thread
  stop:   ts, event, session_id, agent_id, agent_type, stop_reason
`agent_id` of a launch is parsed from the text `agentId: <id>` in the tool response (not a documented field)
and is null when absent; synchronous spawns usually carry no id there, and the id arrives on the stop record.
`thread` is the short `description` parameter. Prompt bodies are never written.

File: `<main checkout>/.claude/ccharness/ledger.jsonl`. The main checkout is the parent of
`git rev-parse --path-format=absolute --git-common-dir`, run in the hook input's `cwd`. In a session isolated
in a linked worktree a ledger written inside the worktree would be an ignored file there, and `worktree-sweep`
classes a worktree with ignored files as "review", so every worktree that spawned an agent would stop being
delete-class. If git fails, the directory falls back to CLAUDE_PROJECT_DIR, then to `cwd`. A repository that
uses this should add `.claude/ccharness/` to its .gitignore.

Limits: no rotation; the file only grows. The count `launches - stops` is best effort (a resumed agent stops
again) and nothing in ccharness depends on it.

Fail-open: malformed input, an unwritable directory or any error exits 0 without output.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys

SCHEMA = "ccharness.ledger/1"
AGENT_ID_RE = re.compile(r"agentId: ([A-Za-z0-9_-]+)")


def main_checkout(cwd: str | None) -> str | None:
    """Directory that owns the ledger: main checkout, else CLAUDE_PROJECT_DIR, else cwd."""
    if cwd:
        try:
            out = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=5)
            common = out.stdout.strip()
            if out.returncode == 0 and common:
                return os.path.dirname(common.rstrip("/"))
        except Exception:
            pass
    return os.environ.get("CLAUDE_PROJECT_DIR") or cwd or None


def agent_id_of(response) -> str | None:
    text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
    match = AGENT_ID_RE.search(text)
    return match.group(1) if match else None


def record(payload: dict) -> dict | None:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    event = payload.get("hook_event_name")
    if event == "SubagentStop":
        return {"schema": SCHEMA, "ts": now, "event": "stop", "session_id": payload.get("session_id"),
                "agent_id": payload.get("agent_id"), "agent_type": payload.get("agent_type"),
                "stop_reason": payload.get("stop_reason")}
    if payload.get("tool_name") not in ("Agent", "Task"):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    return {"schema": SCHEMA, "ts": now, "event": "launch", "session_id": payload.get("session_id"),
            "agent_id": agent_id_of(payload.get("tool_response")),
            "agent_type": tool_input.get("subagent_type") or "claude",
            "model": tool_input.get("model"),
            "background": tool_input.get("run_in_background", True),
            "thread": tool_input.get("description")}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        entry = record(payload)
        if entry is None:
            return 0
        cwd = payload.get("cwd")
        root = main_checkout(cwd if isinstance(cwd, str) else None)
        if not root:
            return 0
        directory = os.path.join(root, ".claude", "ccharness")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "ledger.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # fail-open: bookkeeping must never fail a tool call
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
