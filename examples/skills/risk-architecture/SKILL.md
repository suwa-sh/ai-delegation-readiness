---
name: risk-architecture
description: Assess whether the organization RUNNING agentic AI delegation can detect, contain, and escalate representative failure scenarios. Loads definitions/risk-architecture.yaml, asks the profile / scenario / owner questions interactively, runs `aidr assess-risk-architecture`, and translates the bands into "which capability to fix first". Use when the user asks "can our org actually stop an agent incident?", "who owns agent failures?", or wants an EM/PMO-side risk-architecture check before scaling agent autonomy.
---

# risk-architecture

エージェント委任を**受けて運用する組織の側**の体制を対話的に採点します。
`aidr assess-risk-architecture` CLI の薄いラッパーです: 対話で回答を集め、
問い付き CSV(`aidr init --format csv` のテンプレート)に書き込み、CLI を JSON
モードで実行し、結果を「どの能力から埋めるか」の改善地図に翻訳します。

## いつ使うか

- エージェントの自律度(per-action 承認なしの多段実行)を上げる前に、
  事故対応体制の穴を EM / PMO 視点で洗いたいとき
- 「エージェントの事故は誰が止めるのか」に一意の名前で答えられるか
  (3 surface owner の在任)を点検したいとき
- ベンダー / 開発チームへの SLA レビューで「owner が名前付きで居るか」を
  確認項目にしたいとき

## ユーザーから受け取るもの

- 採点対象の組織・チーム名
- 任意: 自社シナリオを追加する overlay YAML のパス

## 手順

1. `definitions/risk-architecture.yaml` を読んで質問を取得する。
   質問をハードコードしない — 必ず定義ファイルから読む。
   **ユーザーに質問を提示するときは `text_ja` を優先し、無ければ `text` を使う**。

2. 質問は 3 ブロックの順で出す:
   - **profile**(7 次元 × 2 問): 組織がどの帯(pure-SE / hybrid / AI-native)かの前段診断
   - **scenario_***(8 シナリオ × 6 問): 各失敗シナリオの検知・抑制・エスカレーション
   - **owners**(3 問): contract / agent-workflow / boundary channel owner の在任
   **全質問に回答が必須**(fail-closed)。各能力は「弱い能力以上 → 強い能力」の
   単調 2 問なので、「強=yes なのに弱=no」の組は CLI が矛盾として拒否する。
   ユーザーが迷ったら決められるまで話し合う。代わりに推測しない。

3. `bin/aidr init --target risk-architecture --format csv`(overlay があれば
   `--overlay <path>`)でテンプレートを `/tmp/aidr-risk-<timestamp>.csv` に生成し、
   回答を書き込む。記入例: `examples/business/sample-risk-architecture.csv`。

4. `bin/aidr assess-risk-architecture <tmp.csv> --format json` を実行する
   (overlay があれば `--overlay <path>`)。stdout を取得する。

5. JSON をユーザー向けに翻訳する:
   - **effective_band が Low のシナリオを先頭に**。`zero_capabilities` が示す
     「0 点の能力」が最初に埋めるべき穴
   - `capped_by_missing_owner` があるシナリオは「owner の指名だけで effective が
     変わる」ことを明示する(ただし指名は仮説であり実測で検証する、下記の注意)
   - `conclusion` が `NOT_APPLICABLE`(pure-SE 帯)なら、シナリオ結果は参考であり
     ゲートは適用されないことを伝え、自律度(D2)が上がったら再採点を勧める

6. **楽観バイアスの注記を必ず添える**(JSON の `case_evidence` を確度ラベルごと引用):
   - 「owner を置けば Low が消える」は論文の derived counterfactual(実測でない)。
     自組織のインシデント実績で検証する仮説として扱う
   - boundary channel owner の共同指名は RACI アンチパターンになりやすい。
     障害時の意思決定者は 1 名に絞る
   - 統制強度は自律性レベル(D2)に比例させる(一律ガバナンスは失敗する)

## 出力の作法

- Low band(未カバー)の一覧を先に、説明の文章を後に。
- 「代表シナリオ簡易チェックであり、論文の全セル採点ではない」ことを要約に残す。
  クラスタ全体への結論を出さない。

## 失敗時の扱い

- `bin/aidr` が PATH に無い場合は、`PYTHONPATH` にリポの `src/` を設定して
  `python -m adr.cli assess-risk-architecture ...` にフォールバックする。
- CLI が欠落 id・矛盾回答を列挙して exit 3 になったら、その質問だけ手順 2 に戻る。
  既定値で埋めない。
- overlay が `check-overlay` に通らない場合は、違反を提示して止まる。
