---
name: patch-ownership-check
description: Gate an AI-generated code patch by probe size, future ownership cost, test integrity, content-addressed evidence, and never-cheap risk categories. Use before accepting or merging an AI-generated patch.
---

# patch-ownership-check

AI 生成パッチを「いま動くか」でなく、人間が将来も所有できる条件で対話的に確認します。
`aidr check-patch-ownership` の薄いラッパーです。定義から質問を読み、証拠を推測せず、
GREEN / YELLOW / RED と次の行動をユーザー向けに翻訳します。

## いつ使うか

- coding agent が生成した commit / PR / diff を受け入れる前
- テストは成功しているが、長期保守・責任分界・test integrity を再確認したいとき
- 認可・削除・課金・規制・公開契約の変更を、人間の採否判断へ確実に回したいとき
- 自社の patch-ownership overlay を含めて受入ゲートを実行したいとき

## ユーザーから受け取るもの

- 対象の commit SHA、PR、または diff のパス
- 将来 owner の参照(`user:<id>` / `team:<id>` / `codeowners:<path>`)
- test・risk manifest・必要な review route の content-addressed ref
- 任意: 適用する patch-ownership overlay YAML のパス(複数可)

## 手順

1. 対象と overlay を確認する。最初は read-only で差分・テスト・所有情報を調べる。
   ユーザーの明示承認なしに編集、commit、push、merge、外部送信をしない。

2. `definitions/patch-ownership.yaml` を読み、質問をこの skill にハードコードしない。
   overlay があれば先に `bin/aidr check-overlay <path>` で検証する。質問を提示するときは
   `text_ja` を優先し、無ければ `text` を使う。

3. 変更ファイルと意味的変更を確認し、probe / ownership / hollow_green /
   never_cheap の全 question を明示的な yes / no にする。曖昧ならユーザーへ確認し、
   勝手に no にしない。never-cheap は 5 種すべてを確認する。

4. patch、risk manifest、test、必要なら human review route を content-addressed ref にする。
   `test_status=present` は実在する test ref、`not_applicable` は実在する根拠 ref が必須。
   test / review / owner / approval の証拠を推測・捏造しない。確認できなければ
   `absent` または no とする。

5. raw diff や秘密値を入力・レポートへ複製しない。full commit SHA、相対パス、digest、
   redacted summary だけを使う。secret らしき値を見つけたら内容を表示せず所在だけ報告する。

6. `bin/aidr init --target patch-ownership --format csv` で問い付きテンプレートを
   `/tmp/aidr-patch-ownership-<timestamp>.csv` に生成し、質問列を保ったまま回答する。
   overlay があれば `--overlay <path>` を付ける。

7. `bin/aidr check-patch-ownership <tmp.csv> --format json` を実行する。
   overlay があれば同じ順序で `--overlay <path>` を追加し、stdout と exit code を取得する。

8. JSON をユーザー向けに翻訳する。region、never-cheap risk、missing controls、
   evidence ref は形式検証のみで参照先を取得していないことを報告する。
   GREEN は「受入判断へ進める」、YELLOW は「指名 owner が採否判断」、
   RED は「受入不可」と訳す。GREEN でも自動 merge しない。

9. CLI 判定と人間の最終採否を別の decision record に残すよう促す。手順は次のとおり:
   `bin/aidr check-patch-ownership <tmp.csv> --emit-decision-record <path> --team <name>` を
   同じ回答で再実行し、pending の決定記録を JSONL に追記する。人間が採否を決めたら、
   `decision` / `discard_reason` / `note` / `decided_on` をユーザーに追記してもらう
   (`gate` ブロックはゲート機械側の転記なので書き換えない)。月次では
   `bin/aidr summarize-patch-decisions <path または dir>` で破棄率・決定済み率を振り返る。
   詳細は `docs/12_patch_decision_loop.md` と `patch-decision-summary` skill を参照する。
   sandbox や権限で読めない対象は迂回せず、必要な最小権限をユーザーへ求める。

## 出力の作法

- 結論(`[GREEN]` / `[YELLOW]` / `[RED]` / `[ERROR]`)を先頭に置く
- `risk_ids` と `missing_controls` を ID のまま示し、その後に平易な説明を付ける
- 証拠参照の中身や raw diff を繰り返さず、確認済み / 未確認の境界を明示する
- GREEN を「merge 可」、YELLOW を「条件付き自動承認」と言い換えない

## 失敗時の扱い

- exit 3: 未回答・未知 ID・重複 key・不正 ref / enum / overlay を直して再実行する
- test ref の実体を確認できない: 形式だけ整えて `present` にしない
- 高リスクで review route がない: RED のまま止め、review 済みとして扱わない
- overlay が `check-overlay` に通らない: 違反を提示し、半端に適用して採点しない
- sandbox / 権限で対象を読めない: 迂回・権限昇格せず、ユーザーに確認する
