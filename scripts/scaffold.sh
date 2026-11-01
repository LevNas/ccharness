#!/usr/bin/env bash
# ccharness scaffold: put the always-on harness into <target> using official files only.
#
#   .claude/rules/<name>.md          rule templates (never overwritten; marker line on top)
#   .claude/skills/<name>/SKILL.md   behaviour skills (never overwritten; marker after the
#                                    frontmatter; each repository owns and adapts them)
#   .claude/settings.json            permissions.deny rules for the standard tier
#                                    (created when absent; otherwise the missing rules are printed)
#   CLAUDE.md                        never written; reports which file the snippet goes to
#                                    (append / create-import / ask / current / review)
#
# Usage: scaffold.sh [--lang ja|en] [--target DIR] [--dry-run] [--no-settings] [--no-skills]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$HERE/.claude-plugin/plugin.json" | head -1)"
LANG_SEL="en"
TARGET="$PWD"
DRY=0
SETTINGS=1
SKILLS=1

usage() {
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --lang) LANG_SEL="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --no-settings) SETTINGS=0; shift ;;
    --no-skills) SKILLS=0; shift ;;
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

# --- always-on tier: rule files ---------------------------------------------
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

# --- on-demand tier: behaviour skills (repository-owned copies) -------------
skills_created=0
skills_skipped=0
SKILL_TPL_DIR="$HERE/templates/skills/$LANG_SEL"
if [ "$SKILLS" -eq 1 ] && [ -d "$SKILL_TPL_DIR" ]; then
  for tpl in "$SKILL_TPL_DIR"/*/SKILL.md; do
    name="$(basename "$(dirname "$tpl")")"
    dest="$TARGET/.claude/skills/$name/SKILL.md"
    if [ -e "$dest" ]; then
      skills_skipped=$((skills_skipped + 1))
      echo "skip (exists):           $dest"
      continue
    fi
    echo "create:                  $dest"
    if [ "$DRY" -eq 0 ]; then
      mkdir -p "$(dirname "$dest")"
      # Insert the marker right after the frontmatter so the file stays a valid skill.
      awk -v marker="$MARKER" '
        NR == 1 && $0 == "---" { infm = 1 }
        { print }
        infm && NR > 1 && $0 == "---" { print marker; infm = 0 }
      ' "$tpl" > "$dest"
    fi
    skills_created=$((skills_created + 1))
  done
fi

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

# --- CLAUDE.md snippet: report which file it goes to (never written here) ----
# Claude Code reads AGENTS.md only when no CLAUDE.md, .claude/CLAUDE.md or
# CLAUDE.local.md exists, so creating a CLAUDE.md next to an AGENTS.md hides it
# unless the new file imports it. The snippet's own marker (first line,
# "<!-- ccharness template v<version> (<lang>): ...") tells whether it is in already.
CLAUDE_SNIPPET="$HERE/templates/CLAUDE.md.snippet.$LANG_SEL.md"
snippet_marker_version() {
  sed -n 's/^<!-- ccharness template v\([0-9][0-9.]*\) ([a-z]*):.*/\1/p' "$1" | head -1
}
snippet_ver="$(snippet_marker_version "$CLAUDE_SNIPPET")"
marker_file=""
marker_ver=""
for f in "$TARGET/CLAUDE.md" "$TARGET/.claude/CLAUDE.md" "$TARGET/AGENTS.md"; do
  [ -f "$f" ] || continue
  v="$(snippet_marker_version "$f")"
  if [ -n "$v" ]; then
    marker_file="$f"
    marker_ver="$v"
    break
  fi
done

echo
if [ -n "$marker_file" ] && [ "$marker_ver" = "$snippet_ver" ]; then
  claude_md="current"
  echo "claude-md: current       $marker_file has the snippet v$marker_ver, the same as the template; nothing to add"
elif [ -n "$marker_file" ]; then
  claude_md="review"
  echo "claude-md: review        $marker_file has the snippet v$marker_ver, the template is v$snippet_ver; do not append a second copy, compare the two with the user"
elif [ -f "$TARGET/CLAUDE.md" ]; then
  claude_md="append"
  echo "claude-md: append        $TARGET/CLAUDE.md (no snippet marker yet)"
elif [ -f "$TARGET/.claude/CLAUDE.md" ]; then
  claude_md="append"
  echo "claude-md: append        $TARGET/.claude/CLAUDE.md (no snippet marker yet)"
elif [ -f "$TARGET/AGENTS.md" ]; then
  claude_md="create-import"
  echo "claude-md: create-import $TARGET/CLAUDE.md with @AGENTS.md on its first line, then the snippet"
  echo "    (AGENTS.md is the only instruction file; once a CLAUDE.md exists Claude Code stops reading AGENTS.md directly, so the new file imports it)"
else
  claude_md="ask"
  echo "claude-md: ask           neither CLAUDE.md nor AGENTS.md exists in $TARGET; ask the user which file to create"
fi
if [ -f "$TARGET/CLAUDE.local.md" ]; then
  echo "    note: $TARGET/CLAUDE.local.md exists; it is personal and never the target"
fi

cat <<EOF
CLAUDE.md is never written by scaffold. Act on the claude-md line only with the user's approval; the snippet is:
  $CLAUDE_SNIPPET

Suggested .gitignore entries for local workspace files (add if missing):
  .claude/tasks/
  .claude/private/
  .claude/settings.local.json

done: created=$created skipped=$skipped skills_created=$skills_created skills_skipped=$skills_skipped settings=$settings_state lang=$LANG_SEL target=$TARGET dry-run=$DRY claude_md=$claude_md
EOF
