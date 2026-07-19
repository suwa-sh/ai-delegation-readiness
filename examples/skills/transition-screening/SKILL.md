---
name: transition-screening
description: Screen a user's task groups into the four AI-transition types (growth / high automation / reorganization / minimal change) before any delegation scoring. Loads definitions/transition-screening.yaml, asks the 3 axes' questions per task group, runs `aidr screen-transition`, and reports the delegation-design priority order with HITL flags. Use when the user asks "where should we start with AI?", "which tasks to delegate first?", or wants a workforce-transition map before headcount talk.
---

# transition-screening

ユーザーのタスク群を AI 移行 4 類型に対話的に分類します。
`aidr screen-transition` CLI の薄いラッパーです: 対話で回答を集め、
task-groups YAML を書き出し、CLI を JSON モードで実行し、結果を
「どこから委任設計を始めるか」の地図 — headcount を最後に置く意思決定順序つき —
に翻訳します。

## いつ使うか

- **どのタスク群から** AI に手を付けるかを決めたいとき
  (`score-delegation` で判定単位を採点する前の段階)
- 「うちの仕事はどれが成長 / 自動化 / 再編か」という移行マップを、
  機械可読のレンズで作りたいとき
- 顧客提案で「4 類型マップ → 委任設計 → headcount は最後」の意思決定順序を
  出典・確度ラベル付きで示したいとき

## ユーザーから受け取るもの

- タスク群のリスト(自由記述。3〜10 群が扱いやすい)。タスク群は
  まとまりのあるタスクの束(例: 「経費精算チェック」「顧客サポートチャット」)で、
  職種名ではない。
- 任意: 自社質問を追加する overlay YAML のパス

## 手順

1. タスク群を聞く。職種名でなくタスクの束に誘導する
   (スクリーニングは「誰がやっているか」でなく「仕事が何か」を採点する)。

2. `definitions/transition-screening.yaml` を読んで 3 軸の質問を取得する。
   質問をハードコードしない — 必ず定義ファイルから読む。
   **ユーザーに質問を提示するときは `text_ja` を優先し、無ければ `text` を使う**。

3. タスク群ごとに、軸単位で質問を出す(technical_exposure E1〜E3、
   human_necessity H1〜H3、demand_elasticity D1〜D3)。**全質問に回答が必須**
   (fail-closed): CLI は未回答を拒否するので、スキップしない。ユーザーが
   迷ったら yes/no を決められるまで話し合う。代わりに推測しない。

4. `bin/aidr init --target transition --format csv`(overlay があれば `--overlay <path>` を
   付ける)で問い付きテンプレートを `/tmp/aidr-screening-<timestamp>.csv` に生成し、
   タスク群の数だけエンティティ列を複製して回答を書き込む(行 = 質問、列 = タスク群。
   質問列は消さない)。記入例: `examples/task-groups/sample-task-groups.csv`。

5. `bin/aidr screen-transition <tmp.csv> --format json` を実行する
   (overlay があれば `--overlay <path>`)。stdout を取得する。

6. JSON をユーザー向けに翻訳する。CLI が返す委任優先度順のまま:
   - **再編(reorganization)** を先頭に: 設計が最も重いゾーン
     (人は残るが人員需要は減りうる。役割再設計が必要)と明示する
   - **高自動化(high_automation)**: 次の一手を勧める — **まず
     `aidr check-readiness` で業務の readiness を診断し(BLOCK なら改善が先)、
     PASS 後に `aidr score-delegation` で具体的な判定を採点する**。
     readiness 診断を飛ばして判定採点だけで委任を始めさせない
   - `human_control_required: true` の群: 類型がどれであっても、
     権利・財務・健康・規制の領域は人間が最終判断を持つと明言する
   - 締めは `action` テキストの意思決定順序で: タスク分解 → 仕分け →
     役割再定義 → reskill → **headcount は最後**

7. 出典を求められたら、JSON 出力の `case_evidence` を**確度ラベルごと**引用する。
   `claim_needs_verification` の数値(WEF の redeploy 目安など)を、顧客向け
   資料で確定事実として提示しない。

## 出力の作法

- 優先度順の地図を先に、説明の文章を後に。
- 要約に「予測ではなく準備の地図」の枠組みを残す — スクリーニング結果は
  「どこから設計を始めるか」であり、「誰を減らすか」ではない。
- 境界すれすれの分類(軸がちょうど閾値)には、人間の再確認を促す 1 行を添える。

## 失敗時の扱い

- `bin/aidr` が PATH に無い場合は、`PYTHONPATH` にリポの `src/` を設定して
  `python -m adr.cli screen-transition ...` にフォールバックする。
- CLI が欠落 id を列挙して exit 3 になったら、その質問だけ手順 3 に戻る。
  既定値で埋めない。
- overlay が `check-overlay` に通らない場合は、違反を提示して止まる。
