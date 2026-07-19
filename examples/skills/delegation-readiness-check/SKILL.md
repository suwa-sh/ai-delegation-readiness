---
name: delegation-readiness-check
description: Walk a user through the 4-layer readiness check for AI delegation. Loads definitions/four-layer.yaml, asks the questions interactively, and reports PASS/REVISE/BLOCK per layer with the first gate to fix. Use when the user wants to evaluate whether a specific business process is ready to delegate to an AI agent, or asks to "do a readiness check" or "score this process."
---

# delegation-readiness-check

対象業務を 4 層 + 効果測定 + 組織 readiness のフレームワークで対話的に採点します。
`aidr check-readiness` CLI の薄いラッパーです: 対話で回答を集め、問い付きの
CSV(`aidr init --format csv` のテンプレート)に書き込み、CLI を JSON モードで
実行し、判定と「最初に直すべきゲート」を読みやすい要約に翻訳します。

## いつ使うか

- ユーザーが業務名を挙げて、AI エージェントに委任できるか知りたいとき
  (例: 「経費精算承認」「取引先登録」)
- readiness チェック / 4 層チェック / ガバナンスゲートの実行を求められたとき
- overlay(自社の強化ルール)を当てた診断をしたいとき

## ユーザーから受け取るもの

- 対象業務の名前(自由記述)
- 任意: 適用する overlay YAML のパス(複数可)

## 手順

1. 対象業務の名前を聞く。範囲が曖昧なら確認する
   (単一の承認種別か、エンドツーエンドのプロセスか)。

2. `definitions/four-layer.yaml` を読んで質問を取得する。質問をこの skill に
   ハードコードしない — 必ず定義ファイルから読む(overlay やバージョンアップと
   同期を保つため)。**ユーザーに質問を提示するときは `text_ja` を優先し、
   無ければ `text` を使う**。

3. 層ごとに質問を出す。1 層ずつまとめて聞き、質問 id ごとに
   `yes` / `no` / `unknown` を記録する。ユーザーが判断できないときは
   `unknown` にする(CLI は採点上 no として扱い、レポートでは unknown として
   区別して表示する)。

4. L4 の後に効果測定(efficacy)の質問を出し、続けて組織 readiness
   (organization.C1〜C6)の質問を出す。**組織軸を飛ばさない** —
   未回答は unknown(採点上 no)となり、他が満点でも総合 BLOCK になる。

5. `bin/aidr init --target four-layer --format csv`(overlay があれば `--overlay <path>` を
   付ける)で問い付きテンプレートを `/tmp/aidr-readiness-<timestamp>.csv` に生成し、
   集めた回答を 回答 列に書き込む(質問列は消さない — ユーザーが後から
   ファイル単体で見直せるように)。

6. `bin/aidr check-readiness <tmp.csv> --format json` を実行する
   (overlay があれば `--overlay <path>` を追加)。stdout と exit code を取得する。

7. JSON 出力をユーザー向けに翻訳する。結論(PASS / REVISE / BLOCK)を先頭に、
   verdict が pass でない層・軸ごとに:
   - どの質問が no / unknown だったか
   - その層が最初のゲートか(`blocked_from`。**並列軸(efficacy / organization)は
     ゲートに関与しない**ので、blocked_from には現れない)
   - 層・軸の `purpose` から導いた次の一手を 1 文

8. 結論が BLOCK / REVISE なら、次の具体行動を勧める:
   - ゲート層由来なら「まず層 L<N> を直して、チェックを再実行してください」
   - 並列軸(組織 readiness 等)由来なら「業務プロセスとは独立の穴です。
     軸の no / unknown 項目(受け皿・知識移転・bus factor 等)を整えてください」
   この段階では AI への委任を勧めない。

## 出力の作法

- 質問のやりとりは短く。層ごとにまとめて聞き、1 問ずつのラリーにしない。
- 構造化された判定を先に、説明の文章を後に。
- 出典事例(味の素)の引用はユーザーが文脈を求めたときだけ。
  成果物はフレームワークであり、事例研究ではない。

## 失敗時の扱い

- `bin/aidr` が PATH に無い場合は、`PYTHONPATH` にリポの `src/` を設定して
  `python -m adr.cli check-readiness ...` にフォールバックする。
- overlay が `check-overlay` に通らない場合は、違反を提示して止まる。
  半端に適用した overlay で採点しない。
- 自由回答(「たぶん」「場合による」)には yes/no の二値を促し、ニュアンスは
  レポート用のメモに残す。
