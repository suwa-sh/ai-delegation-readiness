---
name: patch-decision-summary
description: Summarize recorded accept/discard decisions over AI-generated patches — discard rate, decided rate, discard-reason mix, and a cross-check against the patch-ownership gate. Use for the monthly retrospective after patch-ownership-check.
---

# patch-decision-summary

`aidr summarize-patch-decisions` の薄いラッパーです。決定記録(JSONL)を集計し、
破棄率・決定済み率・破棄理由の内訳・ゲートとの矛盾チェックをユーザー向けに翻訳します。
数値の健全域はこの skill も定義に持ちません。overlay が無ければ「未設定」と伝えます。

## いつ使うか

- `patch-ownership-check` skill(または `aidr check-patch-ownership --emit-decision-record`)で
  記録した決定を月次・チーム単位で振り返りたいとき
- 破棄率が高い/低いだけで判断せず、決定済み率(未決の多さ)を合わせて確認したいとき
- RED を accepted した記録がないか(ゲートと採否の矛盾)を点検したいとき
- 自社の健全域 overlay を含めて集計したいとき

## ユーザーから受け取るもの

- 決定記録の JSONL ファイル、またはそれらを含むディレクトリのパス
- 任意: `--period YYYY-MM`、`--team NAME` の絞り込み
- 任意: 適用する patch-decision overlay YAML のパス(健全域 `bands` や自社 `discard_reason` の追加)

## 手順

1. 対象パスと overlay を確認する。決定記録を編集・生成しない(この skill は読み取り専用)。

2. `definitions/patch-decision.yaml` を読み、`decision` / `discard_reason` / `reading` の語彙を
   ハードコードしない。overlay があれば先に `bin/aidr check-overlay <path>` で検証する。

3. `bin/aidr summarize-patch-decisions <path> --format json` を実行する。
   `--period` / `--team` / `--overlay` はユーザーが指定した場合のみ、同じ順序で追加する。

4. JSON をユーザー向けに翻訳する。

   - 破棄率の分母は**決定済みの件数だけ**(pending は含まない)。決定済みが 0 件なら
     `N/A` と伝え、率を捏造しない
   - 決定済み率の分母は**全パッチ**。未決件数を必ず併記する
   - 破棄理由の内訳は discarded 合計に対する割合(合計 100%)
   - `Band` が未設定なら「健全域は overlay で自社が定義するもの」と伝え、独自の閾値判断をしない
   - gate cross-check(JSON の `red_accepted` / `red_accepted_current` / `red_accepted_corrected`)は
     **fold 後の最新状態ではなく、対象スコープの全イベントから**検出したものだと伝える。
     `red_accepted`(履歴)のうち `red_accepted_current` に残るものは「まだ RED を抱えている」、
     `red_accepted_corrected` は「一度 RED を採用したが後で discarded に訂正された」と訳し分ける。
     訂正済みを「まだ問題がある」と言わない。`yellow_accepted` は設計どおりの経路(人間が判断した)
     であり、異常ではない
   - **対象月の `patch_count`(最新状態のパッチ数)が 0 でも、その月に起きた RED 採用は
     報告される**。件数がゼロだからと結果を確認せずに済ませない。exit code は
     `red_accepted`(履歴)基準で決まるため、`patch_count: 0` かつ `exit_code: 2` の組み合わせが
     起こりうる

5. 破棄率を単独で「高い/低い/妥当」と評価しない。決定済み率が低い月は、破棄率の解釈を保留する
   よう伝える。両側の失敗(乱発 / サンクコスト)は `docs/12` の読み方に従う。

6. 分母の限界を伝える。集計対象は「gate を通して記録が作られたパッチ」だけであり、
   gate を経由せず捨てられたパッチはこの集計に現れない。

## 出力の作法

- 結論(決定済み率と未決件数)を先頭に置く
- 破棄率は分母を明示して示す(「25.0% = 3/12」のように)
- 健全域が未設定のときに、独自の基準線を代わりに提示しない
- gate cross-check の矛盾(RED accepted)を見落とさず、該当 `patch_id` を挙げる。
  現在も採用中(`red_accepted_current`)か、訂正済み(`red_accepted_corrected`)かを区別して伝える

## 失敗時の扱い

- exit 3: 未知の JSON 契約違反・`discard_reason` の未宣言 id・overlay 違反・入力エラーを
  提示し、集計を強行しない
- exit 1: 未決あり。決定済み率と未決件数をそのまま報告する(異常ではなく状態)
- exit 2: RED を accepted した記録が(履歴上)1 件以上ある。すでに discarded へ訂正済みでも
  exit 2 のままであり、これは仕様(起きた事実は消えない)だと伝える。該当 `patch_id` を明示する
  (exit 1 より優先)
- overlay が `check-overlay` に通らない: 違反を提示し、半端に適用して集計しない
