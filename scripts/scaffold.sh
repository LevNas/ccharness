#!/usr/bin/env bash
# ccharness scaffold: put the always-on harness into <target> using official files only.
#
#   .claude/rules/<name>.md        rule templates (never overwritten; marker line on top)
#   .claude/settings.json          permissions.deny rules for the standard tier
#                                  (created when absent; otherwise the missing rules are printed)
#   CLAUDE.md                      never written; the snippet path is printed for review
#
# Usage: scaffold.sh [--lang ja|en] [--target DIR] [--dry-run] [--no-settings]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$HERE/.claude-plugin/plugin.json" | head -1)"
LANG_SEL="en"
TARGET="$PWD"
DRY=0
SETTINGS=1

usage() {
  sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --lang) LANG_SEL="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --no-settings) SETTINGS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 64 ;;
  esac
done

TPL_DIR="$HERE/templates/rules/$LANG_SEL"
if [ ! -d "$TPL_DIR" ]; then
  echo "unsupported --lang '$LANG_SEL' (available: $(ls "$HERE/templates/rules" | tr '\n' ' '))" >&2
  exit 64
fi

RULES_DIR="$TARGET/.claude/rules"
MARKER="<!-- ccharness template v$VERSION ($LANG_SEL) -->"
created=0
skipped=0

for tpl in "$TPL_DIR"/*.md; do
  name="$(basename "$tpl")"
  dest="$RULES_DIR/$name"
  if [ -e "$dest" ]; then
    skipped=$((skipped + 1))
    if head -1 "$dest" | grep -q '^<!-- ccharness template' && diff -q <(tail -n +2 "$dest") "$tpl" >/dev/null 2>&1; then
      echo "skip (identical):        $dest"
    elif diff -q "$dest" "$tpl" >/dev/null 2>&1; then
      echo "skip (identical):        $dest"
    else
      echo "skip (exists, differs):  $dest"
      diff_lines="$(diff -u "$tpl" "$dest" | wc -l || true)"
      diff -u "$tpl" "$dest" | head -20 || true
      if [ "$diff_lines" -gt 20 ]; then
        echo "    ... (diff truncated: $diff_lines lines, run 'diff -u $tpl $dest' for all)"
      fi
    fi
    continue
  fi
  echo "create:                  $dest"
  if [ "$DRY" -eq 0 ]; then
    mkdir -p "$RULES_DIR"
    { printf '%s\n' "$MARKER"; cat "$tpl"; } > "$dest"
  fi
  created=$((created + 1))
done

# --- standard tier: official permissions.deny rules -------------------------
SNIPPET="$HERE/templates/settings.snippet.json"
SETTINGS_FILE="$TARGET/.claude/settings.json"
settings_state="skipped"
if [ "$SETTINGS" -eq 1 ]; then
  if [ ! -e "$SETTINGS_FILE" ]; then
    echo "create:                  $SETTINGS_FILE (permissions.deny from templates/settings.snippet.json)"
    if [ "$DRY" -eq 0 ]; then
      mkdir -p "$TARGET/.claude"
      python3 - "$SNIPPET" "$SETTINGS_FILE" <<'PY'
import json, sys
snippet = json.load(open(sys.argv[1], encoding="utf-8"))
out = {"permissions": {"deny": snippet["permissions"]["deny"]}}
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PY
    fi
    settings_state="created"
  else
    settings_state="exists"
    python3 - "$SNIPPET" "$SETTINGS_FILE" <<'PY'
import json, sys
snippet = json.load(open(sys.argv[1], encoding="utf-8"))["permissions"]["deny"]
try:
    current = json.load(open(sys.argv[2], encoding="utf-8"))
except ValueError:
    print(f"skip (exists, not valid JSON): {sys.argv[2]}")
    sys.exit(0)
have = set((current.get("permissions") or {}).get("deny") or [])
missing = [r for r in snippet if r not in have]
if not missing:
    print(f"skip (all deny rules present): {sys.argv[2]}")
else:
    print(f"skip (exists): {sys.argv[2]} - add these to permissions.deny with the user's approval:")
    for r in missing:
        print(f"    {json.dumps(r)}")
PY
  fi
fi

cat <<EOF

CLAUDE.md is never written by scaffold. Review the snippet and append it only with the user's approval:
  $HERE/templates/CLAUDE.md.snippet.$LANG_SEL.md

Suggested .gitignore entries for local workspace files (add if missing):
  .claude/tasks/
  .claude/private/
  .claude/settings.local.json

done: created=$created skipped=$skipped settings=$settings_state lang=$LANG_SEL target=$TARGET dry-run=$DRY
EOF
