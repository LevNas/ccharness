---
name: session-end-cleanup
description: セッション終了時や「不要ブランチを棚卸しして」の依頼で、マージ済み・upstream 消失のローカルブランチと worktree を検出し、削除候補を A（即削除可）/ B（worktree あり）に分類して利用者の判断を仰ぐ。削除は実行しない。
---

# session-end-cleanup — ブランチ / worktree の棚卸し

本スキルは**検出と提案だけ**を行い、削除は利用者の判断に委ねます。

## トリガー

- セッション終了時（session-wrap の後）
- マージ指示を受けたあと
- 「不要ブランチを棚卸しして」の依頼

## 手順

1. リモートの削除を反映します: `git fetch origin --prune`
2. 情報を集めます:
   - main にマージ済み: `git branch --merged main --format '%(refname:short)'`
   - upstream が消えたもの: `git for-each-ref --format '%(refname:short) %(upstream:track)' refs/heads | grep gone`
   - worktree に載っているブランチ: `git worktree list --porcelain`
3. 分類します。保護対象（`main` `master` `develop` `release` と現在のブランチ）は除外します。
   - **A. 即削除可**: マージ済みまたは upstream 消失、かつ worktree なし → `git branch -d <branch>`
   - **B. 削除待機**: 同上だが worktree あり → 先に `git worktree remove <path>`、その後 `git branch -d <branch>`。worktree 内の未追跡ファイル（作業ログ、capture など）はメイン側へ退避してから削除します。
   - **C. 現役**: それ以外。触れません。
4. 分類結果とコマンドを提示し、実行するかを利用者に確認します。

## 注意

- `-D`（強制削除）は、マージ済みでない差分を捨てることになるため、利用者が明示した場合だけ使います。
- 別セッションが使用中の worktree は削除しません。
