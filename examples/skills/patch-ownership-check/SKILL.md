---
name: patch-ownership-check
description: Gate an AI-generated code patch by probe size, future ownership cost, test integrity, content-addressed evidence, and never-cheap risk categories. Use before accepting or merging an AI-generated patch.
---

# patch-ownership-check

AI 生成パッチの「現在の成功」ではなく、人間が将来も所有できる条件を対話的に確認し、
`aidr check-patch-ownership` の GREEN / YELLOW / RED に翻訳します。

## 安全境界

- 最初は read-only で差分・テスト・所有情報を調べる。ユーザーの明示承認なしに
  ファイル編集、commit、push、merge、外部送信をしない
- raw diff や秘密値を入力・レポートへ複製しない。full commit SHA、相対パス、digest、
  要約だけを使う。シークレットらしき値を見つけたら内容を表示せず所在だけ報告する
- テスト、review、owner、approval の証拠を推測・捏造しない。確認できなければ
  `absent` または no とする
- GREEN でも自動 merge しない。最終 decision record は人間が別に残す
- sandbox や権限で読めない対象は迂回せず、必要な最小権限をユーザーへ求める

## 手順

1. 対象の commit / PR / diff と、任意の overlay を確認する。`definitions/patch-ownership.yaml`
   を読み、質問をハードコードしない。overlay は先に `bin/aidr check-overlay` で検証する。
2. 変更ファイルと意味的変更を read-only で確認し、5 種の never-cheap リスクをすべて
   明示的な yes/no にする。曖昧ならユーザーへ確認し、勝手に no にしない。
3. probe、future ownership、hollow-green の全質問を明示的な yes/no で埋める。
   将来 owner は `user:` / `team:` / `codeowners:` の参照で記録する。
4. patch、risk manifest、test、必要なら human review route を content-addressed ref にする。
   `test_status=present` は実在する test ref、`not_applicable` は実在する根拠 ref が必須。
5. `bin/aidr init --target patch-ownership --format csv` で一時入力を作り、質問列を保ったまま
   回答する。一時ファイルにも raw diff や secrets を書かない。
6. `bin/aidr check-patch-ownership <input> --format json` を実行する。
7. region、never-cheap risk、missing controls、参照先を取得していないという制約を先に報告する。
   GREEN は「受入判断へ進める」、YELLOW は「人間が採否判断」、RED は「受入不可」と訳す。

## 失敗時

- exit 3 は入力契約違反。列挙された未回答・未知 ID・不正 ref を直して再実行する
- test ref の実体を確認できない場合、形式だけ整えて `present` にしない
- 高リスクで review route がない場合は RED のまま止め、レビューを実行したことにしない
