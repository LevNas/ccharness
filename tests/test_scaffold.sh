#!/usr/bin/env bash
# Tests for scripts/scaffold.sh. Run: bash tests/test_scaffold.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# 1. dry-run creates nothing
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP" --dry-run)"
[ ! -e "$TMP/.claude" ] || fail "dry-run must not write"
echo "$out" | grep -q 'dry-run=1' || fail "dry-run flag not reported"

# 2. first run creates every en template with the marker line, plus settings.json
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP")"
n_tpl="$(ls "$ROOT/templates/rules/en"/*.md | wc -l)"
n_out="$(ls "$TMP/.claude/rules"/*.md | wc -l)"
[ "$n_tpl" -eq "$n_out" ] || fail "expected $n_tpl files, got $n_out"
for f in "$TMP/.claude/rules"/*.md; do
  head -1 "$f" | grep -q '^<!-- ccharness template v[0-9.]* (en) -->$' || fail "marker missing in $f"
done
echo "$out" | grep -q "created=$n_tpl skipped=0 settings=created" || fail "summary mismatch on first run: $out"
[ -e "$TMP/.claude/settings.json" ] || fail "settings.json not created"
python3 - "$TMP/.claude/settings.json" <<'PY' || fail "settings.json invalid or without deny rules"
import json, sys
d = json.load(open(sys.argv[1]))
assert len(d["permissions"]["deny"]) >= 8
assert "_comment" not in d
PY

# 3. second run is idempotent: nothing created, everything skipped, deny rules all present
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP")"
echo "$out" | grep -q "created=0 skipped=$n_tpl settings=exists" || fail "second run must skip all: $out"
echo "$out" | grep -q 'skip (identical)' || fail "identical files must be reported as identical"
echo "$out" | grep -q 'all deny rules present' || fail "existing complete settings must be reported"

# 4. a user-modified rule file is never overwritten and is reported as differing
first="$(ls "$TMP/.claude/rules"/*.md | head -1)"
echo "user edit" >> "$first"
sum_before="$(cksum "$first")"
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP")"
[ "$sum_before" = "$(cksum "$first")" ] || fail "modified file was overwritten"
echo "$out" | grep -q 'skip (exists, differs)' || fail "differing file not reported"

# 5. an existing settings.json is never rewritten; missing rules are listed
printf '{"permissions": {"deny": ["Bash(git reset --hard*)"]}, "env": {"X": "1"}}\n' > "$TMP/.claude/settings.json"
sum_before="$(cksum "$TMP/.claude/settings.json")"
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP")"
[ "$sum_before" = "$(cksum "$TMP/.claude/settings.json")" ] || fail "existing settings.json was rewritten"
echo "$out" | grep -q 'add these to permissions.deny' || fail "missing rules not listed"
echo "$out" | grep -q 'Bash(git push --force \*)' || fail "a missing rule was not printed"
echo "$out" | grep -qv 'Bash(git reset --hard\*)"$' || true

# 6. --no-settings leaves settings alone
rm "$TMP/.claude/settings.json"
out="$(bash "$ROOT/scripts/scaffold.sh" --lang en --target "$TMP" --no-settings)"
[ ! -e "$TMP/.claude/settings.json" ] || fail "--no-settings must not create settings.json"
echo "$out" | grep -q 'settings=skipped' || fail "--no-settings not reported"

# 7. ja templates include tone.md; en templates do not
[ -e "$ROOT/templates/rules/ja/tone.md" ] || fail "ja/tone.md missing"
[ ! -e "$ROOT/templates/rules/en/tone.md" ] || fail "tone.md must be ja-only"

# 8. CLAUDE.md is never written
[ ! -e "$TMP/CLAUDE.md" ] || fail "CLAUDE.md must not be written"

# 9. unknown lang fails with 64
set +e
bash "$ROOT/scripts/scaffold.sh" --lang xx --target "$TMP" >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 64 ] || fail "unknown lang should exit 64, got $rc"

# 10. base template budget: all ja rules together stay under 12 KB
total=$(cat "$ROOT/templates/rules/ja"/*.md | wc -c)
[ "$total" -le 12288 ] || fail "ja rule templates exceed 12 KB budget: $total"

echo "OK: scaffold tests passed ($n_tpl en templates, ja rules total ${total} bytes)"
