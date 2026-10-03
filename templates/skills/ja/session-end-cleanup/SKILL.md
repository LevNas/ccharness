---
name: session-end-cleanup
description: セッション終了時・マージ後・「不要ブランチを棚卸しして」の依頼で、ccharness:worktree-sweep でブランチと worktree を棚卸しし、何を消すかを利用者に確かめる。削除は実行しない。
license: MIT
allowed-tools: Bash, Read
---

# session-end-cleanup — ブランチ / worktree の棚卸し

本スキルは**検出と提案だけ**を行い、削除は利用者の判断に委ねます。

## トリガー

- セッション終了時（session-wrap の後）
- マージ指示を受けたあと
- 「不要ブランチを棚卸しして」の依頼

## 手順

1. メインの checkout で作業します。このセッションが worktree に分けられているときは、先に `ExitWorktree`（`action: keep`）で抜けます。
2. **`ccharness:worktree-sweep`** スキルを呼びます。fetch のあと、失うものが無ければベースブランチを fast-forward し、ブランチと worktree を delete（消してよい）/ review（判断が要る）/ in-use（使用中）に分けて、実行するコマンドを示します。
3. 報告を示し、どのコマンドを実行するかを利用者に確かめます。実行するのは、そのコマンドだけです。

### ccharness が無いとき

スキルが使えないときは、同じことを手作業で行います。

1. `git fetch origin --prune` のあと、メインの checkout でベースブランチを `git pull --ff-only` します（手元のベースブランチが古いと、あとの判定が狂います）。
2. ブランチごとに、表示ではなく中身で判定します。
   - `git merge-base --is-ancestor <branch> origin/main` が成功 → マージ済み
   - 失敗なら `git cherry origin/main <branch>`: すべて `-` → 同じ内容が取り込み済み。`+` が 1 つでもある → 未マージ
   - `[gone]` は「リモートのブランチが消えた」という意味だけで、マージ済みの証拠にはなりません。
3. worktree があるブランチは、`git -C <worktree> status --porcelain --ignored` も確かめます。未コミット・未追跡・gitignore 済みのファイルがすべて対象です。`git worktree remove` は前の 2 つなら断りますが、gitignore 済みのファイルは確認なしに消します。
4. 示し方: **delete**（マージ済みで何も残っていない）には `git worktree remove <path>`（`--force` なし）と `git branch -d <branch>`。**review**（それ以外）には理由を添えます。動いているセッションがロックしている worktree には触れません。

## 注意

- `-D`（強制削除）はマージされていない作業を捨てます。`git cherry` がすべて `-` のときだけ提案し、利用者が同意したときだけ実行します。
- 別のセッションが使用中の worktree は削除しません。
