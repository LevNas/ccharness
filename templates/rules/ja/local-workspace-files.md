# ローカル作業ファイルの扱い

個人の作業状態は共有リポジトリにコミットしません。

## コミットしないもの

- 個人のプラン・進捗（`.claude/tasks/` など。チームで共有すると決めたものを除く）
- 機微な個人情報・背景（`.claude/private/`）
- 作業ログ、タイムログ、一時出力
- 個人環境の設定（`.claude/settings.local.json`、エディタ設定）

`.gitignore` に列挙します。迷ったらコミットせず、利用者に確認します。

## 個人環境の事情を共有設定に持ち込まない

`CLAUDE.md`、`.claude/settings.json`、`.claude/rules/` は共有物です。個人の環境固有の値・パス・好みは `~/.claude/` か `settings.local.json` に置きます。

## worktree セッションとのやり取り

- gitignore 済みのローカルファイルを新しい worktree に持ち込むには、プロジェクトルートの `.worktreeinclude`（gitignore 構文）に書きます。手作業でコピーしません。
- 分離 worktree で生じた未追跡の作業ファイルは、worktree を削除する前にメイン側へ退避します。
