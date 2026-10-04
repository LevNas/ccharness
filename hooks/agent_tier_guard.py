#!/usr/bin/env python3
"""Model tier guard for the leaf agent catalog (PreToolUse, matcher Agent|Task).

Each catalog agent in `agents/<type>.md` pins its model in the frontmatter (`model: sonnet`). A per-call
`model` override on the Agent tool is only legitimate as one deterministic escalation step after a failed
run (re-run one tier up, once). This hook denies an override more than one tier above the pinned tier.

Tiers: haiku=1, sonnet=2, opus=3, fable and mythos=4 (a full name such as `claude-opus-5-5` counts by its
family). An unknown model name is denied, since its tier cannot be compared. `inherit` and an empty value
are allowed (nothing is overridden).

The pinned tier is read from the `model:` line of `${CLAUDE_PLUGIN_ROOT}/agents/<type>.md` on every call,
so it cannot drift from the frontmatter. A `ccharness:<type>` subagent type is a catalog type when that file
exists; any other subagent type (another plugin's, a built-in, a user's own) is not ours and is allowed.

Limits: it looks only at the `model` parameter of the call. A model set by `CLAUDE_CODE_SUBAGENT_MODEL` or by
a settings file is not seen here. Downward overrides are allowed.

Off switch: environment `CCHARNESS_TIER_GUARD=off`.

Fail-open: malformed input, an unreadable agent file, a file without a `model:` line, an unknown pinned
value or any error exits 0 without output.
"""
from __future__ import annotations

import json
import os
import re
import sys

PREFIX = "ccharness:"
TYPE_RE = re.compile(r"^[A-Za-z0-9_-]+$")  # keeps a crafted type from reaching other paths
FAMILIES = (("haiku", 1), ("sonnet", 2), ("opus", 3), ("fable", 4), ("mythos", 4))


def tier(model: str) -> int:
    """Tier of a model name, 0 when unknown. Matches `sonnet`, `claude-sonnet-5-5`, `opus[1m]`."""
    name = model.strip().lower()
    if name.startswith("claude-"):
        name = name[len("claude-"):]
    for family, rank in FAMILIES:
        if name.startswith(family):
            return rank
    return 0


def plugin_root() -> str:
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return root if root else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pinned_model(path: str) -> str | None:
    """`model:` value inside the leading frontmatter block of an agent file, None if there is none."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        match = re.match(r"^model\s*:\s*(.*?)\s*$", line)
        if match:
            return match.group(1).strip("\"'").strip() or None
    return None


def decision(payload: dict) -> str | None:
    """Deny reason, or None to allow."""
    if payload.get("tool_name") not in ("Agent", "Task"):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    subagent = tool_input.get("subagent_type")
    model = tool_input.get("model")
    if not isinstance(subagent, str) or not subagent.startswith(PREFIX):
        return None
    if not isinstance(model, str) or model.strip() in ("", "inherit"):
        return None
    bare = subagent[len(PREFIX):]
    if not TYPE_RE.match(bare):
        return None
    path = os.path.join(plugin_root(), "agents", bare + ".md")
    if not os.path.isfile(path):
        return None  # not a catalog type
    pinned = pinned_model(path)
    base = tier(pinned) if pinned else 0
    if base == 0:
        return None  # no comparable pinned tier: allow
    if tier(model) == 0 or tier(model) > base + 1:
        return (f"ccharness tier guard: '{bare}' is pinned to {pinned} (tier {base}). The only allowed override "
                f"is one tier up, as the single escalation step after a failed run. Drop the model parameter "
                f"or use the next tier.")
    return None


def main() -> int:
    try:
        if os.environ.get("CCHARNESS_TIER_GUARD", "on").strip().lower() == "off":
            return 0
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        reason = decision(payload)
        if reason:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "permissionDecision": "deny",
                                                     "permissionDecisionReason": reason}}))
    except Exception:  # fail-open: a guard must never block a session by accident
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
