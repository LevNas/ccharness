---
name: local-workspace-files
description: ローカル作業ファイル（個人プラン・作業ログ・個人設定）の扱いの詳細。共有しない理由、.gitignore の構成、.worktreeinclude による worktree への持ち込みと書き戻し。骨子は rules/local-workspace-files.md。
license: MIT
allowed-tools: Read, Bash
---

# ローカル作業ファイルの扱い（詳細）

骨子は `.claude/rules/local-workspace-files.md` にあります。ここでは理由と手順を補います。

## なぜ共有しないのか

- 個人の進捗やプランは、他のメンバーには文脈が無く、読まれない上にレビュー負荷になります。
- 機微な背景（人事・評価・個人事情）は最小化の原則で共有リポジトリに置きません。
- 個人環境の値（パス、ホスト名、好み）を共有設定に入れると、他の環境で壊れます。

## .gitignore の構成

```
.claude/tasks/
.claude/private/
.claude/settings.local.json
.claude/worktrees/
CLAUDE.local.md
*.timelog
```

チームで共有すると決めたもの（例: プロジェクト共通のタスク台帳）は、決めた時点で除外から外します。`.claude/worktrees/` を除外しておくと、worktree の中身がメイン checkout の未追跡として現れません。

## worktree セッションでの扱い

- **持ち込み（メイン → worktree）**: 新しい worktree は追跡ファイルだけの checkout なので、`.env` や `settings.local.json` のような gitignore 済みファイルは入りません。プロジェクトルートの `.worktreeinclude` にパターン（gitignore 構文）を書くと、Claude Code が作る worktree（`--worktree`、サブエージェントの worktree、デスクトップの並行セッション）へ自動でコピーされます。gitignore 済みで、かつパターンに一致するファイルだけが対象です。

  ```
  .env
  .claude/settings.local.json
  ```

- **read-through**: worktree のルートに `.claude/skills` が無ければ、メイン checkout のスキル・エージェント・コマンドが読まれます。gitignore しているスキルをコピーする必要はありません。
- **分岐元**: 既定はリモートの既定ブランチ（`worktree.baseRef: "fresh"`）。未 push の作業を持ち込むなら `"head"` にします。
- **書き戻し（worktree → メイン）**: worktree で生じた未追跡の作業ファイル（capture、ログ）は、worktree を削除する前にメイン側の同じ場所へ移します。同名衝突があれば、セッション識別子を付けて残します。
- **経路が使えないとき**: 一時ディレクトリに退避してから、利用者に場所を報告します。

## 個人設定の置き場

| 内容 | 置き場 |
|---|---|
| 全リポジトリ共通の自分の流儀 | `~/.claude/CLAUDE.md`、`~/.claude/rules/` |
| このリポジトリだけの個人メモ | `CLAUDE.local.md`（gitignore） |
| 権限・環境変数の個人差分 | `.claude/settings.local.json` |
