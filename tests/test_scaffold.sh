#!/usr/bin/env bash
# Tests for scripts/scaffold.sh. Run: bash tests/test_scaffold.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

n_tpl="$(ls "$ROOT/templates/rules/en"/*.md | wc -l)"
n_skill="$(ls -d "$ROOT/templates/skills/en"/*/ | wc -l)"

# 1. dry-run creates nothing
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP" --dry-run)"
[ ! -e "$TMP/.claude" ] || fail "dry-run must not write"
echo "$out" | grep -q 'dry-run=1' || fail "dry-run flag not reported"

# 2. first run creates every en rule template with the marker line, every skill, and settings.json
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP")"
n_out="$(ls "$TMP/.claude/rules"/*.md | wc -l)"
[ "$n_tpl" -eq "$n_out" ] || fail "expected $n_tpl rule files, got $n_out"
for f in "$TMP/.claude/rules"/*.md; do
  head -1 "$f" | grep -q '^<!-- ccharness template v[0-9.]* (en) -->$' || fail "marker missing in $f"
done
n_sk_out="$(ls "$TMP/.claude/skills"/*/SKILL.md | wc -l)"
[ "$n_skill" -eq "$n_sk_out" ] || fail "expected $n_skill skills, got $n_sk_out"
for f in "$TMP/.claude/skills"/*/SKILL.md; do
  head -1 "$f" | grep -qx -- '---' || fail "skill must start with frontmatter: $f"
  grep -q '^name: ' "$f" || fail "skill frontmatter lacks name: $f"
  grep -q '^description: ' "$f" || fail "skill frontmatter lacks description: $f"
  # marker sits right after the closing frontmatter line
  awk 'NR==1{next} $0=="---"{getline nxt; if (nxt ~ /^<!-- ccharness template v[0-9.]+ \(en\) -->$/) ok=1; exit} END{exit ok?0:1}' "$f" \
    || fail "marker not right after frontmatter: $f"
done
echo "$out" | grep -q "created=$n_tpl skipped=0 skills_created=$n_skill skills_skipped=0 settings=created" || fail "summary mismatch on first run: $out"
[ -e "$TMP/.claude/settings.json" ] || fail "settings.json not created"
python3 - "$TMP/.claude/settings.json" <<'PY' || fail "settings.json invalid or without deny rules"
import json, sys
d = json.load(open(sys.argv[1]))
assert len(d["permissions"]["deny"]) >= 8
assert "_comment" not in d
PY

# 3. second run is idempotent
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP")"
echo "$out" | grep -q "created=0 skipped=$n_tpl skills_created=0 skills_skipped=$n_skill settings=exists" || fail "second run must skip all: $out"
echo "$out" | grep -q 'skip (identical)' || fail "identical files must be reported as identical"
echo "$out" | grep -q 'all deny rules present' || fail "existing complete settings must be reported"

# 4. a user-modified rule file is never overwritten and is reported as differing
first="$(ls "$TMP/.claude/rules"/*.md | head -1)"
echo "user edit" >> "$first"
sum_before="$(cksum "$first")"
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP")"
[ "$sum_before" = "$(cksum "$first")" ] || fail "modified file was overwritten"
echo "$out" | grep -q 'skip (exists, differs)' || fail "differing file not reported"

# 5. a user-modified skill is never overwritten
sk="$TMP/.claude/skills/dev-shipper/SKILL.md"
echo "team addition" >> "$sk"
sum_before="$(cksum "$sk")"
bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP" >/dev/null
[ "$sum_before" = "$(cksum "$sk")" ] || fail "modified skill was overwritten"

# 6. an existing settings.json is never rewritten; missing rules are listed
printf '{"permissions": {"deny": ["Bash(git reset --hard*)"]}, "env": {"X": "1"}}\n' > "$TMP/.claude/settings.json"
sum_before="$(cksum "$TMP/.claude/settings.json")"
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP")"
[ "$sum_before" = "$(cksum "$TMP/.claude/settings.json")" ] || fail "existing settings.json was rewritten"
echo "$out" | grep -q 'add these to permissions.deny' || fail "missing rules not listed"
echo "$out" | grep -q 'Bash(git push --force \*)' || fail "a missing rule was not printed"

# 7. --no-settings and --no-skills leave those parts alone
rm "$TMP/.claude/settings.json"
rm -r "$TMP/.claude/skills"
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP" --no-settings --no-skills)"
[ ! -e "$TMP/.claude/settings.json" ] || fail "--no-settings must not create settings.json"
[ ! -e "$TMP/.claude/skills" ] || fail "--no-skills must not create skills"
echo "$out" | grep -q 'skills_created=0 skills_skipped=0 settings=skipped' || fail "--no-settings/--no-skills not reported"

# 8. ja templates include tone.md; en templates do not; ja and en ship the same skill set
[ -e "$ROOT/templates/rules/ja/tone.md" ] || fail "ja/tone.md missing"
[ ! -e "$ROOT/templates/rules/en/tone.md" ] || fail "tone.md must be ja-only"
diff <(ls "$ROOT/templates/skills/ja") <(ls "$ROOT/templates/skills/en") >/dev/null || fail "ja and en skill sets differ"
for l in ja en; do
  [ -e "$ROOT/templates/skills/$l/arc-handoff/SKILL.md" ] || fail "$l arc-handoff skill missing"
  grep -q '^## Compact Instructions$' "$ROOT/templates/CLAUDE.md.snippet.$l.md" || fail "$l snippet lacks Compact Instructions"
done
# arc-handoff carries the three handoff elements in both languages: point instead of copying, redact, name the next skills
for pair in "en|Point, don't copy" "en|Redact before writing" "en|the skills the next arc should call" \
            "ja|場所を指す" "ja|書く前に伏せる" "ja|次のアークで使うスキル"; do
  l="${pair%%|*}"; phrase="${pair#*|}"
  grep -qF -- "$phrase" "$ROOT/templates/skills/$l/arc-handoff/SKILL.md" || fail "$l arc-handoff lacks: $phrase"
done
# session-wrap hands this session's repeated failures to promote-to-computation, in both languages
for l in ja en; do
  grep -qF -- "/promote-to-computation" "$ROOT/templates/skills/$l/session-wrap/SKILL.md" || fail "$l session-wrap lacks the repeated-failure step"
  grep -qF -- "[ccevolve] 同じ失敗が" "$ROOT/templates/skills/$l/session-wrap/SKILL.md" || fail "$l session-wrap does not say how to recognise the repeat note"
done
# dev-shipper and the snippet point at diagnosing-bugs, and the snippet asks for checks seen able to fail, in both languages
for pair in "skills/en/dev-shipper/SKILL.md|read the test rules of \`ccharness:diagnosing-bugs\`" \
            "skills/ja/dev-shipper/SKILL.md|\`ccharness:diagnosing-bugs\` のテストの決まり" \
            "CLAUDE.md.snippet.en.md|investigate autonomously with \`ccharness:diagnosing-bugs\`" \
            "CLAUDE.md.snippet.ja.md|\`ccharness:diagnosing-bugs\` で自律的に調査" \
            "CLAUDE.md.snippet.en.md|with tests or logs you have seen able to fail" \
            "CLAUDE.md.snippet.ja.md|落ちうることを確かめたテストかログで"; do
  f="${pair%%|*}"; phrase="${pair#*|}"
  grep -qF -- "$phrase" "$ROOT/templates/$f" || fail "$f lacks: $phrase"
done

# 9. CLAUDE.md is never written
[ ! -e "$TMP/CLAUDE.md" ] || fail "CLAUDE.md must not be written"

# 10. unknown lang fails with 64
set +e
bash "$ROOT/scripts/scaffold.sh" --lang xx --target "$TMP" >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 64 ] || fail "unknown lang should exit 64, got $rc"

# 11. budgets: ja rules <= 12 KB; each skill description <= 320 bytes (always-on cost per repository)
total=$(cat "$ROOT/templates/rules/ja"/*.md | wc -c)
[ "$total" -le 12288 ] || fail "ja rule templates exceed 12 KB budget: $total"
for f in "$ROOT/templates/skills"/*/*/SKILL.md; do
  d=$(grep -m1 '^description: ' "$f" | wc -c)
  [ "$d" -le 320 ] || fail "description too long ($d bytes) in $f"
done

# 12. the instruction-file report: which file the CLAUDE.md snippet goes to, never written
snippet_head="$(head -1 "$ROOT/templates/CLAUDE.md.snippet.en.md")"
case_dir() { d="$TMP/case-$1"; mkdir -p "$d"; printf '%s' "$d"; }
report() { bash "$ROOT/scripts/scaffold.sh" --lang en --target "$1" --dry-run --no-settings --no-skills; }

d="$(case_dir agents-only)"; echo "# shared agent notes" > "$d/AGENTS.md"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=create-import' || fail "AGENTS.md only must report create-import: $out"
echo "$out" | grep -q '^claude-md: create-import' || fail "AGENTS.md only: report line missing: $out"
echo "$out" | grep -qF '@AGENTS.md' || fail "create-import must name the @AGENTS.md import: $out"

d="$(case_dir both)"; echo "# project" > "$d/CLAUDE.md"; echo "# agents" > "$d/AGENTS.md"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=append' || fail "CLAUDE.md and AGENTS.md must report append: $out"
echo "$out" | grep -q "^claude-md: append .*$d/CLAUDE.md" || fail "append must name CLAUDE.md: $out"

d="$(case_dir none)"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=ask' || fail "no instruction file must report ask: $out"

d="$(case_dir current)"; printf '# project\n\n%s\n## Workflow Rules\n' "$snippet_head" > "$d/CLAUDE.md"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=current' || fail "same snippet version must report current: $out"

d="$(case_dir older)"; printf '# project\n\n<!-- ccharness template v0.0.1 (en): old -->\n' > "$d/CLAUDE.md"
tpl_ver="$(echo "$snippet_head" | sed -n 's/^<!-- ccharness template v\([0-9.]*\) .*/\1/p')"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=review' || fail "older snippet version must report review: $out"
echo "$out" | grep '^claude-md: review' | grep -q "v0.0.1" || fail "review must name the file's version: $out"
echo "$out" | grep '^claude-md: review' | grep -q "v$tpl_ver" || fail "review must name the template's version: $out"

d="$(case_dir dot-claude)"; mkdir -p "$d/.claude"; echo "# project" > "$d/.claude/CLAUDE.md"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=append' || fail ".claude/CLAUDE.md must report append: $out"
echo "$out" | grep -q "^claude-md: append .*$d/.claude/CLAUDE.md" || fail "append must name .claude/CLAUDE.md: $out"

# a marker in AGENTS.md counts only while AGENTS.md is read: no CLAUDE.md, or a CLAUDE.md that imports it
d="$(case_dir agents-marker-hidden)"; echo "# project" > "$d/CLAUDE.md"; printf '%s\n' "$snippet_head" > "$d/AGENTS.md"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=append' || fail "a CLAUDE.md that does not import AGENTS.md hides its marker, so append: $out"
echo "$out" | grep -q "^claude-md: append .*$d/CLAUDE.md" || fail "append must name CLAUDE.md when AGENTS.md is hidden: $out"

d="$(case_dir agents-marker-imported)"; printf '@AGENTS.md\n\n# project\n' > "$d/CLAUDE.md"; printf '%s\n' "$snippet_head" > "$d/AGENTS.md"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=current' || fail "a CLAUDE.md that imports AGENTS.md makes its marker count: $out"

d="$(case_dir agents-marker-only)"; printf '%s\n' "$snippet_head" > "$d/AGENTS.md"
out="$(report "$d")"
echo "$out" | grep -q 'claude_md=current' || fail "AGENTS.md alone is read, so its marker counts: $out"

# a real run (no --dry-run) still writes neither CLAUDE.md nor AGENTS.md
d="$(case_dir agents-real)"; echo "# shared agent notes" > "$d/AGENTS.md"
sum_before="$(cksum < "$d/AGENTS.md")"
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$d" --no-settings --no-skills)"
[ ! -e "$d/CLAUDE.md" ] || fail "scaffold must not create CLAUDE.md"
[ "$sum_before" = "$(cksum < "$d/AGENTS.md")" ] || fail "scaffold must not change AGENTS.md"
echo "$out" | grep -q 'claude_md=create-import' || fail "real run must report the same action: $out"

echo "OK: scaffold tests passed ($n_tpl en rules, $n_skill skills, ja rules total ${total} bytes)"
